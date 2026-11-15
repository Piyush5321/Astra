"""Environment-backed application configuration."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _positive_float(name: str, default: str) -> float:
    raw = os.getenv(name, default)
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid {name} {raw!r}: expected a number.") from exc
    if value <= 0:
        raise ValueError(f"Invalid {name} {value}: expected a positive number.")
    return value


@dataclass(frozen=True)
class Settings:
    """Application settings populated from environment variables."""

    app_name: str
    environment: str
    api_host: str
    api_port: int
    database_url: str
    datasets_dir: Path
    reports_dir: Path
    http_timeout_seconds: float
    power_cache_ttl_hours: float
    llm_provider: str
    llm_api_key: str
    llm_model: str
    llm_base_url: str
    llm_timeout_seconds: float
    cors_origins: tuple[str, ...]

    @property
    def llm_enabled(self) -> bool:
        """Whether an LLM provider is configured with credentials."""
        return self.llm_provider == "anthropic" and bool(
            self.llm_api_key or os.getenv("ANTHROPIC_API_KEY"))

    @classmethod
    def from_environment(cls) -> "Settings":
        """Create settings from environment variables and development defaults."""
        raw_port = os.getenv("API_PORT", "8000")
        try:
            api_port = int(raw_port)
        except ValueError as exc:
            raise ValueError(
                f"Invalid API_PORT {raw_port!r}: expected an integer from 1 to 65535."
            ) from exc

        if not 1 <= api_port <= 65535:
            raise ValueError(
                f"Invalid API_PORT {api_port}: expected a value from 1 to 65535."
            )

        api_host = os.getenv("API_HOST", "127.0.0.1").strip()
        if not api_host:
            raise ValueError("API_HOST must not be empty.")

        app_name = os.getenv("APP_NAME", "ASTRA").strip()
        if not app_name:
            raise ValueError("APP_NAME must not be empty.")

        environment = os.getenv("ENVIRONMENT", "development").strip()
        if not environment:
            raise ValueError("ENVIRONMENT must not be empty.")

        # Serverless hosts (Vercel) only allow writes under /tmp.
        data_dir = Path("/tmp/astra") if os.getenv("VERCEL") else PROJECT_ROOT / "data"
        database_url = os.getenv("DATABASE_URL", "").strip() or (
            f"sqlite:///{(data_dir / 'astra.db').as_posix()}"
        )
        # Hosted Postgres providers (Neon, Vercel) hand out postgres:// URLs;
        # SQLAlchemy needs the dialect+driver form.
        for prefix in ("postgres://", "postgresql://"):
            if database_url.startswith(prefix):
                database_url = "postgresql+psycopg://" + database_url[len(prefix):]

        llm_provider = os.getenv("LLM_PROVIDER", "none").strip().lower() or "none"
        if llm_provider not in {"none", "anthropic"}:
            raise ValueError(
                f"Invalid LLM_PROVIDER {llm_provider!r}: expected none or anthropic."
            )

        cors = os.getenv("CORS_ORIGINS", "").strip()

        return cls(
            app_name=app_name,
            environment=environment,
            api_host=api_host,
            api_port=api_port,
            database_url=database_url,
            datasets_dir=Path(os.getenv("DATASETS_DIR", "") or PROJECT_ROOT / "datasets"),
            reports_dir=Path(os.getenv("REPORTS_DIR", "") or data_dir / "reports"),
            http_timeout_seconds=_positive_float("HTTP_TIMEOUT_SECONDS", "60"),
            power_cache_ttl_hours=_positive_float("POWER_CACHE_TTL_HOURS", "720"),
            llm_provider=llm_provider,
            llm_api_key=os.getenv("LLM_API_KEY", "").strip(),
            llm_model=os.getenv("LLM_MODEL", "").strip() or "claude-opus-5-5",
            llm_base_url=os.getenv("LLM_BASE_URL", "").strip(),
            llm_timeout_seconds=_positive_float("LLM_TIMEOUT_SECONDS", "60"),
            cors_origins=tuple(o.strip() for o in cors.split(",") if o.strip()),
        )


settings = Settings.from_environment()
