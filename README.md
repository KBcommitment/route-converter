# route-converter

Turn a navigation route planned in **Kurviger** or **Google Maps** into a link
that opens turn-by-turn navigation in **Apple Maps** — so you get native iOS
Maps + CarPlay for a route you planned elsewhere.

## The problem

You plan a car/motorcycle trip in Google Maps or Kurviger, but you want to ride
it with native iOS Maps and Apple CarPlay. Apple Maps **can't import a route**.

## The approach

Extract the route's checkpoints from a file or link and build an Apple Maps
**unified directions URL** (iOS 18.4+), which supports multiple stops:

```
https://maps.apple.com/directions?source=<lat,lng>&waypoint=<lat,lng>&waypoint=<lat,lng>&destination=<lat,lng>&mode=driving
```

Open that link on your iPhone → it launches Apple Maps → tap **Go** →
CarPlay picks it up.

> **Requires iOS 18.4+ / recent macOS.** The unified Maps URL is the first Apple
> Maps URL scheme to support multi-stop routes (`waypoint=`). The older
> `?saddr=&daddr=&dirflg=` scheme handled a single destination only, and
> `daddr=lat,lng` regressed on iOS 18.4+.

### The link has to start navigation itself

A plain directions URL only opens a route **preview**. You then have to start
navigation from the Maps UI — and that is exactly where a multi-stop route gets
stuck: the preview offers a **Steps** button (the written turn list), and
starting it on CarPlay reports *"Directions Not Available — Turn-by-turn
directions are not available to this destination."*

The fix is the `start` parameter, which tells Maps to begin turn-by-turn on its
own. The generated link carries `start=0`, so opening it goes straight into
navigation. Use `--no-start` if you'd rather preview the route first.

