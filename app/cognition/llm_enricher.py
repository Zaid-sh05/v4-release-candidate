from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.config import settings


_ARABIC_DIACRITICS_RE = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")


def _normalize(text: str) -> str:
    text = _ARABIC_DIACRITICS_RE.sub("", (text or "").lower())
    return " ".join(
        text.replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
        .replace("ٱ", "ا")
        .replace("ى", "ي")
        .replace("ؤ", "و")
        .split()
    )


def support_is_grounded(source_text: str, support_span: str) -> bool:
    """Accept an LLM extraction only when it points back to text the user actually wrote."""
    source = _normalize(source_text)
    span = _normalize(support_span)
    return bool(span) and span in source


@dataclass
class CognitionEnrichment:
    language: str | None = None
    user_goal: str | None = None
    procedural_posture: str | None = None
    actors: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    semantic_signals: list[dict[str, Any]] = field(default_factory=list)
    ambiguities: list[dict[str, Any]] = field(default_factory=list)
    provider: str = "none"
    model: str = ""


class CognitionEnricher(Protocol):
    def enrich(self, message: str, language: str = "ar") -> CognitionEnrichment | None: ...


SYSTEM_PROMPT = """You are the language-understanding layer of Qanoni, a Jordanian legal assistant.
Your only job is to understand what the user said. You are NOT a source of law.

Hard rules:
1. Never output a law number, article number, penalty, deadline, fee, legal conclusion, guilt finding, liability finding, or court outcome.
2. Extract facts and semantic meaning only from the user's message.
3. Every actor, event, evidence item, or semantic signal MUST include support_span copied from the user's message. If you cannot point to supporting text, omit it.
4. Do not silently convert an allegation into a proven fact. Preserve uncertainty and words such as "يقول", "يدعي", "بالغلط", "دفاعاً عن نفسي", "حسب كلامه".
5. Distinguish intent signals: accidental, intentional, premeditated, self_defense_claim, unknown. These are linguistic signals, not legal findings.
6. Distinguish evidence from the event it may support. A camera, witness, document, message, police seizure, or report is evidence, not proof by itself.
7. For long scenarios, split chained conduct into separate events in chronological order.
8. Understand Jordanian colloquial Arabic, Modern Standard Arabic, English, and mixed Arabic/English.
9. Return valid JSON only. No markdown and no explanation outside JSON.
"""


JSON_INSTRUCTIONS = """Return exactly this JSON object shape:
{
  "language": "ar|en|mixed",
  "user_goal": "penalty|rights|appeal|procedure|legal_analysis|conversation|other",
  "procedural_posture": "pre_case|investigation|litigation|post_judgment|unknown",
  "actors": [
    {"label": "...", "role": "person|worker|employer|victim|suspect|police|prosecutor|court|other", "support_span": "exact text from user"}
  ],
  "events": [
    {"event_type": "entry|breaking|taking|violence|death|injury|threat|termination|judgment|payment|communication|other", "actor_label": "... or empty", "target": "... or empty", "intent": "accidental|intentional|premeditated|self_defense_claim|unknown", "time_expression": "... or empty", "location": "... or empty", "support_span": "exact text from user"}
  ],
  "evidence": [
    {"kind": "camera|witness|document|digital|physical|medical|official_record|other", "description": "short neutral description", "support_span": "exact text from user"}
  ],
  "semantic_signals": [
    {"code": "intent.accidental|intent.intentional|intent.premeditated|intent.self_defense_claim|goal.appeal|employment.termination|property.taking|event.death|event.threat|other", "confidence": "low|medium|high", "support_span": "exact text from user"}
  ],
  "ambiguities": [
    {"question": "one concise clarification question", "reason": "why the answer could materially change case understanding", "material": true}
  ]
}
"""


class GroqCognitionEnricher:
    """Optional LLM cognition adapter using Groq's OpenAI-compatible endpoint.

    Failure is intentionally non-fatal. Qanoni must continue using the deterministic
    cognition engine when the free API is unavailable, rate-limited, or not configured.
    """

    provider = "groq"

    def __init__(self, api_key: str | None = None, model: str | None = None, timeout_seconds: float | None = None):
        self.api_key = api_key if api_key is not None else settings.groq_api_key
        self.model = model or settings.groq_cognition_model
        self.timeout_seconds = timeout_seconds or settings.cognition_llm_timeout_seconds

    @property
    def available(self) -> bool:
        return bool(self.api_key and settings.cognition_llm_enabled)

    def enrich(self, message: str, language: str = "ar") -> CognitionEnrichment | None:
        if not self.available or not message.strip():
            return None
        try:
            from openai import OpenAI

            client = OpenAI(
                api_key=self.api_key,
                base_url=settings.groq_base_url,
                timeout=self.timeout_seconds,
                max_retries=1,
            )
            response = client.chat.completions.create(
                model=self.model,
                temperature=0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"Preferred UI language: {language}\n\n{JSON_INSTRUCTIONS}\n\nUSER MESSAGE:\n{message}",
                    },
                ],
            )
            raw = (response.choices[0].message.content or "").strip()
            payload = json.loads(raw)
            return self._validated_payload(message, payload)
        except Exception:
            return None

    def _validated_payload(self, message: str, payload: dict[str, Any]) -> CognitionEnrichment:
        def grounded(items: Any) -> list[dict[str, Any]]:
            if not isinstance(items, list):
                return []
            out: list[dict[str, Any]] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                span = str(item.get("support_span") or "").strip()
                if support_is_grounded(message, span):
                    out.append(item)
            return out

        valid_goals = {"penalty", "rights", "appeal", "procedure", "legal_analysis", "conversation", "other"}
        valid_postures = {"pre_case", "investigation", "litigation", "post_judgment", "unknown"}
        valid_languages = {"ar", "en", "mixed"}

        language = payload.get("language") if payload.get("language") in valid_languages else None
        goal = payload.get("user_goal") if payload.get("user_goal") in valid_goals else None
        posture = payload.get("procedural_posture") if payload.get("procedural_posture") in valid_postures else None

        ambiguities = payload.get("ambiguities") if isinstance(payload.get("ambiguities"), list) else []
        ambiguities = [a for a in ambiguities if isinstance(a, dict) and a.get("question") and a.get("material") is True][:5]

        return CognitionEnrichment(
            language=language,
            user_goal=goal,
            procedural_posture=posture,
            actors=grounded(payload.get("actors")),
            events=grounded(payload.get("events")),
            evidence=grounded(payload.get("evidence")),
            semantic_signals=grounded(payload.get("semantic_signals")),
            ambiguities=ambiguities,
            provider=self.provider,
            model=self.model,
        )


def default_cognition_enricher() -> CognitionEnricher | None:
    provider = (settings.cognition_llm_provider or "auto").strip().lower()
    if provider in {"off", "none", "disabled"}:
        return None
    if provider in {"auto", "groq"} and settings.groq_api_key:
        return GroqCognitionEnricher()
    return None
