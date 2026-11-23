from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    supabase_url: str = ""
    supabase_service_role_key: str = ""
    ai_service_secret: str = ""

    # Providers: "gemini" (free tier via Google AI Studio) or "openai"
    embedding_provider: str = "gemini"
    embedding_model: str = ""  # empty -> provider default
    # embedding tokens per minute (Gemini free tier: 30000); 0 = no client-side limit
    embedding_tpm: int = 30_000
    llm_provider: str = "gemini"
    llm_model: str = ""  # empty -> provider default
    # comma-separated models tried when the main one is overloaded; unset -> provider default chain
    llm_fallback_models: str | None = None

    gemini_api_key: str = ""
    openai_api_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
