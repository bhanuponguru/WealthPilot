"""Central settings.

Precedence for every setting (highest first):
  1. explicit init kwargs (tests)
  2. the project's ``.env`` file
  3. the process / global environment
  4. field defaults

The NIM key is read from ``NVIDIA_API_KEY`` or ``NVIDIA_NIM_API_KEY`` (either
name, in either place). It has no default: if it is set in neither ``.env`` nor
the environment, ``get_settings()`` raises a ``RuntimeError``. A blank value
(e.g. ``NVIDIA_API_KEY=`` copied from ``.env.example``) counts as unset, so it
falls through to the global environment instead of masking it.

Note: langchain-nvidia-ai-endpoints only auto-reads ``NVIDIA_API_KEY``, so the
NIM gateway must always pass ``api_key=get_settings().nvidia_api_key`` explicitly.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

# src/wealthpilot/config.py -> project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_ignore_empty=True,  # blank values are treated as unset
        populate_by_name=True,
        extra="ignore",
    )

    nvidia_api_key: SecretStr = Field(
        validation_alias=AliasChoices("NVIDIA_API_KEY", "NVIDIA_NIM_API_KEY")
    )  # required: no default
    database_url: str = "postgresql://wealthpilot:wealthpilot@127.0.0.1:5432/wealthpilot"
    mlflow_tracking_uri: str = "http://127.0.0.1:5000"
    nim_rpm_budget: int = 15  # ceiling for the adaptive shared limiter; NIM returned real 429s at 25-35

    # Model IDs verified callable for this account on 2026-11-11 (the public catalog lists many retired ones).
    chat_model: str = "nvidia/nemotron-3.5-lightning-30b-a3b"   # fast + available; the 550B model returned 503s during testing
    chat_fallback_model: str = ""  # disabled by default: the only other usable chat model (550B) returned garbled text on long outputs. E4 enables it explicitly.
    vlm_model: str = "nvidia/nemotron-3.5-super-vl-120b-a12b"
    rerank_model: str = "nvidia/llama-nemotron-rerank-vl-1b-v2"
    embed_model: str = "nomic-embed-text"  # served by local Ollama (no NIM embedding model works for this account)
    ollama_url: str = "http://127.0.0.1:11434"
    nim_cache_enabled: bool = True
    nim_timeout_s: float = 45.0  # fail over faster than the library default of 60 s
    nim_thinking: bool = False  # reasoning models: thinking off = ~0 reasoning tokens, 3x faster

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # pydantic-settings default is init > env > dotenv. We want .env to win.
        return (init_settings, dotenv_settings, env_settings, file_secret_settings)


@lru_cache
def get_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        if any(e["type"] == "missing" for e in exc.errors()):
            raise RuntimeError(
                "NVIDIA API key not found. Set NVIDIA_API_KEY (or NVIDIA_NIM_API_KEY) in "
                f"{PROJECT_ROOT / '.env'} or export it in your shell environment."
            ) from None
        raise
