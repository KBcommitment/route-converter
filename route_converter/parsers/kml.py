"""Parse KML / KMZ files (Google Earth, Google My Maps exports).

A ``<LineString>`` is treated as the ordered route geometry; ``<Placemark>``
``<Point>`` elements are treated as named, significant stops. KMZ is a zip
archive whose main document is conventionally ``doc.kml``.
"""
from __future__ import annotations

import io
import xml.etree.ElementTree as ET
import zipfile
from typing import List, Optional

from ..models import Checkpoint, Route


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _findall(root, name: str):
    return [e for e in root.iter() if _local(e.tag) == name]


def _text_child(el, name: str) -> Optional[str]:
    for c in el:
        if _local(c.tag) == name:
            return (c.text or "").strip() or None
    return None


def _parse_coords(text: str):
    """KML coordinates: whitespace-separated ``lon,lat[,alt]`` tuples."""
    out = []
    for tok in text.split():
        parts = tok.split(",")
        if len(parts) >= 2:
            out.append((float(parts[1]), float(parts[0])))  # -> (lat, lon)
    return out


def parse_kml(text: str, name: Optional[str] = None) -> Route:
    root = ET.fromstring(text)

    line_coords = []
    for ls in _findall(root, "LineString"):
        c = _text_child(ls, "coordinates")
        if c:
            line_coords.extend(_parse_coords(c))

    placemark_points: List[Checkpoint] = []
    for pm in _findall(root, "Placemark"):
        nm = _text_child(pm, "name")
        for pt in _findall(pm, "Point"):
            c = _text_child(pt, "coordinates")
            if c:
                for lat, lon in _parse_coords(c):
                    placemark_points.append(
                        Checkpoint(lat, lon, name=nm, significant=True)
                    )

    if line_coords:
        checkpoints = [Checkpoint(lat, lon) for lat, lon in line_coords]
        for pc in placemark_points:
            i = min(
                range(len(checkpoints)),
                key=lambda k: (checkpoints[k].lat - pc.lat) ** 2
                + (checkpoints[k].lon - pc.lon) ** 2,
            )
            checkpoints[i].significant = True
            checkpoints[i].name = pc.name or checkpoints[i].name
    elif placemark_points:
        checkpoints = placemark_points
    else:
        raise ValueError("KML contains no LineString or Point geometry")

    checkpoints[0].significant = True
    checkpoints[-1].significant = True

    doc_name = name
    if not doc_name:
        docs = _findall(root, "Document")
        if docs:
            doc_name = _text_child(docs[0], "name")

    return Route(checkpoints=checkpoints, name=doc_name, source_format="kml")


def parse_kmz(data: bytes, name: Optional[str] = None) -> Route:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        kml_names = [n for n in z.namelist() if n.lower().endswith(".kml")]
        if not kml_names:
            raise ValueError("KMZ archive contains no .kml file")
        target = "doc.kml" if "doc.kml" in kml_names else kml_names[0]
        text = z.read(target).decode("utf-8", errors="replace")
    return parse_kml(text, name=name)
