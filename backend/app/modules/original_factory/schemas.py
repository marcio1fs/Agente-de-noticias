from enum import Enum
from pydantic import BaseModel, Field, ConfigDict


class Category(str, Enum):
    HISTORY = "historia"
    SCIENCE = "ciencia"
    TECHNOLOGY = "tecnologia"
    SPACE = "espaco"
    HYPOTHETICAL = "hipoteses"
    FUTURE = "futuro"
    NATURE = "natureza"
    INVENTIONS = "invencoes"
    BRAIN = "cerebro"
    EVERYDAY = "cotidiano"


class TopicInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=10, max_length=300)
    category: Category
    nature: str = Field(default="FACTUAL", pattern="^(FACTUAL|HYPOTHESIS|FICTION)$")
    source_urls: list[str] = Field(default_factory=list, max_length=5)
    is_vertical: bool = True


class Claim(BaseModel):
    text: str = Field(min_length=5, max_length=1000)
    kind: str = Field(pattern="^(FACT|HYPOTHESIS|UNCERTAINTY)$")
    source_index: int | None = Field(default=None, ge=0, le=4)
    evidence_quote: str = Field(default="", max_length=1500)


class Scene(BaseModel):
    narration: str = Field(min_length=5, max_length=1200)
    visual: str = Field(min_length=5, max_length=300)
    illustrative: bool = True


class OriginalDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=10, max_length=100)
    description: str = Field(min_length=30, max_length=2000)
    short_script: str = Field(min_length=100, max_length=1200)
    long_script: str = Field(min_length=300, max_length=6000)
    claims: list[Claim] = Field(min_length=1, max_length=20)
    scenes: list[Scene] = Field(min_length=2, max_length=12)
    hashtags: list[str] = Field(min_length=1, max_length=8)
    thumbnail_text: str = Field(min_length=3, max_length=70)
    uncertainties: list[str] = Field(default_factory=list, max_length=10)


class Approval(BaseModel):
    reviewer: str = Field(min_length=3, max_length=100)
    facts_checked: bool
    rights_checked: bool
    script_reviewed: bool
