from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str

    # Credentials are optional because there are two auth paths and neither
    # needs both keys.  Local runs read gemini_api_key; docker-compose sets
    # GOOGLE_GENAI_USE_VERTEXAI=true and authenticates through mounted ADC.
    # The agents assert what they need at call time, so importing this module
    # never fails over a key the caller was not going to use.
    gemini_api_key: Optional[str] = None
    parallel_api_key: Optional[str] = None
    google_genai_use_vertexai: bool = False

    # Flash for extraction, Pro for assessment.  Pinned exactly — the A2 probe
    # found that `gemini-2.0-flash` silently resolves to `gemini-2.5-flash`,
    # which would make run-to-run results incomparable.
    extraction_model: str = "gemini-2.5-flash"
    assessment_model: str = "gemini-2.5-pro"

    upload_dir: str = "./uploads"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
