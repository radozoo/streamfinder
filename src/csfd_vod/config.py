"""Configuration management for the pipeline."""

import json
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class ScrapeConfig:
    """Configuration for scraping."""
    rate_limit_delay_ms: int = 1000  # Increased from 500ms to respect server limits
    rate_limit_jitter_ms: int = 300   # Increased from 200ms for more variation
    request_timeout_sec: int = 10
    max_retries: int = 3
    user_agents: List[str] = None

    def __post_init__(self):
        if self.user_agents is None:
            self.user_agents = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36",
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36",
            ]


@dataclass
class DatabaseConfig:
    """Configuration for PostgreSQL database."""
    host: str = "localhost"
    port: int = 5432
    database: str = "csfd_vod"
    user: str = "csfd_user"
    password: str = ""
    pool_size: int = 5
    max_overflow: int = 2

    @property
    def connection_string(self) -> str:
        """Get SQLAlchemy connection string."""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


@dataclass
class PipelineConfig:
    """Overall pipeline configuration."""
    scrape: ScrapeConfig
    database: DatabaseConfig
    selectors_path: str = "config/selectors.json"
    log_level: str = "INFO"
    cache_dir: str = "cache"


def load_selectors(path: str) -> Dict:
    """Load CSS selectors from JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_config_from_env() -> PipelineConfig:
    """Load configuration from environment variables."""
    from dotenv import load_dotenv
    load_dotenv()

    db_config = DatabaseConfig(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        database=os.getenv("DB_NAME", "csfd_vod"),
        user=os.getenv("DB_USER", "csfd_user"),
        password=os.getenv("DB_PASSWORD", ""),
    )

    scrape_config = ScrapeConfig(
        rate_limit_delay_ms=int(os.getenv("SCRAPE_DELAY_MS", 500)),
        rate_limit_jitter_ms=int(os.getenv("SCRAPE_JITTER_MS", 200)),
    )

    return PipelineConfig(
        scrape=scrape_config,
        database=db_config,
        selectors_path=os.getenv("SELECTORS_PATH", "config/selectors.json"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        cache_dir=os.getenv("CACHE_DIR", "cache"),
    )
