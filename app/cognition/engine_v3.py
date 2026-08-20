from __future__ import annotations

from .case_graph import build_case_graph
from .clarification import choose_questions
from .decision_gate import decide_next_action
from .engine_v21 import CaseCognitionEngine as BaseCaseCognitionEngine
from .issue_spotter_v5_guard import spot_issues
from .retrieval_planner import build_retrieval_queries
from .scenario_sanity_v4 import apply_scenario_sanity


class CaseCognitionEngine(BaseCaseCognitionEngine):
    """Scenario-fidelity layer for lawyer-oriented case analysis.

    The upstream cognition engine performs bilingual language understanding. This layer applies
    deterministic semantic sanity checks and the extended lawyer issue vocabulary before rebuilding
    the legal issue map. The rebuild is triggered either by a scenario correction or by newly spotted
    V5 issues, so domains such as wages, contracts, family matters, company authority, cyber incidents,
    and service/deadline questions are not dependent on an unrelated sanity correction firing first.
    """

    def analyze(self, message: str, language: str = "ar"):
        case = super().analyze(message, language)
        prior_decision = case.decision
        preserve_short_ambiguous = bool(
            prior_decision and "short_ambiguous_prompt" in getattr(prior_decision, "blockers", [])
        )

        sanity_changed = apply_scenario_sanity(case)
        next_hypotheses = spot_issues(case)
        prior_codes = [hypothesis.code for hypothesis in getattr(case, "hypotheses", [])]
        next_codes = [hypothesis.code for hypothesis in next_hypotheses]
        issue_map_changed = prior_codes != next_codes

        if sanity_changed or issue_map_changed:
            signal_codes = {signal.code for signal in case.semantic_signals}
            if "procedure.police_statement" in signal_codes and case.procedural_posture == "pre_case":
                case.procedural_posture = "investigation"

            case.hypotheses = next_hypotheses
            case.domains = list(dict.fromkeys(h.domain for h in case.hypotheses)) or ["general"]
            case.clarifying_questions = choose_questions(case)
            case.retrieval_queries = build_retrieval_queries(case)
            case.decision = decide_next_action(case)
            if preserve_short_ambiguous:
                case.decision = prior_decision
            case.graph = build_case_graph(case)

        return case


__all__ = ["CaseCognitionEngine"]