> Verified end-to-end: `start=0` starts turn-by-turn on the full 14-stop route
> in the iOS 26.2 Simulator, on a real iPhone 11, and in a real CarPlay session
> (Apple's CarPlay Simulator, which speaks the same protocol as a head unit) —
> Maps' log shows `CPRouteGuidance … RouteGuidanceState: Active`. See
> [Testing CarPlay without a car](#testing-carplay-without-a-car).

The link also omits `source=`, so the origin is **your current location** and the
route's first point becomes the first stop. That matches Apple's documented
condition for offering **Go** rather than **Steps**, and means you navigate from
where you're standing. `--source-at-start` pins the origin to the route's first
point instead, for previewing a route you're not on.

### Why it's not just "start + end"

Apple caps a route at **~15 stops** and **re-routes between them** with its own
engine. For a deliberately curvy motorcycle route, handing it only the start and
destination would throw the whole route away and send you down the fastest
highway.

So the tool samples intermediate checkpoints **evenly along the route** (by
distance), always keeping your real planned waypoints (start, destination, named
vias). Even spacing holds Apple to the original corridor — no gap is left large
enough for it to wander onto a different road. More stops = closer match, up to
the 15-stop limit.

> **Reality check (see it on a real route):** 15 stops over ~85 km is a stop
> every ~6 km, and Apple re-routes *within* each gap. For a deliberately curvy
> route that hugs specific small roads, Apple will still straighten many bends.
> The result is a rough corridor, not your exact line. If you need the **exact**
> curvy route with CarPlay, use a nav app that imports the GPX directly
> (Kurviger's own Pro app has CarPlay; also Scenic, Calimoto, TomTom GO,
> Guru Maps, OsmAnd) — that isn't native Apple Maps, but it follows the route.

Tip: add `--avoid highways` to nudge Apple onto smaller roads between
checkpoints — closer to a Kurviger "avoid motorways" route.

> The result is an **approximation** constrained by Apple's stop limit and its
> own routing. It won't be bit-for-bit identical to your Kurviger line. (For an
> exact route with CarPlay, a GPX-importing nav app — e.g. Kurviger's own app,
> Scenic, Calimoto — is the only option, but that isn't native Apple Maps.)

## Web app (no install)

The same converter runs fully client-side as a static page — open it on the
iPhone itself, pick the route file, tap the link, ride:

**https://kbcommitment.github.io/route-converter/**

The page (`docs/`) is a dependency-free JS port of this package: file picker /
drag-and-drop for `.kurviger`/`.gpx`/`.kml`/`.kmz`, paste box for Kurviger and
full Google Maps links, and a `?url=` query param for deep-linking. Nothing is
uploaded — parsing happens in the browser. Only `goo.gl` short links don't work
there (CORS); paste the expanded URL instead.

The Python package remains the reference implementation: `tests/js/` holds
golden fixtures generated from its `--json` output
(`python3 tests/js/gen_fixtures.py`), and `node --test tests/js/` checks the JS
port against them.

### Share-sheet integration (iOS Shortcut)

iOS has no Web Share Target, so a web page can never appear in the share sheet
directly. The bridge is a Shortcut (share-sheet enabled, input: Files):

```
Receive Files from Share Sheet
Base64 Encode        (Shortcut Input)
Copy to Clipboard    (Base64 Encoded)
Open URLs            (https://…/route-converter/#paste)
```

Then: export in Kurviger → Share → the Shortcut → tap **📋 Paste shared
route** on the page → done. To skip the iOS paste-permission bubble:
Settings → Apps → Safari → *Paste from Other Apps* → Allow.

Why the clipboard and not the URL: iOS re-parses URLs during app→browser
handoff and mangles large fragments — a 34 KB route fragment arrives either
truncated at its first `=` or stripped entirely (measured on iOS 26). Query
strings would reach the server (and its logs), which this page's
privacy design forbids. The clipboard has neither problem; the one tap it
costs is WebKit's user-gesture requirement for clipboard reads. Small
payloads in `#<base64>` fragments do work for links opened *within* Safari.

## Install (CLI)

No dependencies required (Python 3.9+). Run it straight from the repo:

```bash
python3 -m route_converter <route-file-or-link> [options]
```

Optionally install it as a `route2maps` command:

```bash
pip install -e .            # adds the `route2maps` CLI
pip install -e ".[qr]"      # also enables --qr (scannable QR codes)
```

## Usage

```bash
# Kurviger native export (best — carries the full curvy geometry)
python3 -m route_converter "sample/Aandalsnes - Trollstigen - Valldal.kurviger"

# GPX / KML / KMZ files
python3 -m route_converter trip.gpx
python3 -m route_converter route.kml

# Tune stops, mode, road avoidance
python3 -m route_converter trip.gpx --max-stops 12 --avoid highways
python3 -m route_converter trip.gpx --strategy even     # even spacing, no detour bias
python3 -m route_converter trip.gpx --no-start          # preview instead of navigating

# Get it onto the phone
python3 -m route_converter trip.gpx --qr                # scannable QR (needs qrcode)
python3 -m route_converter trip.gpx --open              # open locally (macOS)
python3 -m route_converter trip.gpx --json              # machine-readable
```

### Options

| Option              | Description                                                       |
| ------------------- | ----------------------------------------------------------------- |
| `--max-stops N`     | Max stops Apple sees, incl. your current location (caps at ~15; default: 15). |
| `--mode`            | `drive` (default), `walk`, `transit`, `cycle`. Multi-stop is driving only. |
| `--avoid`           | Comma-separated: `tolls,highways,busy-roads,stairs`.              |
| `--strategy`        | `hybrid` (default, stops on detour apexes) or `even` (even spacing). |
| `--start SECONDS`   | Begin turn-by-turn after N seconds (default: 0, immediately).     |
| `--no-start`        | Open a preview instead of navigating — the mode that fails on CarPlay. |
| `--source-at-start` | Pin the origin to the route's first point instead of your location. |
| `--scheme`          | `https` (universal link, default) or `maps` (`maps://` app scheme). |
| `--json`            | Emit structured JSON.                                             |
| `--qr`              | Print a scannable QR code of the link (needs `qrcode`).           |
| `--open`            | Open the link locally with macOS `open`.                          |

## Supported inputs

| Format                  | Notes                                                       |
| ----------------------- | ----------------------------------------------------------- |
| `.kurviger`             | **Best.** Native Kurviger JSON — full road geometry + waypoints. Handles GraphHopper 3D (elevation) polyline encoding. |
| `.gpx`                  | Routes (`rte`), tracks (`trk`), and waypoints (`wpt`).      |
| `.kml` / `.kmz`         | Google Earth / Google My Maps exports.                     |
| Kurviger link           | Best-effort; prefer a `.kurviger`/GPX export.              |
| Google Maps link        | Best-effort; prefer a GPX/KML export.                      |

## Project layout

```
route_converter/
  parsers/        kurviger (+ polyline decode), gpx, kml, google-maps links
  simplify.py     checkpoint reduction (hybrid deviation-based / even spacing)
  apple_maps.py   unified Apple Maps directions URL builder
  cli.py          command-line interface
tests/            unittest suite (run: python3 -m unittest)
tests/js/         golden parity tests for the JS port (run: node --test tests/js/)
docs/             the static web app (GitHub Pages): index.html + converter.js
sample/           synthetic sample route, outbound + return (make_samples.py regenerates)
links/            generated Apple Maps URLs for the sample route, one per file
.claude/skills/   "route-to-apple-maps" skill wrapping the CLI
```

## Tests

```bash
python3 -m unittest discover -s tests -v   # Python reference
node --test tests/js/test_converter.mjs    # JS port vs golden fixtures
```

## Testing CarPlay without a car

How the `start=0` behavior was verified, and what does / doesn't work — so the
next debugging session doesn't rediscover it.

**The Xcode iOS Simulator can test the phone side only.**

```bash
xcrun simctl location <device> set 62.567200,7.687500    # stand at the start
xcrun simctl privacy <device> grant location-always com.apple.Maps
xcrun simctl openurl <device> "$(cat links/aandalsnes-to-valldal.txt)"
xcrun simctl io <device> screenshot nav.png              # see the result
```

Its CarPlay display (`I/O → External Displays → CarPlay`) is useless for this:
that display **ships without Apple Maps** — it exists for testing third-party
CarPlay apps, and no setting adds Maps to it.

**Real CarPlay testing needs Apple's standalone CarPlay Simulator** (in
[Additional Tools for Xcode](https://developer.apple.com/download/all/),
`Hardware/CarPlay Simulator.app`). Plug a real iPhone in over USB and the Mac
window becomes a head unit speaking the genuine CarPlay protocol, running the
phone's actual Maps CarPlay UI — the *"Directions Not Available"* failure and
its fix both reproduce there, at a desk.

**Watching Maps' own verdict** (`brew install libimobiledevice`):

```bash
idevicesyslog -u <udid> | grep -E "CPRouteGuidance|RouteGuidanceState|CarGuidanceCard"
```

Active CarPlay navigation shows `Updating CPRouteGuidance` and
`RouteGuidanceState: Active`; the guidance cards log as
`CarGuidanceCardViewController`.

Gotchas that cost real time:

- **Charge-only Lightning cables** power the phone but have no data lines — the
  Mac sees nothing at all. The tell: no "Trust This Computer" prompt on plug-in.
  Check enumeration with `ioreg -p IOUSB -w0`.
- `idevicesyslog` over Wi-Fi (`-n`) is heavily throttled and drops most lines;
  use the cable for captures. Its `-p` process filter can silently match
  nothing — capture unfiltered and grep afterwards.
