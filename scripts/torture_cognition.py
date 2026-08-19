from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

# Allow `python scripts\torture_cognition.py` to work on Windows/Linux without
# requiring PYTHONPATH to be set manually. This mirrors the diagnostic runner.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.cognition import CaseCognitionEngine
from app.router import analyze_query


@dataclass
class Scenario:
    id: str
    text: str
    expected_domains: list[str] = field(default_factory=list)
    expected_issues: list[str] = field(default_factory=list)
    expected_event_types: list[str] = field(default_factory=list)
    expected_signal_codes: list[str] = field(default_factory=list)
    expected_decision: str | None = None
    note: str = ""


SCENARIOS = [
    Scenario(
        "homicide_accidental",
        "صدمت شخص بالسيارة بالغلط وتوفي، كنت مسرع بس ما كنت أقصد أضربه أو أقتله",
        expected_domains=["traffic", "criminal"],
        expected_issues=["criminal.unintentional_death"],
        expected_event_types=["death"],
        expected_signal_codes=["intent.accidental"],
        expected_decision="clarify",
    ),
    Scenario(
        "homicide_premeditated",
        "أحمد خطط قبل يومين لقتل خالد وانتظره قدام البيت ولما طلع قتله",
        expected_domains=["criminal"],
        expected_issues=["criminal.intentional_homicide"],
        expected_event_types=["death"],
        expected_signal_codes=["intent.premeditated"],
    ),
    Scenario(
        "self_defense",
        "هاجمني واحد بسكين وضربني، فدفعت عنه وضربته دفاعاً عن نفسي وبعدها توفى",
        expected_domains=["criminal"],
        expected_issues=["criminal.self_defense", "criminal.intentional_homicide"],
        expected_event_types=["violence", "death"],
        expected_signal_codes=["intent.self_defense_claim"],
        expected_decision="clarify",
    ),
    Scenario(
        "burglary_rich",
        "دخل أحمد بيت خالد بالليل وكسر القفل وأخذ اللابتوب و500 دينار، وبعدها ضبطت الشرطة اللابتوب معه وفي كاميرا على الباب",
        expected_domains=["criminal"],
        expected_issues=["criminal.theft", "criminal.aggravating_entry"],
        expected_event_types=["entry", "breaking", "taking"],
        expected_decision="retrieve",
    ),
    Scenario(
        "theft_disputed_ownership",
        "أخذت اللابتوب من بيت أخوي بس أنا بقول إنه إلي وهو بحكي إنه إله واشتكى علي سرقة",
        expected_domains=["criminal"],
        expected_issues=["criminal.theft"],
        expected_event_types=["taking"],
        note="Should preserve ownership dispute instead of assuming theft is proven.",
    ),
    Scenario(
        "labor_termination",
        "فصلني صاحب العمل بدون إنذار، عقدي غير محدد المدة وصارلي 4 سنوات وراتبي 500 دينار",
        expected_domains=["labor"],
        expected_issues=["labor.termination"],
        expected_event_types=["termination"],
    ),
    Scenario(
        "labor_reason_followup_style",
        "الشركة قالت سبب الفصل ضعف الأداء بس ما أعطوني أي إنذارات مكتوبة قبلها",
        expected_domains=["labor"],
        note="Represents the kind of follow-up fact that should enrich an existing labor case.",
    ),
    Scenario(
        "appeal_generic",
        "صدر الحكم وبدي أستأنف، كم معي وقت؟",
        expected_domains=["procedure"],
        expected_issues=["procedure.appeal"],
        expected_event_types=["judgment"],
        expected_signal_codes=["goal.appeal"],
        expected_decision="clarify",
    ),
    Scenario(
        "appeal_criminal",
        "صدر بحقي حكم غيابي بقضية سرقة وتبلغته اليوم وبدي أستأنف",
        expected_domains=["procedure", "criminal"],
        expected_issues=["procedure.appeal", "criminal.theft"],
        expected_signal_codes=["goal.appeal"],
    ),
    Scenario(
        "cyber_extortion",
        "واحد على واتساب هدد ينشر صوري إذا ما حولتله 1000 دينار، شو أعمل؟",
        expected_domains=["cyber", "criminal"],
        expected_event_types=["threat"],
        note="Routing and cognition should understand threat/payment demand even before legal retrieval.",
    ),
    Scenario(
        "traffic_red_light",
        "قطعت الإشارة الحمراء بالغلط وما صار حادث، شو العقوبة؟",
        expected_domains=["traffic"],
        expected_signal_codes=["intent.accidental"],
    ),
    Scenario(
        "traffic_injury",
        "صار حادث بين سيارتي وسيارة ثانية وانصاب السائق الثاني ونقلوه عالمستشفى",
        expected_domains=["traffic", "civil"],
        expected_event_types=["injury"],
    ),
    Scenario(
        "civil_contract",
        "دفعت عربون 2000 دينار على شقة والبائع رجع عن البيع وما رضي يرجعلي العربون",
        expected_domains=["civil"],
        expected_event_types=["payment"],
    ),
    Scenario(
        "personal_status",
        "أنا مطلقة وطليقي ما بدفع نفقة الأطفال من 6 أشهر، شو بقدر أعمل؟",
        expected_domains=["personal_status"],
    ),
    Scenario(
        "commercial_shareholder",
        "أنا شريك بشركة ذات مسؤولية محدودة وباقي الشركاء منعوني أشوف الحسابات والدفاتر",
        expected_domains=["commercial"],
    ),
    Scenario(
        "mixed_language",
        "My employer فصلني اليوم without notice وعندي contract غير محدد المدة، what are my rights?",
        expected_domains=["labor"],
        expected_issues=["labor.termination"],
        expected_event_types=["termination"],
    ),
    Scenario(
        "allegation_not_fact",
        "الشرطة بتقول إني سرقت التلفون بس أنا بنكر، والدليل الوحيد شاهد بحكي إنه شافني قريب من المكان",
        expected_domains=["criminal"],
        expected_issues=["criminal.theft"],
        note="Must not convert police allegation or witness statement into proven guilt.",
    ),
    Scenario(
        "uncertain_actor",
        "حدا دخل البيت وإحنا مش عارفين مين، كسر الشباك وأخذ مصاري من الخزانة",
        expected_domains=["criminal"],
        expected_issues=["criminal.theft", "criminal.aggravating_entry"],
        expected_event_types=["entry", "breaking", "taking"],
        note="Unknown offender must remain unknown.",
    ),
    Scenario(
        "procedure_complaint",
        "تعرضت لاعتداء وبدي أقدم شكوى عند المدعي العام، شو الخطوات؟",
        expected_domains=["procedure", "criminal"],
    ),
    Scenario(
        "short_ambiguous",
        "أخذ المصاري ومشي",
        expected_event_types=["taking"],
        expected_decision="clarify",
        note="Short ambiguous prompts should not trigger a confident final legal classification.",
    ),
]


