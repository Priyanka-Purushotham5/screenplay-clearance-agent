from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str

    # Where the browser may call this API from, comma separated.
    #
    # This was hard-coded to localhost:3000. That failure is invisible from
    # the server side: the API answers normally, the browser discards the
    # response because the origin does not match, and the UI simply never
    # fills in. Nothing is logged, because nothing went wrong here.
    cors_origins: str = "http://localhost:3000"

    # Create any missing tables on startup.
    #
    # Locally the schema comes from db/init.sql, which Postgres runs through
    # docker-entrypoint-initdb.d. That hook is a feature of the postgres
    # image, not of Postgres, so a managed database has no equivalent and a
    # hosted deployment comes up against an empty schema and fails every
    # query. Off by default, so local behaviour does not change.
    auto_init_db: bool = False

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

    #upload cap - 25MB
    max_upload_bytes: int = 25 * 1024 * 1024;

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("database_url")
    @classmethod
    def _async_driver(cls, v: str) -> str:
        """Accept the URL shape managed Postgres providers hand out.

        Render, Neon, Heroku and friends all export DATABASE_URL as
        `postgres://` or `postgresql://`, which SQLAlchemy resolves to the
        synchronous psycopg driver. Every query in this application goes
        through create_async_engine, so that URL raises InvalidRequestError
        at import time. Rewriting it here means the deployment can use the
        provider's variable verbatim instead of maintaining a second copy
        that has to be kept in step by hand.
        """
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+asyncpg://" + v[len(prefix):]
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
