import os
from functools import lru_cache
from pathlib import Path
from typing import List, Optional
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def get_env_file_path() -> str:
    """
    Dynamically locate the .env file across execution environments.
    Checks:
      1. ENV_FILE environment variable if set
      2. Current working directory
      3. Project 'src/.env' relative to this module
      4. Workspace root directory
    """
    if "ENV_FILE" in os.environ and os.path.exists(os.environ["ENV_FILE"]):
        return os.environ["ENV_FILE"]

    cwd_env = Path(".env")
    if cwd_env.is_file():
        return str(cwd_env)

    # Path to src/
    src_env = Path(__file__).resolve().parent.parent / ".env"
    if src_env.is_file():
        return str(src_env)

    # Path to repository root
    root_env = Path(__file__).resolve().parent.parent.parent / ".env"
    if root_env.is_file():
        return str(root_env)

    return ".env"


class Settings(BaseSettings):
    """
    NexusRAG Application Settings.
    Centralized configuration management with support for multiple LLM backends,
    vector databases, distributed task queues, and persistent storage.
    """

    # Application Info
    APP_NAME: str = "NexusRAG"
    APP_VERSION: str = "1.0.0"

    # File Processing Constraints
    FILE_ALLOWED_TYPES: List[str] = ["text/plain", "application/pdf"]
    FILE_MAX_SIZE: int = 10  # in MB
    FILE_DEFAULT_CHUNK_SIZE: int = 512000  # 512KB buffer

    # PostgreSQL Database
    POSTGRES_USERNAME: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_MAIN_DATABASE: str = "minirag"

    # LLM & Embedding Selection
    GENERATION_BACKEND: str = "GEMINI"
    EMBEDDING_BACKEND: str = "GEMINI"

    # Provider API Keys
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_API_URL: Optional[str] = None
    COHERE_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None

    # Model Parameters
    GENERATION_MODEL_ID_LITERAL: Optional[List[str]] = None
    GENERATION_MODEL_ID: Optional[str] = None
    EMBEDDING_MODEL_ID: Optional[str] = None
    EMBEDDING_MODEL_SIZE: Optional[int] = None

    # Hyperparameters (supports both proper spelling and legacy DAFAULT typo)
    INPUT_DEFAULT_MAX_CHARACTERS: Optional[int] = 1024
    INPUT_DAFAULT_MAX_CHARACTERS: Optional[int] = None

    GENERATION_DEFAULT_MAX_TOKENS: Optional[int] = 1000
    GENERATION_DAFAULT_MAX_TOKENS: Optional[int] = None

    GENERATION_DEFAULT_TEMPERATURE: Optional[float] = 0.1
    GENERATION_DAFAULT_TEMPERATURE: Optional[float] = None

    # Vector Database
    VECTOR_DB_BACKEND_LITERAL: Optional[List[str]] = None
    VECTOR_DB_BACKEND: str = "QDRANT"
    VECTOR_DB_PATH: str = "qdrant_db"
    VECTOR_DB_DISTANCE_METHOD: Optional[str] = "cosine"
    VECTOR_DB_PGVEC_INDEX_THRESHOLD: int = 100

    # Internationalization / Prompts
    PRIMARY_LANG: str = "ar"
    DEFAULT_LANG: str = "en"

    # Celery Task Queue
    CELERY_BROKER_URL: Optional[str] = None
    CELERY_RESULT_BACKEND: Optional[str] = None
    CELERY_TASK_SERIALIZER: str = "json"
    CELERY_TASK_TIME_LIMIT: int = 600
    CELERY_TASK_ACKS_LATE: bool = True
    CELERY_WORKER_CONCURRENCY: int = 2
    CELERY_FLOWER_PASSWORD: Optional[str] = None
    CELERY_TASK_ALWAYS_EAGER: bool = False

    model_config = SettingsConfigDict(
        env_file=get_env_file_path(),
        extra="ignore",
        env_file_encoding="utf-8"
    )

    @model_validator(mode="after")
    def sync_legacy_hyperparameters(self) -> "Settings":
        """Sync properly spelled settings with legacy typo fields for backward compatibility."""
        if self.INPUT_DAFAULT_MAX_CHARACTERS is not None:
            self.INPUT_DEFAULT_MAX_CHARACTERS = self.INPUT_DAFAULT_MAX_CHARACTERS
        else:
            self.INPUT_DAFAULT_MAX_CHARACTERS = self.INPUT_DEFAULT_MAX_CHARACTERS

        if self.GENERATION_DAFAULT_MAX_TOKENS is not None:
            self.GENERATION_DEFAULT_MAX_TOKENS = self.GENERATION_DAFAULT_MAX_TOKENS
        else:
            self.GENERATION_DAFAULT_MAX_TOKENS = self.GENERATION_DEFAULT_MAX_TOKENS

        if self.GENERATION_DAFAULT_TEMPERATURE is not None:
            self.GENERATION_DEFAULT_TEMPERATURE = self.GENERATION_DAFAULT_TEMPERATURE
        else:
            self.GENERATION_DAFAULT_TEMPERATURE = self.GENERATION_DEFAULT_TEMPERATURE

        return self


@lru_cache()
def get_settings() -> Settings:
    """Return a cached singleton instance of application settings."""
    return Settings()
