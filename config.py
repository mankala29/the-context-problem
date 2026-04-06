from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str
    model: str = "claude-opus-4-6"
    token_budget: int = 600      # max tokens allowed in context window
    quality_threshold: float = 0.5  # minimum quality score before retry

    class Config:
        env_file = ".env"


settings = Settings()
