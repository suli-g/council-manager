from pathlib import Path
from pydantic import Field, AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Base workspace directory, defaults to current directory
    workspace_dir: Path = Path(".").resolve()
    db_file: str = "governance.db"
    database_dir: Path | None = Field(
        default=None,
        validation_alias=AliasChoices("council_database_dir", "database_dir", "db_dir")
    )
    council_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("council_api_key", "api_key")
    )
    debug: bool = False

    # AI Config
    gemini_api_key: str | None = None
    gemini_model: str = Field(
        default="gemini-3.5-flash",
        validation_alias=AliasChoices("llm_model", "gemini_model", "ollama_model")
    )
    llm_provider: str = "google"
    llm_api_base: str | None = None
    llm_api_key: str | None = None

    @property
    def resolved_database_dir(self) -> Path:
        if self.database_dir is not None:
            return self.database_dir.resolve()
        # Default to user home directory under .council_manager/databases (cross-platform)
        return (Path.home() / ".council_manager" / "databases").resolve()

    @property
    def db_path(self) -> Path:
        db_dir = self.resolved_database_dir / get_workspace_slug(self.workspace_dir)
        db_dir.mkdir(parents=True, exist_ok=True)
        return db_dir / self.db_file

def get_workspace_slug(workspace_path: Path) -> str:
    import re
    import hashlib
    path_str = str(workspace_path.resolve()).lower()
    slug = re.sub(r'[^a-z0-9]', '_', path_str)
    slug = re.sub(r'_+', '_', slug).strip('_')
    path_hash = hashlib.md5(path_str.encode('utf-8')).hexdigest()[:8]
    return f"{slug}_{path_hash}"

settings = Settings()

