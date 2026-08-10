import json
from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Coordinate = Annotated[float, Field(ge=0.0, le=1.0)]


class AnnotationStroke(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    width: float = Field(ge=0.0005, le=0.03)
    points: list[tuple[Coordinate, Coordinate]] = Field(min_length=1, max_length=2_000)

    @field_validator("points")
    @classmethod
    def require_distinct_points_for_lines(cls, points):
        if len(points) > 1 and all(point == points[0] for point in points[1:]):
            return [points[0]]
        return points


class AnnotationPageUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_revision: int = Field(ge=0)
    strokes: list[AnnotationStroke] = Field(max_length=500)

    @model_validator(mode="after")
    def validate_payload_size(self):
        total_points = sum(len(stroke.points) for stroke in self.strokes)
        if total_points > 25_000:
            raise ValueError("An annotation page cannot contain more than 25,000 points")
        compact = json.dumps(self.model_dump(mode="json"), separators=(",", ":"))
        if len(compact.encode("utf-8")) > 1_048_576:
            raise ValueError("Annotation payload cannot exceed 1 MiB")
        return self


class AnnotationPageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    child_id: int
    document_id: int
    page_number: int
    strokes: list[AnnotationStroke]
    revision: int
    updated_at: datetime | None = None


class AnnotationConflictResponse(BaseModel):
    message: str
    current: AnnotationPageResponse