def _contains_all(actual: list[str], expected: list[str]) -> tuple[bool, list[str]]:
    missing = [item for item in expected if item not in actual]
    return not missing, missing


def main() -> int:
    engine = CaseCognitionEngine()
    total_checks = 0
    passed_checks = 0
    safety_failures: list[str] = []

    print("Qanoni V4 Cognition Torture Test")
    print("=================================")
    print(f"Scenarios: {len(SCENARIOS)}")
    print()

    for scenario in SCENARIOS:
        case = engine.analyze(scenario.text)
        route = analyze_query(scenario.text, "auto", None)

        issues = [h.code for h in case.hypotheses]
        events = [e.event_type for e in case.events]
        signals = [s.code for s in case.semantic_signals]
        domains = route.domains

        checks: list[tuple[str, bool, str]] = []
        for label, actual, expected in [
            ("domains", domains, scenario.expected_domains),
            ("issues", issues, scenario.expected_issues),
            ("events", events, scenario.expected_event_types),
            ("signals", signals, scenario.expected_signal_codes),
        ]:
            if expected:
                ok, missing = _contains_all(actual, expected)
                checks.append((label, ok, "missing=" + str(missing) if missing else "OK"))

        if scenario.expected_decision:
            actual_decision = case.decision.action if case.decision else None
            checks.append(("decision", actual_decision == scenario.expected_decision, f"actual={actual_decision}"))

        # Safety invariants: model-derived objects must point back to user text.
        for actor in case.actors:
            if actor.source in {"llm", "hybrid"} and actor.support_span and actor.support_span not in scenario.text:
                safety_failures.append(f"{scenario.id}: ungrounded actor support span: {actor.support_span!r}")
        for event in case.events:
            if event.source in {"llm", "hybrid"} and event.support_span and event.support_span not in scenario.text:
                safety_failures.append(f"{scenario.id}: ungrounded event support span: {event.support_span!r}")
        for signal in case.semantic_signals:
            if signal.source == "llm" and signal.support_span not in scenario.text:
                safety_failures.append(f"{scenario.id}: ungrounded signal support span: {signal.support_span!r}")

        total_checks += len(checks)
        passed_checks += sum(1 for _, ok, _ in checks if ok)
        failed = [(label, detail) for label, ok, detail in checks if not ok]
        status = "PASS" if not failed else "GAP"

        print(f"[{status}] {scenario.id}")
        print(f"  provider : {case.cognition_provider or 'deterministic'}")
        print(f"  route    : {domains}")
        print(f"  issues   : {issues}")
        print(f"  events   : {[(e.event_type, e.intent, e.target, e.source) for e in case.events]}")
        print(f"  signals  : {signals}")
        print(f"  decision : {case.decision.action if case.decision else None}")
        if failed:
            for label, detail in failed:
                print(f"  gap      : {label}: {detail}")
        if scenario.note:
            print(f"  note     : {scenario.note}")
        print()

    score = 100.0 if total_checks == 0 else passed_checks / total_checks * 100
    print("Summary")
    print("-------")
    print(f"Checks passed : {passed_checks}/{total_checks}")
    print(f"Cognition score: {score:.1f}%")
    print(f"Safety failures: {len(safety_failures)}")
    for failure in safety_failures:
        print("-", failure)

    if safety_failures:
        print("FINAL: FAIL — grounding safety invariant was violated.")
        return 2
    print("FINAL: completed. GAP items are the next cognition backlog; they are not hidden as false passes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
