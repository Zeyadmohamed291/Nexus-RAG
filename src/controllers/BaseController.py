import os
import random
import string
from pathlib import Path
from typing import Optional
from helpers.config import get_settings, Settings


class BaseController:
    """
    Base controller providing shared file system paths, configuration access,
    and common utility functions for domain controllers.
    """

    def __init__(self) -> None:
        self.app_settings: Settings = get_settings()
        
        self.base_dir: Path = Path(__file__).resolve().parent.parent
        self.files_dir: Path = self.base_dir / "assets" / "files"
        self.database_dir: Path = self.base_dir / "assets" / "database"

        # Ensure base storage directories exist
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self.database_dir.mkdir(parents=True, exist_ok=True)

    def generate_random_string(self, length: int = 12) -> str:
        """Generate a cryptographically secure random alphanumeric string."""
        chars = string.ascii_lowercase + string.digits
        return "".join(random.choices(chars, k=length))

    def get_database_path(self, db_name: str) -> str:
        """Ensure and return the absolute path to a named database directory."""
        db_path = self.database_dir / db_name
        db_path.mkdir(parents=True, exist_ok=True)
        return str(db_path)