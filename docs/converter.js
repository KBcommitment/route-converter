/* Route → Apple Maps: browser port of the Python `route_converter` package.
 *
 * Pure ES module, no dependencies. The Python package stays the reference
 * implementation; tests/js/ holds golden fixtures generated from its --json
 * output, and this module must produce the same URLs.
 *
 * Differences from the Python CLI, all forced by the static-page setting:
 * - goo.gl short links can't be expanded (CORS) — the caller gets an error
 *   telling the user to paste the expanded google.com/maps/dir/... URL.
 * - KMZ decompression uses the browser's DecompressionStream, so parsing
 *   bytes is async.
 */

// ---------------------------------------------------------------- models ---

export function checkpoint(lat, lon, name = null, significant = false) {
  return { lat, lon, name, significant };
}

// ------------------------------------------------------ polyline decoding ---

/** Decode a GraphHopper / Google encoded polyline into [lat, lon] pairs.
 *  With elevation=true the encoding is 3-D; the third value is consumed so
 *  coordinates stay aligned, but not returned. */
export function decodePolyline(encoded, withElevation = false, precision = 1e5) {
  const dims = withElevation ? 3 : 2;
  const coords = [];
  let i = 0;
  let lat = 0, lon = 0, ele = 0;
  const n = encoded.length;

  while (i < n) {
    const deltas = [0, 0, 0];
    for (let d = 0; d < dims; d++) {
      let shift = 0, result = 0, b;
      do {
        b = encoded.charCodeAt(i++) - 63;
        result |= (b & 0x1f) << shift;
        shift += 5;
      } while (b >= 0x20);
      deltas[d] = result & 1 ? ~(result >> 1) : result >> 1;
    }
    lat += deltas[0];
    lon += deltas[1];
    ele += deltas[2];
    coords.push([lat / precision, lon / precision]);
  }
  return coords;
}

// ------------------------------------------------------------- XML helper ---

/* parseGpx/parseKml walk a minimal element tree: {name, attrs, children,
 * text}. In the browser it's built with DOMParser; in Node (tests) a small
 * fallback parser handles the machine-generated XML these formats are. */

function domToTree(el) {
  const node = {
    name: el.localName,
    attrs: {},
    children: [],
    text: "",
  };
  for (const a of el.attributes) node.attrs[a.localName] = a.value;
  for (const c of el.childNodes) {
    if (c.nodeType === 1) node.children.push(domToTree(c));
    else if (c.nodeType === 3 || c.nodeType === 4) node.text += c.nodeValue;
  }
  return node;
}

const XML_ENTITIES = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'" };

function decodeEntities(s) {
  return s.replace(/&(#x?[0-9a-fA-F]+|[a-zA-Z]+);/g, (m, e) => {
    if (e[0] === "#") {
      const code = e[1] === "x" || e[1] === "X" ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10);
      return Number.isNaN(code) ? m : String.fromCodePoint(code);
    }
    return XML_ENTITIES[e] ?? m;
  });
}

/** Tiny XML parser for the Node test environment (no DOMParser there).
 *  Handles well-formed elements, attributes, text, CDATA, comments, and
 *  processing instructions — enough for GPX/KML exports. */
