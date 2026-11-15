"""Pydantic request schemas for the ASTRA API."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.science.features import DIMENSIONS
from backend.science.profiles import PROFILES, normalize_weights


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _check_weights(v: dict[str, float] | None) -> dict[str, float] | None:
    if v is None:
        return None
    normalize_weights(v)  # raises ValueError with a clear message
    return v


class MissionCreate(Strict):
    name: str = Field(min_length=3, max_length=200)
    target_site_id: str = Field(pattern=r"^[a-z0-9-]{3,80}$")
    profile_key: str = "general_analog"
    weights: dict[str, float] | None = Field(
        default=None, description=f"Optional custom dimension weights over {list(DIMENSIONS)}")
    objectives: str = Field(default="", max_length=2000)

    @field_validator("profile_key")
    @classmethod
    def _profile(cls, v):
        if v not in PROFILES and v != "custom":
            raise ValueError(f"profile_key must be one of {sorted(PROFILES)} or 'custom'")
        return v

    @field_validator("weights")
    @classmethod
    def _weights(cls, v):
        return _check_weights(v)


class DiscoveryRunRequest(Strict):
    mission_id: int = Field(ge=1)
    weights: dict[str, float] | None = None
    candidate_ids: list[str] | None = Field(default=None, max_length=100)
    rank_by: Literal["score", "bound_low"] = "score"

    @field_validator("weights")
    @classmethod
    def _weights(cls, v):
        return _check_weights(v)


class CompareRequest(Strict):
    candidate_id: str = Field(pattern=r"^[a-z0-9-]{3,80}$")
    target_id: str = Field(pattern=r"^[a-z0-9-]{3,80}$")
    profile_key: str = "general_analog"
    weights: dict[str, float] | None = None

    @field_validator("profile_key")
    @classmethod
    def _profile(cls, v):
        if v not in PROFILES:
            raise ValueError(f"profile_key must be one of {sorted(PROFILES)}")
        return v

    @field_validator("weights")
    @classmethod
    def _weights(cls, v):
        return _check_weights(v)


class ChatTurn(Strict):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=20_000)


class ChatRequest(Strict):
    message: str = Field(min_length=1, max_length=4000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=40)
    context: dict[str, str | int | None] = Field(default_factory=dict)

    @field_validator("context")
    @classmethod
    def _ctx(cls, v):
        allowed = {"run_id", "target_id", "candidate_id", "profile_key", "mission_id"}
        bad = set(v) - allowed
        if bad:
            raise ValueError(f"Unknown context keys: {sorted(bad)}")
        return v


class ReportRequest(Strict):
    run_id: int = Field(ge=1)
    site_id: str | None = Field(default=None, pattern=r"^[a-z0-9-]{3,80}$")
