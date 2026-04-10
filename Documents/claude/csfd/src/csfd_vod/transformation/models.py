"""Data models for VOD titles with Pydantic validation."""

from datetime import datetime, date, timezone
from typing import Optional
from pydantic import BaseModel, Field, field_validator, ConfigDict


class VODTitle(BaseModel):
    """Validated VOD title model."""

    url_id: str = Field(..., description="Unique identifier (csfd.cz URL)")
    title: str = Field(..., description="Title name")
    year: Optional[int] = Field(None, description="Release year (1890–2030)")
    director: Optional[str] = Field(None, description="Directors (comma-separated)")
    actors: Optional[str] = Field(None, description="Actors (comma-separated)")
    genres: Optional[str] = Field(None, description="Genres (forward-slash separated)")
    countries: Optional[str] = Field(None, description="Countries (forward-slash separated)")
    vod_platforms: Optional[str] = Field(None, description="VOD platforms (comma-separated)")
    link: str = Field(..., description="Full csfd.cz URL")
    date_added: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When added to VOD")

    # New fields from parser rewrite (2026-04-10)
    title_en: Optional[str] = Field(None, description="English/original title")
    plot: Optional[str] = Field(None, description="Film synopsis/description")
    rating: Optional[int] = Field(None, description="CSFD rating 0-100, NULL if unrated")
    image_url: Optional[str] = Field(None, description="Poster image URL")
    title_type: Optional[str] = Field(None, description="'film', 'serial', 'seria', 'epizoda'")
    parent_url: Optional[str] = Field(None, description="Parent film/serial URL for child titles")
    script: Optional[str] = Field(None, description="Screenwriters (comma-separated)")
    camera: Optional[str] = Field(None, description="Cinematographers (comma-separated)")
    music: Optional[str] = Field(None, description="Composers (comma-separated)")
    tags: Optional[str] = Field(None, description="User tags (comma-separated)")
    reviews: Optional[str] = Field(None, description="JSON string [{author, text, stars}] — loaded into dim_reviews, not stored in fact_titles")
    vod_date: Optional[date] = Field(None, description="VOD availability date from list page")
    distributor: Optional[str] = Field(None, description="VOD distributor from list page")
    premiere_detail: Optional[str] = Field(None, description="Raw 'Na VOD od...' text")
    scraped_at: Optional[datetime] = Field(None, description="When HTML was downloaded")

    @field_validator("year")
    @classmethod
    def validate_year(cls, v: Optional[int]) -> Optional[int]:
        """Validate year is in reasonable range."""
        if v is not None and (v < 1890 or v > 2030):
            raise ValueError(f"Year out of range: {v}")
        return v

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        """Validate title is not empty."""
        if not v or len(v.strip()) == 0:
            raise ValueError("Title cannot be empty")
        return v.strip()

    @field_validator("url_id")
    @classmethod
    def validate_url_id(cls, v: str) -> str:
        """Validate URL is valid."""
        if not v or not v.startswith("http"):
            raise ValueError("url_id must be a valid HTTP(S) URL")
        return v

    @field_validator("rating")
    @classmethod
    def validate_rating(cls, v: Optional[int]) -> Optional[int]:
        """Validate rating is 0-100."""
        if v is not None and (v < 0 or v > 100):
            raise ValueError(f"Rating out of range: {v}")
        return v

    model_config = ConfigDict(use_enum_values=True)


class ParsedTitle:
    """Intermediate representation during parsing."""

    def __init__(self, url: str, raw_data: dict):
        """Initialize with raw extracted data."""
        self.url = url
        self.raw_data = raw_data
        self.errors = []

    def to_vod_title(self) -> Optional[VODTitle]:
        """Convert to validated VODTitle model."""
        try:
            # Ensure mandatory fields
            if "title" not in self.raw_data or not self.raw_data["title"]:
                self.errors.append("Missing mandatory field: title")
                return None

            if "url_id" not in self.raw_data:
                self.raw_data["url_id"] = self.url

            if "link" not in self.raw_data:
                self.raw_data["link"] = self.url

            return VODTitle(**self.raw_data)

        except ValueError as e:
            self.errors.append(f"Validation error: {e}")
            return None
        except Exception as e:
            self.errors.append(f"Parsing error: {e}")
            return None
