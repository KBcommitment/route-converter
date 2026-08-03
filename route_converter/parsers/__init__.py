"""Route parsers and the :func:`parse_source` dispatcher."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from ..models import Route
from .gpx import parse_gpx
from .kml import parse_kml, parse_kmz
from .kurviger import parse_kurviger_file, parse_kurviger_link
from .links import parse_google_maps_link

__all__ = [
    "parse_source",
    "parse_gpx",
    "parse_kml",
    "parse_kmz",
    "parse_kurviger_file",
    "parse_kurviger_link",
    "parse_google_maps_link",
]

_URL_RE = re.compile(r"https?://\S+")


def _parse_link(url: str, name: Optional[str] = None) -> Route:
    host = urlparse(url).netloc.lower()
    if "kurviger" in host:
        return parse_kurviger_link(url, name=name)
    if "google" in host or "goo.gl" in host:
        return parse_google_maps_link(url, name=name)
    raise ValueError(
        f"Unsupported link host: {host!r}. Supported links: kurviger.de, "
        "google maps."
    )


def _parse_links_text(text: str, name: Optional[str] = None) -> Route:
    """Parse a text file of share links, preferring the most complete one."""
    urls = [u.rstrip(").,'\"") for u in _URL_RE.findall(text)]
    if not urls:
        raise ValueError("File has no http(s) URL and no recognized route format")

    fallback: Optional[Route] = None
    last_error: Optional[Exception] = None
    for url in urls:
        try:
            route = _parse_link(url, name=name)
        except (ValueError, OSError) as exc:
            last_error = exc
            continue
        if len(route.checkpoints) >= 2:
            return route
        fallback = fallback or route
    if fallback is not None:
        return fallback
    raise last_error or ValueError("Could not parse any link in the file")


def parse_source(source: str) -> Route:
    """Parse a file path or URL into a :class:`Route`."""
    s = source.strip()

    if s.startswith("http://") or s.startswith("https://"):
        return _parse_link(s)

    path = Path(s).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"No such file: {path}")

    ext = path.suffix.lower()
    name = path.stem

    if ext == ".kmz":
        return parse_kmz(path.read_bytes(), name=name)

    text = path.read_text(encoding="utf-8", errors="replace")
    head = text[:500].lstrip()

    # A plain file containing share link(s), e.g. an exported Google Maps URL.
    if head.startswith("http://") or head.startswith("https://"):
        return _parse_links_text(text, name=name)

    if ext == ".kurviger" or (head.startswith("{") and '"paths"' in text[:2000]):
        return parse_kurviger_file(text, name=name)
    if ext == ".gpx" or "<gpx" in head:
        return parse_gpx(text, name=name)
    if ext == ".kml" or "<kml" in head:
        return parse_kml(text, name=name)

    raise ValueError(
        f"Unrecognized route format for {path.name!r}. "
        "Supported: .kurviger, .gpx, .kml, .kmz, or a file of links"
    )
