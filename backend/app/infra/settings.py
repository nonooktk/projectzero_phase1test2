from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    cors_origins_raw: str = "http://localhost:3000"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    vector_search_backend: str = "simple"
    enable_supabase_save: bool = True
    enable_idempotency: bool = True
    openai_timeout_seconds: float = 45.0
    openai_max_retries: int = 2

    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins_raw.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
