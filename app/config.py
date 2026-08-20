from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / '.env',
        env_file_encoding='utf-8',
        extra='ignore',
        env_ignore_empty=True,
    )

    app_name: str = 'Qanoni | قانوني'
    app_version: str = '4.0.0-rc'
    app_env: str = 'v4-release-candidate'
    host: str = '127.0.0.1'
    port: int = 8000

    sqlite_path: str = 'data/qanoni.sqlite3'

    # Optional answer-generation provider. A real key is never committed.
    openai_api_key: str = ''
    openai_model: str = 'gpt-5.6'
    openai_embedding_model: str = 'text-embedding-3-small'
    # Keep the writer useful in an interactive legal product: low reasoning is enough for
    # grounded synthesis because retrieval/cognition are already performed by Qanoni.
    openai_reasoning_effort: str = 'low'
    openai_timeout_seconds: float = 18.0
    openai_embedding_timeout_seconds: float = 6.0

    # Optional cognition-only LLM. Groq currently exposes an OpenAI-compatible API.
    # Qanoni always falls back to deterministic cognition if this is unavailable.
    cognition_llm_enabled: bool = True
    cognition_llm_provider: str = 'auto'  # auto | groq | off
    cognition_llm_timeout_seconds: float = 12.0
    groq_api_key: str = ''
    groq_base_url: str = 'https://api.groq.com/openai/v1'
    groq_cognition_model: str = 'openai/gpt-oss-120b'

    supabase_url: str = ''
    supabase_service_role_key: str = ''
    runtime_store: str = 'auto'  # auto | supabase | sqlite
    admin_api_key: str = ''

    sync_timeout_seconds: int = 35
    sync_max_docs_per_source: int = 100
    sync_user_agent: str = 'QanoniV4/4.0 (+Jordan legal research pilot)'

    @property
    def sqlite_file(self) -> Path:
        p = Path(self.sqlite_path)
        return p if p.is_absolute() else ROOT / p


settings = Settings()