function parseXmlFallback(text) {
  const root = { name: "#root", attrs: {}, children: [], text: "" };
  const stack = [root];
  const tagRe = /<!\[CDATA\[([\s\S]*?)\]\]>|<!--[\s\S]*?-->|<!DOCTYPE[^>]*>|<\?[\s\S]*?\?>|<\/([^\s>]+)\s*>|<([^\s/>]+)((?:\s+[^\s=]+\s*=\s*(?:"[^"]*"|'[^']*'))*)\s*(\/?)>|([^<]+)/g;
  const attrRe = /([^\s=]+)\s*=\s*(?:"([^"]*)"|'([^']*)')/g;
  let m;
  while ((m = tagRe.exec(text)) !== null) {
    const [, cdata, closeName, openName, attrText, selfClose, textRun] = m;
    const top = stack[stack.length - 1];
    if (cdata !== undefined) {
      top.text += cdata;
    } else if (textRun !== undefined) {
      top.text += decodeEntities(textRun);
    } else if (closeName !== undefined) {
      if (stack.length > 1) stack.pop();
    } else if (openName !== undefined) {
      const node = {
        name: openName.split(":").pop(),
        attrs: {},
        children: [],
        text: "",
      };
      let a;
      while ((a = attrRe.exec(attrText || "")) !== null) {
        node.attrs[a[1].split(":").pop()] = decodeEntities(a[2] ?? a[3] ?? "");
      }
      top.children.push(node);
      if (!selfClose) stack.push(node);
    }
  }
  if (!root.children.length) throw new Error("Not valid XML");
  return root.children[0];
}

function parseXml(text) {
  if (typeof DOMParser !== "undefined") {
    const doc = new DOMParser().parseFromString(text, "application/xml");
    const err = doc.querySelector("parsererror");
    if (err) throw new Error("Not valid XML: " + err.textContent.slice(0, 120));
    return domToTree(doc.documentElement);
  }
  return parseXmlFallback(text);
}

function* iterTree(node) {
  yield node;
  for (const c of node.children) yield* iterTree(c);
}

function findAll(root, name) {
  const out = [];
  for (const n of iterTree(root)) if (n.name === name) out.push(n);
  return out;
}

function textChild(el, name) {
  for (const c of el.children) {
    if (c.name === name) {
      const t = c.text.trim();
      return t || null;
    }
  }
  return null;
}

// ---------------------------------------------------------------- parsers ---

function nearestIndex(points, lat, lon) {
  let bestI = 0, bestD = Infinity;
  for (let i = 0; i < points.length; i++) {
    const d = (points[i].lat - lat) ** 2 + (points[i].lon - lon) ** 2;
    if (d < bestD) { bestD = d; bestI = i; }
  }
  return bestI;
}

/** Native .kurviger JSON: GraphHopper response with encoded geometry. */
export function parseKurviger(text, name = null) {
  const data = JSON.parse(text);
  const paths = data.paths;
  if (!paths || !paths.length) throw new Error("Not a Kurviger route file: no 'paths' found");
  const path = paths[0];

  let geometry;
  const pts = path.points;
  if (pts === undefined || pts === null) throw new Error("Kurviger path has no 'points' geometry");
  if (path.points_encoded ?? true) {
    if (typeof pts !== "string") throw new Error("points_encoded is true but 'points' is not a string");
    geometry = decodePolyline(pts, Boolean(path.elevation));
  } else {
    const coords = Array.isArray(pts) ? pts : pts.coordinates;
    geometry = coords.map((c) => [c[1], c[0]]);
  }

  const checkpoints = geometry.map(([lat, lon]) => checkpoint(lat, lon));
  for (const wp of path.waypoints || []) {
    if (wp.latitude == null || wp.longitude == null) continue;
    const i = nearestIndex(checkpoints, wp.latitude, wp.longitude);
    checkpoints[i].significant = true;
    if (wp.address) checkpoints[i].name = wp.address;
  }
  checkpoints[0].significant = true;
  checkpoints[checkpoints.length - 1].significant = true;
  return { checkpoints, name, sourceFormat: "kurviger" };
}

function gpxPoint(el) {
  const nm = textChild(el, "name");
  return checkpoint(parseFloat(el.attrs.lat), parseFloat(el.attrs.lon), nm, Boolean(nm));
}

/** GPX: prefer <rte>, then <trk>, then bare <wpt>. */
export function parseGpx(text, name = null) {
  const root = parseXml(text);
  const rtepts = findAll(root, "rtept").map(gpxPoint);
  const trkpts = findAll(root, "trkpt").map(gpxPoint);
  const wpts = findAll(root, "wpt").map(gpxPoint);

  const base = rtepts.length ? rtepts : trkpts.length ? trkpts : wpts;
  if (!base.length) throw new Error("GPX file contains no route points, track points, or waypoints");

  if (base === trkpts && wpts.length) {
    for (const w of wpts) {
      const i = nearestIndex(base, w.lat, w.lon);
      base[i].significant = true;
      base[i].name = w.name || base[i].name;
    }
  }
  base[0].significant = true;
  base[base.length - 1].significant = true;

  let routeName = name;
  if (!routeName) {
    for (const parent of ["rte", "trk", "metadata"]) {
      for (const el of findAll(root, parent)) {
        const nm = textChild(el, "name");
        if (nm) { routeName = nm; break; }
      }
      if (routeName) break;
    }
  }
  return { checkpoints: base, name: routeName ?? null, sourceFormat: "gpx" };
}

function kmlCoords(text) {
  const out = [];
  for (const tok of text.split(/\s+/)) {
    const parts = tok.split(",");
    if (parts.length >= 2) out.push([parseFloat(parts[1]), parseFloat(parts[0])]);
  }
  return out;
}

/** KML: <LineString> is the geometry, Placemark <Point>s are named stops. */
export function parseKml(text, name = null) {
  const root = parseXml(text);

  const lineCoords = [];
  for (const ls of findAll(root, "LineString")) {
    const c = textChild(ls, "coordinates");
    if (c) lineCoords.push(...kmlCoords(c));
  }

  const placemarkPoints = [];
  for (const pm of findAll(root, "Placemark")) {
    const nm = textChild(pm, "name");
    for (const pt of findAll(pm, "Point")) {
      const c = textChild(pt, "coordinates");
      if (c) for (const [lat, lon] of kmlCoords(c)) placemarkPoints.push(checkpoint(lat, lon, nm, true));
    }
  }

  let checkpoints;
  if (lineCoords.length) {
    checkpoints = lineCoords.map(([lat, lon]) => checkpoint(lat, lon));
    for (const pc of placemarkPoints) {
      const i = nearestIndex(checkpoints, pc.lat, pc.lon);
      checkpoints[i].significant = true;
      checkpoints[i].name = pc.name || checkpoints[i].name;
    }
  } else if (placemarkPoints.length) {
    checkpoints = placemarkPoints;
  } else {
    throw new Error("KML contains no LineString or Point geometry");
  }
  checkpoints[0].significant = true;
  checkpoints[checkpoints.length - 1].significant = true;

  let docName = name;
  if (!docName) {
    const docs = findAll(root, "Document");
    if (docs.length) docName = textChild(docs[0], "name");
  }
  return { checkpoints, name: docName ?? null, sourceFormat: "kml" };
}

// ------------------------------------------------------------- KMZ (zip) ---

/* Minimal ZIP reader: walk the central directory, inflate with the native
 * DecompressionStream. Handles stored (0) and deflate (8) entries — all that
 * KML tooling produces. */

async function inflateRaw(bytes) {
  const ds = new DecompressionStream("deflate-raw");
  const stream = new Blob([bytes]).stream().pipeThrough(ds);
  const buf = await new Response(stream).arrayBuffer();
  return new Uint8Array(buf);
}

async function unzip(buffer) {
  const b = new Uint8Array(buffer);
  const view = new DataView(buffer);
  // End of central directory: scan back for PK\x05\x06.
  let eocd = -1;
  for (let i = b.length - 22; i >= Math.max(0, b.length - 22 - 65535); i--) {
    if (view.getUint32(i, true) === 0x06054b50) { eocd = i; break; }
  }
  if (eocd < 0) throw new Error("Not a ZIP archive");
  const count = view.getUint16(eocd + 10, true);
  let off = view.getUint32(eocd + 16, true);

  const entries = [];
  for (let e = 0; e < count; e++) {
    if (view.getUint32(off, true) !== 0x02014b50) break;
    const method = view.getUint16(off + 10, true);
    const csize = view.getUint32(off + 20, true);
    const nameLen = view.getUint16(off + 28, true);
    const extraLen = view.getUint16(off + 30, true);
    const commentLen = view.getUint16(off + 32, true);
    const localOff = view.getUint32(off + 42, true);
    const name = new TextDecoder().decode(b.subarray(off + 46, off + 46 + nameLen));
    entries.push({ name, method, csize, localOff });
    off += 46 + nameLen + extraLen + commentLen;
  }

  return {
    names: entries.map((e) => e.name),
    async read(name) {
      const e = entries.find((x) => x.name === name);
      if (!e) throw new Error(`No ${name} in archive`);
      // Local header: sizes of name/extra fields differ from the central copy.
      const ln = view.getUint16(e.localOff + 26, true);
      const le = view.getUint16(e.localOff + 28, true);
      const start = e.localOff + 30 + ln + le;
      const raw = b.subarray(start, start + e.csize);
      if (e.method === 0) return raw;
      if (e.method === 8) return inflateRaw(raw);
      throw new Error(`Unsupported ZIP compression method ${e.method}`);
    },
  };
}

export async function parseKmz(buffer, name = null) {
  const zip = await unzip(buffer);
  const kmlNames = zip.names.filter((n) => n.toLowerCase().endsWith(".kml"));
  if (!kmlNames.length) throw new Error("KMZ archive contains no .kml file");
  const target = kmlNames.includes("doc.kml") ? "doc.kml" : kmlNames[0];
  const text = new TextDecoder("utf-8").decode(await zip.read(target));
  return parseKml(text, name);
}

// ------------------------------------------------------------------ links ---

const DIR_COORD = /^-?\d{1,3}(?:\.\d+)?,-?\d{1,3}(?:\.\d+)?$/;
const PLACE_LNGLAT = /!1d(-?\d+\.\d+)!2d(-?\d+\.\d+)/g; // (lng, lat)
const PLACE_LATLNG = /!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)/g; // (lat, lng)

