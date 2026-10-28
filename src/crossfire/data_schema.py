"""
All Pydantic data models for CROSSFIRE.

Structured output models (used as LangChain .with_structured_output() targets)
are marked with # [structured-output].
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# ── Enumerations 

class EffectLabel(str, Enum):
    CHALLENGING = "CHALLENGING"
    REINFORCING = "REINFORCING"
    INEFFECTIVE = "INEFFECTIVE"
    ERROR       = "ERROR"


class Confidence(str, Enum):
    HIGH   = "high"
    MEDIUM = "medium"
    LOW    = "low"


class QualityLabel(str, Enum):
    HIGH    = "High"
    MEDIUM  = "Medium"
    LOW     = "Low"
    LOWEST  = "Lowest"


# ── LLM structured output ─────────────────────────────────────────────────────

class AudienceEffectResponse(BaseModel):  # [structured-output]
    """
    Single-run LLM response: how one audience group reacts to an article.
    Used as the target schema for LangChain .with_structured_output().
    """
    label: EffectLabel = Field(
        description=(
            "Effect the article would have on this audience group: "
            "CHALLENGING (conflicts with beliefs), "
            "REINFORCING (confirms beliefs), or "
            "INEFFECTIVE (irrelevant / unconvincing)."
        )
    )
    confidence: Confidence = Field(
        description="How confident you are in this assessment: high, medium, or low."
    )
    rationale: str = Field(
        description=(
            "2–4 sentences explaining why this article would have this effect "
            "on someone with this political profile. Be specific about which "
            "arguments, values, or framing elements drive the assessment."
        )
    )


# ── Pipeline intermediate types ───────────────────────────────────────────────

class RunResult(BaseModel):
    """Result of one LLM call for a group × model cell."""
    label:      EffectLabel
    confidence: Optional[Confidence] = None
    rationale:  str = ""


class GroupEffect(BaseModel):
    """Aggregated result for one (group, model) cell after Level-1 majority rule."""
    final_label: EffectLabel
    runs:        List[RunResult]


class PairwiseQuality(BaseModel):
    """Quality score for one pair of audience groups within a model row."""
    g1:       str   # group id
    g2:       str   # group id
    quality:  QualityLabel
    is_worst: bool = False


class ModelResult(BaseModel):
    """Full result for one LLM model row: group effects + pairwise + overall quality."""
    model:            str
    model_label:      str
    configured:       bool
    group_effects:    Dict[str, GroupEffect]
    pairwise_quality: List[PairwiseQuality] = []
    overall_quality:  Optional[QualityLabel] = None


# ── Article / input ───────────────────────────────────────────────────────────

class ArticleInput(BaseModel):
    """Validated article payload sent from the frontend."""
    title:  str = ""
    author: str = ""
    date:   str = ""
    url:    str = ""
    source: str = ""
    domain: str = ""
    body:   str


class AnalyzeRequest(BaseModel):
    """Full /analyze POST body."""
    article:   ArticleInput
    group_ids: List[str] = Field(min_length=2)
    models:    List[str] = Field(default_factory=list)
