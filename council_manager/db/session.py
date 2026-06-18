from pathlib import Path
from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from council_manager.db.models import Base
from council_manager.config import settings

class DatabaseManager:
    def __init__(self):
        self._engines = {}
        self._sessionmakers = {}

    def get_db_path(self, workspace_dir: str | Path) -> Path:
        from council_manager.config import get_workspace_slug
        workspace_path = Path(workspace_dir).resolve()
        db_dir = settings.resolved_database_dir / get_workspace_slug(workspace_path)
        db_dir.mkdir(parents=True, exist_ok=True)
        return db_dir / settings.db_file

    def get_engine(self, workspace_dir: str | Path):
        db_path = self.get_db_path(workspace_dir)
        db_url = f"sqlite:///{db_path}"
        
        if db_url not in self._engines:
            # Create engine with check_same_thread=False for async safety
            engine = create_engine(db_url, connect_args={"check_same_thread": False})

            # Register sqlite pragma event listener for connection
            @event.listens_for(engine, "connect")
            def set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA journal_mode=WAL")  # Enable WAL mode for concurrent write safety
                cursor.close()

            # Initialize database schemas
            Base.metadata.create_all(engine)
            
            self._engines[db_url] = engine
            self._sessionmakers[db_url] = sessionmaker(
                bind=engine, 
                autoflush=False, 
                autocommit=False
            )
            
        return self._engines[db_url]

    def get_session(self, workspace_dir: str | Path) -> Session:
        """Get a raw Session instance for the target workspace."""
        self.get_engine(workspace_dir)  # Ensure engine and tables are initialized
        db_path = self.get_db_path(workspace_dir)
        db_url = f"sqlite:///{db_path}"
        return self._sessionmakers[db_url]()

    def session_scope(self, workspace_dir: str | Path) -> Generator[Session, None, None]:
        """Context manager for safe session handling."""
        session = self.get_session(workspace_dir)
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def close_all(self):
        """Dispose all engines and clear caches. Releases file locks on Windows."""
        for engine in self._engines.values():
            engine.dispose()
        self._engines.clear()
        self._sessionmakers.clear()

db_manager = DatabaseManager()