/** Best-effort decode of a kurviger.de share link (point= query params). */
export function parseKurvigerLink(url, name = null) {
  const query = new URL(url).searchParams;
  const raw = [...query.getAll("point"), ...query.getAll("waypoints")];
  const coords = [];
  for (const item of raw) {
    for (const piece of item.split(";")) {
      const p = piece.trim();
      if (!p) continue;
      const [latStr, lonStr] = [p.slice(0, p.indexOf(",")), p.slice(p.indexOf(",") + 1)];
      coords.push([parseFloat(latStr), parseFloat(lonStr)]);
    }
  }
  if (!coords.length) {
    throw new Error(
      "Could not extract waypoints from this Kurviger link. Export the route " +
      "as a .kurviger or GPX file and use that instead."
    );
  }
  const checkpoints = coords.map(([lat, lon]) => checkpoint(lat, lon, null, true));
  return { checkpoints, name, sourceFormat: "kurviger-link" };
}

/** Best-effort extraction of stops from a full Google Maps directions URL.
 *  Short links (goo.gl) need an HTTP redirect a static page can't follow. */
export function parseGoogleMapsLink(url, name = null) {
  url = url.trim();
  const host = new URL(url).host.toLowerCase();
  if (host.includes("goo.gl")) {
    throw new Error(
      "Short links can't be expanded from a static page. Open the link, " +
      "let it redirect, then paste the full google.com/maps/dir/... URL."
    );
  }
  const placeCoords = [...url.matchAll(PLACE_LNGLAT)].map((m) => [parseFloat(m[2]), parseFloat(m[1])]);
  if (!placeCoords.length) {
    placeCoords.push(...[...url.matchAll(PLACE_LATLNG)].map((m) => [parseFloat(m[1]), parseFloat(m[2])]));
  }

  const path = new URL(url).pathname;
  const coords = [];
  if (path.includes("/dir/")) {
    let placeIdx = 0;
    for (const seg of path.split("/dir/")[1].split("/")) {
      const s = decodeURIComponent(seg);
      if (!s || s.startsWith("@") || s.startsWith("data=")) continue;
      if (DIR_COORD.test(s)) {
        const [lat, lon] = s.split(",");
        coords.push([parseFloat(lat), parseFloat(lon)]);
      } else if (placeIdx < placeCoords.length) {
        coords.push(placeCoords[placeIdx++]);
      }
    }
  } else {
    coords.push(...placeCoords);
  }

  if (!coords.length) {
    throw new Error(
      "Could not extract coordinates from this Google Maps link. Export the " +
      "route as GPX or KML and use that file instead."
    );
  }
  const checkpoints = coords.map(([lat, lon]) => checkpoint(lat, lon, null, true));
  return { checkpoints, name, sourceFormat: "google-maps-link" };
}

