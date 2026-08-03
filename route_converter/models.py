from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Checkpoint:
    """A single point along a route.

    ``significant`` marks a point the user explicitly chose — a planned
    waypoint / named stop — as opposed to dense path geometry that only
    describes the *shape* of the route. Significant points are always kept
    when a route is reduced down to Apple Maps' stop limit.
    """

    lat: float
    lon: float
    name: Optional[str] = None
    significant: bool = False


@dataclass
class Route:
    """An ordered list of checkpoints plus some metadata."""

    checkpoints: List[Checkpoint]
    name: Optional[str] = None
    source_format: str = ""

    def __post_init__(self) -> None:
        if not self.checkpoints:
            raise ValueError("Route has no checkpoints")
