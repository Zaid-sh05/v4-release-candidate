from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import settings
from app.cognition import CaseCognitionEngine
from app.cognition.llm_enricher import GroqCognitionEnricher

SAMPLE = (
    "دخل أحمد بيت خالد بالليل وكسر القفل وأخذ اللابتوب، "
    "وبعدها ضبطت الشرطة الجهاز معه وكانت في كاميرا على الباب."
)


def safe_error(exc: Exception) -> str:
    text = f"{type(exc).__name__}: {exc}"
    if settings.groq_api_key:
        text = text.replace(settings.groq_api_key, "***")
    return text[:700]


def main() -> int:
    print("Qanoni V4 Cognition Diagnostic")
    print("=" * 31)
    print("Project root:", ROOT)
    print("Current cwd :", Path.cwd())
    print("V4 env file:", (ROOT / ".env").exists())
    print("App version:", settings.app_version)
    print("App env    :", settings.app_env)
    print()

    print("Cognition config")
    print("----------------")
    print("enabled     :", settings.cognition_llm_enabled)
    print("provider    :", settings.cognition_llm_provider)
    print("groq key    :", "configured" if bool(settings.groq_api_key) else "MISSING")
    print("groq model  :", settings.groq_cognition_model)
    print("groq base   :", settings.groq_base_url)
    print()

    print("Deterministic Arabic test")
    print("-------------------------")
    deterministic = CaseCognitionEngine(enable_llm=False).analyze(SAMPLE)
    print("facts       :", len(deterministic.facts))
    print("events      :", [(e.event_type, e.target) for e in deterministic.events])
    print("evidence    :", [e.kind for e in deterministic.evidence])
    print("issues      :", [h.code for h in deterministic.hypotheses])
    deterministic_ok = (
        {"entry", "breaking", "taking"}.issubset({e.event_type for e in deterministic.events})
        and "criminal.theft" in {h.code for h in deterministic.hypotheses}
    )
    print("result      :", "OK" if deterministic_ok else "FAILED")
    print()

    if not settings.cognition_llm_enabled:
        print("Groq test   : SKIPPED (COGNITION_LLM_ENABLED=false)")
        return 2 if not deterministic_ok else 0
    if not settings.groq_api_key:
        print("Groq test   : SKIPPED (GROQ_API_KEY is missing from V4 .env)")
        return 2 if not deterministic_ok else 3

    print("Groq API test")
    print("-------------")
    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=settings.groq_api_key,
            base_url=settings.groq_base_url,
            timeout=settings.cognition_llm_timeout_seconds,
            max_retries=0,
        )
        response = client.chat.completions.create(
            model=settings.groq_cognition_model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "Return valid JSON only."},
                {"role": "user", "content": 'Return exactly {"ok": true}.'},
            ],
        )
        print("basic API   : OK")
        print("api content :", (response.choices[0].message.content or "")[:160])
    except Exception as exc:
        print("basic API   : FAILED")
        print("error       :", safe_error(exc))
        return 4

    print()
    print("Grounded enrichment test")
    print("------------------------")
    enricher = GroqCognitionEnricher()
    enrichment = enricher.enrich(SAMPLE, "ar")
    if enrichment is None:
        print("enrichment  : FAILED (adapter returned None)")
        return 5
    print("provider    :", enrichment.provider)
    print("model       :", enrichment.model)
    print("actors      :", [a.get("label") for a in enrichment.actors])
    print("events      :", [e.get("event_type") for e in enrichment.events])
    print("signals     :", [s.get("code") for s in enrichment.semantic_signals])

    print()
    print("Hybrid cognition test")
    print("---------------------")
    hybrid = CaseCognitionEngine().analyze(SAMPLE)
    print("provider    :", hybrid.cognition_provider)
    print("model       :", hybrid.cognition_model)
    print("events      :", [(e.event_type, e.intent, e.target, e.source) for e in hybrid.events])
    print("issues      :", [h.code for h in hybrid.hypotheses])
    print("decision    :", hybrid.decision.action if hybrid.decision else None)
    hybrid_ok = hybrid.cognition_provider == "groq"
    print("result      :", "OK" if hybrid_ok else "FAILED")

    if deterministic_ok and hybrid_ok:
        print("\nFINAL: cognition stack is working correctly.")
        return 0
    print("\nFINAL: check the failed section above.")
    return 6


if __name__ == "__main__":
    raise SystemExit(main())
