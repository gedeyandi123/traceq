"""Normalised values a requirement or an observation states (submission schema version 1)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Range(_Model):
    """A required or tested range; either bound may be open."""

    type: Literal["range"] = "range"
    min: float | None = None
    max: float | None = None
    unit: str

    @model_validator(mode="after")
    def _bounds(self) -> Range:
        if self.min is None and self.max is None:
            raise ValueError("range needs at least one bound")
        return self


class Number(_Model):
    type: Literal["number"] = "number"
    value: float
    unit: str


class OneOf(_Model):
    type: Literal["one_of"] = "one_of"
    allowed: tuple[str, ...] = Field(min_length=1)


class Text(_Model):
    type: Literal["text"] = "text"
    value: str


class Present(_Model):
    """A feature that must exist; ``value`` is set when an observation states it."""

    type: Literal["present"] = "present"
    value: bool | None = None


Value = Annotated[Range | Number | OneOf | Text | Present, Field(discriminator="type")]
