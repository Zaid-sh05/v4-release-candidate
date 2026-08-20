from __future__ import annotations

from .case_graph import build_case_graph
from .clarification import choose_questions
from .decision_gate import decide_next_action
from .engine_v21 import CaseCognitionEngine as BaseCaseCognitionEngine
from .issue_spotter_v4 import spot_issues
from .retrieval_planner import build_retrieval_queries
from .scenario_sanity import apply_scenario_sanity


class CaseCognitionEngine(BaseCaseCognitionEngine):
    """Scenario-fidelity layer for lawyer-oriented case analysis.

    The upstream cognition engine performs bilingual language understanding. This layer applies
    deterministic semantic sanity checks before the legal issue map is rebuilt, preventing common
    narrative mistakes such as objects becoming people, "taking a statement" becoming theft, a
    requested amount becoming a completed payment, or later police statements being lost from the
    chronology.
    """

    def analyze(self, message: str, language: str = "ar"):
        case = super().analyze(message, language)

        if apply_scenario_sanity(case):
            signal_codes = {signal.code for signal in case.semantic_signals}
            if "procedure.police_statement" in signal_codes and case.procedural_posture == "pre_case":
                case.procedural_posture = "investigation"

            case.hypotheses = spot_issues(case)
            case.domains = list(dict.fromkeys(h.domain for h in case.hypotheses)) or ["general"]
            case.clarifying_questions = choose_questions(case)
            case.retrieval_queries = build_retrieval_queries(case)
            case.decision = decide_next_action(case)
            case.graph = build_case_graph(case)

        return case


__all__ = ["CaseCognitionEngine"]