export function parseLink(url, name = null) {
  const host = new URL(url).host.toLowerCase();
  if (host.includes("kurviger")) return parseKurvigerLink(url, name);
  if (host.includes("google") || host.includes("goo.gl")) return parseGoogleMapsLink(url, name);
  throw new Error(`Unsupported link host: ${host}. Supported: kurviger.de, google maps.`);
}

// --------------------------------------------------------------- simplify ---

const STRAIGHT_EPS = 5e-5; // ~5 m in scaled degrees: below this a cell is straight

function dedupe(points, eps = 1e-6) {
  const out = [];
  for (const p of points) {
    const last = out[out.length - 1];
    if (last && Math.abs(last.lat - p.lat) < eps && Math.abs(last.lon - p.lon) < eps) {
      if (p.significant && !last.significant) last.significant = true;
      if (p.name && !last.name) last.name = p.name;
      continue;
    }
    out.push({ ...p });
  }
  return out;
}

function haversineKm(a, b) {
  const r = 6371.0;
  const la1 = (a.lat * Math.PI) / 180, lo1 = (a.lon * Math.PI) / 180;
  const la2 = (b.lat * Math.PI) / 180, lo2 = (b.lon * Math.PI) / 180;
  const h =
    Math.sin((la2 - la1) / 2) ** 2 +
    Math.cos(la1) * Math.cos(la2) * Math.sin((lo2 - lo1) / 2) ** 2;
  return 2 * r * Math.asin(Math.sqrt(h));
}

