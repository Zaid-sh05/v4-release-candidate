from __future__ import annotations

from dataclasses import dataclass, field

from .engine import CaseCognitionEngine
from .models import CaseModel, Fact


NEW_TOPIC_MARKERS = (
    "شو عقوبة", "ما عقوبة", "ما هي عقوبة", "قانون العمل", "قانون العقوبات",
    "القانون المدني", "قانون الشركات", "كم مدة الاستئناف", "كيف أقدم شكوى",
)
FOLLOWUP_MARKERS = (
    "راتبي", "عقدي", "صارلي", "ما أعطوني", "ما اعطوني", "السبب", "كان بالغلط",
    "ما كنت أقصد", "كنت أقصد", "كان معه", "صار بالليل", "وصلني التبليغ",
    "صدر بتاريخ", "نعم", "لا", "اه", "آه",
)

# Strong, unambiguous domain signals. A short message that clearly names a domain the
# current case does NOT belong to is a new case, never a followup detail - regardless of
# word count. This is deliberately conservative (only the clearest single-word signals per
# domain) since it only ever blocks the length-based fallback below, never joins facts.
_DOMAIN_SIGNAL_TERMS: dict[str, tuple[str, ...]] = {
    "criminal": ("سرق", "سرقة", "سرقو", "اقتحم", "اقتحام", "قتل", "طعن", "اعتدى", "اعتداء"),
    "traffic": ("حادث سير", "بسوق", "دهست", "تصادم", "مركبتي", "سيارتي"),
    "cyber": ("ابتزاز", "ابتزني", "هكر", "اختراق", "واتساب", "انستغرام", "فيسبوك"),
    "labor": ("فصلني", "صاحب العمل", "راتبي", "عقد عملي"),
    "personal_status": ("طلاق", "حضانة", "نفقة", "خلع"),
}


def _signaled_conflicting_domain(message: str, current_domains: list[str]) -> bool:
    low = message.lower()
    current = set(current_domains)
    for domain, terms in _DOMAIN_SIGNAL_TERMS.items():
        if domain in current:
            continue
        if any(term.lower() in low for term in terms):
            return True
    return False


@dataclass
class ConversationCaseState:
    engine: CaseCognitionEngine = field(default_factory=CaseCognitionEngine)
    current_case: CaseModel | None = None
    turns: list[str] = field(default_factory=list)

    def _is_followup(self, message: str) -> bool:
        if not self.current_case:
            return False
        text = message.strip()
        low = text.lower()
        if any(m.lower() in low for m in FOLLOWUP_MARKERS):
            return True
        if _signaled_conflicting_domain(text, self.current_case.domains):
            return False
        if len(text.split()) <= 12 and not any(m.lower() in low for m in NEW_TOPIC_MARKERS):
            return True
        return False

    def ingest(self, message: str, language: str = "ar") -> tuple[CaseModel, bool]:
        """Ingest a turn and return (case, continued_existing_case).

        V4 keeps the user's original turns for traceability, but rebuilds cognition from the
        accumulated user facts. A clearly independent legal question starts a fresh case.
        """
        continued = self._is_followup(message)
        if continued:
            self.turns.append(message)
            joined = "\n".join(self.turns)
            rebuilt = self.engine.analyze(joined, language)
            # Mark the latest turn explicitly so downstream components can distinguish a fact
            # supplied after clarification from the original narrative.
            rebuilt.facts.append(Fact(text=message, category="followup", source="user_followup"))
            self.current_case = rebuilt
            return rebuilt, True

        self.turns = [message]
        self.current_case = self.engine.analyze(message, language)
        return self.current_case, False

    def reset(self) -> None:
        self.current_case = None
        self.turns = []
