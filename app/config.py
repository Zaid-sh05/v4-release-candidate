from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / '.env', env_file_encoding='utf-8', extra='ignore', env_ignore_empty=True)

    app_name: str = 'Qanoni | قانوني'
    app_version: str = '3.6.0-pilot-final'
    app_env: str = 'pilot-final'
    host: str = '127.0.0.1'
    port: int = 8000

    sqlite_path: str = 'data/qanoni.sqlite3'

    openai_api_key: str = ''
    openai_model: str = 'gpt-5.6'
    openai_embedding_model: str = 'text-embedding-3-small'

    supabase_url: str = ''
    supabase_service_role_key: str = ''
    runtime_store: str = 'auto'  # auto | supabase | sqlite
    admin_api_key: str = ''

    sync_timeout_seconds: int = 35
    sync_max_docs_per_source: int = 100
    sync_user_agent: str = 'QanoniPilot/3.6 (+Jordan legal research pilot)'

    @property
    def sqlite_file(self) -> Path:
        p = Path(self.sqlite_path)
        return p if p.is_absolute() else ROOT / p

settings = Settings()