function cumulative(points) {
  const cum = [0.0];
  for (let i = 1; i < points.length; i++) cum.push(cum[i - 1] + haversineKm(points[i - 1], points[i]));
  return cum;
}

/** Apportion integer slots across segments by weight (largest remainder). */
function allocate(budget, weights) {
  const total = weights.reduce((s, w) => s + w, 0) || 1.0;
  const raw = weights.map((w) => (budget * w) / total);
  const base = raw.map(Math.floor);
  const remainder = budget - base.reduce((s, x) => s + x, 0);
  const order = raw.map((x, i) => i).sort((i, j) => raw[j] - base[j] - (raw[i] - base[i]));
  for (const i of order.slice(0, remainder)) base[i] += 1;
  return base;
}

function nearestArcIndex(cum, lo, hi, target) {
  let best = -1, bestD = Infinity;
  for (let j = lo + 1; j < hi; j++) {
    const d = Math.abs(cum[j] - target);
    if (d < bestD) { bestD = d; best = j; }
  }
  return best;
}

function bisectLeft(a, x, lo, hi) {
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (a[mid] < x) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

function idxAt(cum, arc, lo, hi) {
  const i = bisectLeft(cum, arc, lo, hi + 1);
  return Math.min(Math.max(i, lo), hi);
}

/** Perpendicular distance from p to segment a-b, in cos(lat)-scaled degrees. */
function perp(p, a, b) {
  const coslat = Math.cos((a[0] * Math.PI) / 180);
  const ax = a[1] * coslat, ay = a[0];
  const bx = b[1] * coslat, by = b[0];
  const px = p[1] * coslat, py = p[0];
  const dx = bx - ax, dy = by - ay;
  if (dx === 0 && dy === 0) return Math.hypot(px - ax, py - ay);
  const t = Math.max(0.0, Math.min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)));
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}

function placeEven(cum, a, b, k, keep) {
  const span = cum[b] - cum[a];
  for (let m = 1; m <= k; m++) {
    const j = nearestArcIndex(cum, a, b, cum[a] + (span * m) / (k + 1));
    if (j !== -1) keep.add(j);
  }
}

