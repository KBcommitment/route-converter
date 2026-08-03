"""route_converter — turn navigation routes into Apple Maps (iOS / CarPlay) links.

Problem: routes planned in Kurviger or Google Maps cannot be imported directly
into Apple Maps. This package extracts a route's checkpoints from a file or link
and builds a ``maps.apple.com`` URL that opens turn-by-turn navigation on iOS.
"""
from .models import Checkpoint, Route
from .parsers import parse_source
from .simplify import reduce_checkpoints
from .apple_maps import build_url

__version__ = "0.1.0"
__all__ = [
    "Checkpoint",
    "Route",
    "parse_source",
    "reduce_checkpoints",
    "build_url",
    "__version__",
]
