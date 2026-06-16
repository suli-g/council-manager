from pathlib import Path
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

    # AI Config
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"


    @property
    def db_path(self) -> Path:
        agents_dir = self.workspace_dir / ".agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        return agents_dir / self.db_file

settings = Settings()