function placeHybrid(pts, cum, a, b, k, keep) {
  const span = cum[b] - cum[a];
  for (let c = 0; c < k; c++) {
    const lo = idxAt(cum, cum[a] + (span * c) / k, a, b);
    let hi = idxAt(cum, cum[a] + (span * (c + 1)) / k, a, b);
    if (hi <= lo) hi = Math.min(lo + 1, b);
    const chordA = [pts[lo].lat, pts[lo].lon];
    const chordB = [pts[hi].lat, pts[hi].lon];
    let best = lo, bestD = -1.0;
    for (let j = lo; j <= hi; j++) {
      const d = perp([pts[j].lat, pts[j].lon], chordA, chordB);
      if (d > bestD) { bestD = d; best = j; }
    }
    if (bestD < STRAIGHT_EPS) best = (lo + hi) >> 1; // straight cell: even spacing
    keep.add(best);
  }
}

/** Reduce to at most maxPoints checkpoints; keeps endpoints and every
 *  significant waypoint, distributes the rest by gap length. */
export function reduceCheckpoints(points, maxPoints, strategy = "hybrid") {
  const pts = dedupe(points);
  const n = pts.length;
  if (maxPoints <= 0 || n <= maxPoints) return pts;

  const cum = cumulative(pts);
  const total = cum[cum.length - 1] || 1.0;
  const mandatorySet = new Set([0, n - 1]);
  pts.forEach((p, i) => { if (p.significant) mandatorySet.add(i); });
  const mandatory = [...mandatorySet].sort((a, b) => a - b);

  // More named waypoints than budget: endpoints + an evenly spaced subset.
  if (mandatory.length >= maxPoints) {
    const keep = new Set([0, n - 1]);
    const inner = mandatory.filter((i) => i !== 0 && i !== n - 1);
    const budget = maxPoints - keep.size;
    for (let m = 1; m <= budget; m++) {
      const target = (total * m) / (budget + 1);
      let best = inner[0], bestD = Infinity;
      for (const i of inner) {
        const d = Math.abs(cum[i] - target);
        if (d < bestD) { bestD = d; best = i; }
      }
      keep.add(best);
    }
    return [...keep].sort((a, b) => a - b).map((i) => pts[i]);
  }

  const budget = maxPoints - mandatory.length;
  const keep = new Set(mandatory);
  const segments = mandatory.slice(0, -1).map((a, i) => [a, mandatory[i + 1]]);
  const weights = segments.map(([a, b]) => cum[b] - cum[a]);
  const alloc = allocate(budget, weights);
  segments.forEach(([a, b], i) => {
    const k = alloc[i];
    if (k <= 0 || b <= a + 1) return;
    if (strategy === "even") placeEven(cum, a, b, k, keep);
    else placeHybrid(pts, cum, a, b, k, keep);
  });
  return [...keep].sort((a, b) => a - b).map((i) => pts[i]);
}

// -------------------------------------------------------------- Maps URL ---

const MODES = {
  drive: "driving", driving: "driving",
  walk: "walking", walking: "walking",
  transit: "transit",
  cycle: "cycling", cycling: "cycling", bike: "cycling",
};

export const AVOID_OPTIONS = ["busy-roads", "highways", "stairs", "tolls"];

function coord(cp) {
  return `${cp.lat.toFixed(6)},${cp.lon.toFixed(6)}`;
}

/** Unified Apple Maps directions URL (iOS 18.4+). `start` (seconds) is what
 *  actually begins turn-by-turn — without it the link opens a preview only. */
export function buildUrl(points, { mode = "drive", fromCurrent = false, avoid = [], scheme = "https", start = null } = {}) {
  if (!points.length) throw new Error("Cannot build an Apple Maps URL with no checkpoints");
  const modeVal = MODES[mode];
  if (!modeVal) throw new Error(`Unknown mode '${mode}'; use drive, walk, transit, or cycle`);
  const bad = (avoid || []).filter((a) => !AVOID_OPTIONS.includes(a));
  if (bad.length) throw new Error(`Unknown avoid option(s): ${bad.join(",")}. Allowed: ${AVOID_OPTIONS.join(",")}`);
  if (start !== null && start < 0) throw new Error(`start must be a non-negative number of seconds, got ${start}`);

  const base = scheme === "https" ? "https://maps.apple.com/directions" : "maps://directions";
  const pts = [...points];
  const useSource = !fromCurrent && pts.length > 1;
  const source = useSource ? pts[0] : null;
  const rest = useSource ? pts.slice(1) : pts;
  const destination = rest[rest.length - 1];
  const waypoints = rest.slice(0, -1);

  const params = [];
  if (source) params.push(`source=${coord(source)}`);
  for (const w of waypoints) params.push(`waypoint=${coord(w)}`);
  params.push(`destination=${coord(destination)}`);
  params.push(`mode=${modeVal}`);
  if (avoid && avoid.length) params.push("avoid=" + avoid.join(","));
  if (start !== null) params.push(`start=${start}`);
  return base + "?" + params.join("&");
}

