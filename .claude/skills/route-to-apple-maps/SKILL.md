---
name: route-to-apple-maps
description: Convert a planned navigation route (Kurviger .kurviger, GPX, KML/KMZ file, or a Kurviger/Google Maps link) into an Apple Maps directions URL that opens turn-by-turn navigation on iOS / CarPlay. Use when the user wants to take a route planned in Kurviger or Google Maps and open it in native Apple Maps, mentions a .kurviger/.gpx/.kml route, an "apple maps link", "carplay", or "extract checkpoints from a route".
---

# Route → Apple Maps

Convert a route **file or link** into an Apple Maps directions URL.

## Why

Apple Maps / CarPlay can't import a planned route. This extracts the route's
checkpoints and builds a unified Apple Maps URL
(`https://maps.apple.com/directions?...`, iOS 18.4+) which supports multi-stop
routes via repeated `waypoint=` params. Apple caps a route at ~15 stops and
re-routes between them, so the tool samples points **along the route** — always
keeping the real planned waypoints — so Apple is held to the original corridor
instead of snapping start→end onto the fastest highway. Note the hard ceiling:
~15 stops over a long route means Apple still re-routes within each gap, so a
curvy route is approximated, not traced exactly.

**The link must start navigation itself.** A plain directions URL only opens a
preview, and starting a multi-stop route by hand is what fails: Maps offers a
"Steps" list instead of "Go", and CarPlay reports "Directions Not Available". So
the link carries `start=0`, which tells Maps to begin turn-by-turn on open
(verified in the iOS 26.2 Simulator on a 14-stop route). It also omits `source=`,
so the origin is the rider's current location — Apple's documented condition for
offering "Go". `--no-start` and `--source-at-start` opt out of each.

## How to run

From the project root, no install needed:

```bash
python3 -m route_converter "<path-or-link>" [options]
```

Options:

- `--max-stops N` — stops Apple sees, incl. the rider's current location (caps
  ~15; default 15). Lower it for fewer stops.
- `--mode drive|walk|transit|cycle` (default `drive`; multi-stop is driving only)
- `--avoid tolls,highways,busy-roads,stairs` — e.g. `--avoid highways` keeps a
  curvy ride off the autobahn (mirrors Kurviger "avoid motorways").
- `--strategy hybrid|even` — `hybrid` (default) puts stops on route deviations
  (detours, bends); `even` spreads them evenly by distance.
- `--start SECONDS` — begin turn-by-turn after N seconds (default 0).
- `--no-start` — open a preview instead of navigating (the failing mode).
- `--source-at-start` — pin the origin to the route's first point instead of the
  rider's location.
- `--scheme https|maps` — `https` universal link (default) or `maps://` scheme.
- `--json` — structured output (name, counts, stops, url).
- `--qr` — print a scannable QR (needs `pip install qrcode`).
- `--open` — open the link locally (macOS).

## Inputs

- **`.kurviger`** (native Kurviger JSON export) — best; carries the full curvy
  geometry and the planned waypoints.
- **`.gpx`** — routes / tracks / waypoints.
- **`.kml` / `.kmz`** — Google Earth / Google My Maps.
- **Kurviger / Google Maps link** — best-effort; if it fails, ask the user to
  export the route as a `.kurviger` or GPX/KML file instead.

## What to report back

1. Print the resulting `https://maps.apple.com/directions?...` URL.
2. Tell the user to open it on their iPhone (**iOS 18.4+**) **while at the
   route's start** — navigation begins on its own, and CarPlay picks it up. If
   they open it from elsewhere, Maps routes them to the first stop first.
3. State how many checkpoints were kept vs found, and note the path is an
   approximation (Apple re-routes between stops, ~15-stop cap). If they want a
   closer match, suggest raising `--max-stops` or adding `--avoid highways`.

## Example

```bash
python3 -m route_converter "sample/Aandalsnes - Trollstigen - Valldal.kurviger" --avoid highways
```
