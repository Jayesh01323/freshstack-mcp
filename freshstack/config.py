"""Configuration management for FreshStack MCP."""

import os
import logging
from pathlib import Path
from typing import Optional


class Config:
    """FreshStack runtime configuration."""

    def __init__(self):
        self.log_level_name: str = os.getenv("FRESHSTACK_LOG_LEVEL", "INFO").upper()
        self.cache_dir_str: str = os.getenv("FRESHSTACK_CACHE_DIR", ".freshstack")
        self.offline_mode: bool = os.getenv("FRESHSTACK_OFFLINE_MODE", "false").lower() in ("true", "1", "yes")
        self.gemini_api_key: Optional[str] = os.getenv("GEMINI_API_KEY")

        # Set up cache directory
        self.cache_dir = Path(self.cache_dir_str).resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.cache_dir / "freshstack.db"

        # Configure logger
        self.logger = logging.getLogger("freshstack")
        level = getattr(logging, self.log_level_name, logging.INFO)
        self.logger.setLevel(level)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)


config = Config()
logger = config.logger