// ------------------------------------------------------------- dispatcher ---

const URL_RE = /https?:\/\/\S+/g;

function parseLinksText(text, name = null) {
  const urls = [...text.matchAll(URL_RE)].map((m) => m[0].replace(/[).,'"]+$/, ""));
  if (!urls.length) throw new Error("File has no http(s) URL and no recognized route format");
  let fallback = null, lastError = null;
  for (const url of urls) {
    let route;
    try {
      route = parseLink(url, name);
    } catch (exc) {
      lastError = exc;
      continue;
    }
    if (route.checkpoints.length >= 2) return route;
    fallback = fallback || route;
  }
  if (fallback) return fallback;
  throw lastError || new Error("Could not parse any link in the file");
}

/** Parse route text (file content or a pasted link). Mirrors Python's
 *  parse_source dispatch: extension first, then content sniffing. */
export function parseText(text, fileName = null) {
  const s = text.trim();
  if (s.startsWith("http://") || s.startsWith("https://")) {
    const firstLine = s.split(/\s/, 1)[0];
    if (s === firstLine) return parseLink(s);
    return parseLinksText(s, nameFromFile(fileName));
  }
  const name = nameFromFile(fileName);
  const ext = (fileName || "").toLowerCase().match(/\.[^.]+$/)?.[0] || "";
  const head = s.slice(0, 500);

  if (head.startsWith("http://") || head.startsWith("https://")) return parseLinksText(text, name);
  if (ext === ".kurviger" || (head.startsWith("{") && text.slice(0, 2000).includes('"paths"'))) {
    return parseKurviger(text, name);
  }
  if (ext === ".gpx" || head.includes("<gpx")) return parseGpx(text, name);
  if (ext === ".kml" || head.includes("<kml")) return parseKml(text, name);
  throw new Error(
    `Unrecognized route format${fileName ? ` for '${fileName}'` : ""}. ` +
    "Supported: .kurviger, .gpx, .kml, .kmz, or a route link."
  );
}

function nameFromFile(fileName) {
  if (!fileName) return null;
  return fileName.replace(/\.[^.]+$/, "");
}

/** Parse a File/ArrayBuffer (handles .kmz); async because of decompression. */
export async function parseBytes(buffer, fileName = null) {
  const b = new Uint8Array(buffer);
  if (b.length >= 4 && b[0] === 0x50 && b[1] === 0x4b && b[2] === 0x03 && b[3] === 0x04) {
    return parseKmz(buffer, nameFromFile(fileName));
  }
  return parseText(new TextDecoder("utf-8").decode(buffer), fileName);
}

/** Full pipeline: route → reduced checkpoints → URL + summary. */
export function convert(route, {
  maxStops = 15, mode = "drive", avoid = [], strategy = "hybrid",
  sourceAtStart = false, start = 0, noStart = false, scheme = "https",
} = {}) {
  const budget = sourceAtStart ? maxStops : maxStops - 1;
  if (budget < 1) throw new Error(`max stops ${maxStops} leaves no room for the route`);
  const used = reduceCheckpoints(route.checkpoints, budget, strategy);
  const url = buildUrl(used, {
    mode,
    fromCurrent: !sourceAtStart,
    avoid,
    scheme,
    start: noStart ? null : start,
  });
  return {
    name: route.name,
    sourceFormat: route.sourceFormat,
    total: route.checkpoints.length,
    used,
    url,
  };
}
