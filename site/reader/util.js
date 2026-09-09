// Tiny shared helpers. No dependencies.

export function fmt(x) {
  return typeof x === "number" ? x.toLocaleString("en-US") : String(x ?? "");
}

export function plural(n, word) {
  return `${fmt(n)} ${word}${n === 1 ? "" : "s"}`;
}

export const pad = (n) => String(n ?? 0).padStart(3, "0");

/** True for an unmodified left click; modified clicks (cmd/ctrl/shift/alt,
 *  middle button) are left to the browser so links open in new tabs. */
export const plainClick = (e) =>
  !e || (e.button === 0 && !e.metaKey && !e.ctrlKey && !e.shiftKey && !e.altKey);

const MON_F = ["January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December"];
const MON_S = MON_F.map((m) => m.slice(0, 3));

/** "2026-08-21" -> "Aug 21, 2026" (full: "August 21, 2026"; year:false: "Aug 21").
 *  Parsed by hand rather than with Date: `new Date("2026-08-21")` is treated
 *  as UTC midnight and renders as the 20th for anyone west of Greenwich. */
export function fdate(s, { full = false, year = true } = {}) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(s ?? "").trim());
  if (!m) return s ?? "";
  const mon = (full ? MON_F : MON_S)[parseInt(m[2], 10) - 1];
  if (!mon) return s;
  const out = `${mon} ${parseInt(m[3], 10)}`;
  return year ? `${out}, ${m[1]}` : out;
}

/** "Issue 002: Second Pressing" -> "Second Pressing". */
export function displayTitle(issue) {
  const t = issue?.title || "";
  const i = t.indexOf(": ");
  return i === -1 ? t : t.slice(i + 2);
}

const ID_RE = /^[A-Za-z0-9]{16,32}$/;
export function spotifyId(uri) {
  if (!uri || typeof uri !== "string") return null;
  let s = uri.trim();
  const q = s.search(/[?#]/);
  if (q !== -1) s = s.slice(0, q);
  const parts = s.split(/[:/]/).filter(Boolean);
  const cand = parts[parts.length - 1];
  return cand && ID_RE.test(cand) ? cand : null;
}

/** Web destination for a track/album: the stored URL, else built from the URI. */
export function spotifyUrl(item, kind = "track") {
  if (item?.spotify_url) return item.spotify_url;
  const id = spotifyId(item?.spotify_track_uri || item?.spotify_album_uri || item?.uri);
  return id ? `https://open.spotify.com/${kind}/${id}` : null;
}

/** spotify: URI for the desktop app hand-off (kept from the old link pair). */
export function spotifyAppUri(item, kind = "track") {
  const id = spotifyId(item?.spotify_track_uri || item?.spotify_album_uri || item?.uri || item?.spotify_url);
  return id ? `spotify:${kind}:${id}` : null;
}

/** The nine listening lanes, colour-coded: one hue each, same chroma family.
 *  Dot is bright, text is darkened for AA contrast on white. */
export const LANES = {
  "the-mist": 240, "beats-idm": 280, "club-continuum": 320,
  "underground-rap": 65, "jazz-bridge": 95, "cosmic-groove": 155,
  "french-electronic": 350, "punk-turn": 20, "bass-edm": 200,
  "house-garage": 260, "liquid": 178, "dad-rock": 40,
};

/** Display names for lane ids (the engine's lanes.json carries the full
 *  names; this keeps tags readable when it hasn't loaded). */
export const LANE_NAMES = {
  "the-mist": "the mist", "beats-idm": "beats & idm", "club-continuum": "club continuum",
  "underground-rap": "underground rap", "jazz-bridge": "jazz bridge", "cosmic-groove": "cosmic groove",
  "french-electronic": "french electronic", "punk-turn": "the punk turn", "bass-edm": "bass & edm",
  "house-garage": "house & garage", "liquid": "liquid", "dad-rock": "dad rock",
};
export const laneName = (id) => LANE_NAMES[id] || String(id || "").replace(/-/g, " ");

export const MODULE_NAMES = {
  front_to_back: "Album of the Week",
  singles_rack: "Singles Rack",
  the_mix: "Mixes",
  revival_desk: "Second Chances",
  critics_desk: "Critics Desk",
  catalog_room: "Catalog Room",
  new_this_week: "New This Week",
  ledger: "The Ledger",
};

/** The issue's own hover gradient: its three most saturated cover-palette
 *  colours, light to dark, as a CSS gradient. Null when no palette exists
 *  (the fixture), so callers can fall back. */
export function paletteGradient(issue) {
  const pal = issue?.companion_playlist?.cover_art?.palette;
  if (!Array.isArray(pal)) return null;
  const cs = pal.filter((c) => /^#[0-9a-fA-F]{6}$/.test(c));
  if (cs.length < 2) return null;
  const rgb = (h) => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];
  const sat = (h) => { const [r, g, b] = rgb(h); return Math.max(r, g, b) - Math.min(r, g, b); };
  const lum = (h) => { const [r, g, b] = rgb(h); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
  const top = [...cs].sort((x, y) => sat(y) - sat(x)).slice(0, 3).sort((x, y) => lum(y) - lum(x));
  return `linear-gradient(90deg, ${top.join(", ")})`;
}

/** Cover for an issue in the archive. The week's generated cover when the
 *  engine has made one ("text" carries the issue's name, as on Spotify;
 *  "plain" is the bare gradient for places that set the name beside it),
 *  else the companion playlist's art, else the lead recommendation's cover. */
export function issueCover(issue, variant = "text") {
  const cp = issue?.companion_playlist;
  const ca = cp?.cover_art;
  if (ca && ca[variant]) return ca[variant];
  if (ca && ca.text) return ca.text;
  if (cp?.cover_url) return cp.cover_url;
  const lead = (issue?.modules || []).find((m) => m?.type === "front_to_back");
  return lead?.album?.cover_url || null;
}
