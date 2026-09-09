#!/usr/bin/env bash
# Clanker.CD — one weekly issue, start to finish.
#
#   ./weekly.sh              next issue number, template prose, publish playlist
#   ./weekly.sh --n 3        force an issue number
#   ./weekly.sh --dry-run    build and validate, publish nothing
#   ./weekly.sh --no-playlist
#
# Stages, in order:
#   model    rebuild the taste model from the cleaned history
#   ledger   grade the PREVIOUS issue against what actually got played
#   harvest  pull candidates (MusicBrainz, Last.fm, LB labs, Deezer, RSS)
#   nts      pull radio episodes + tracklists for Mixes
#   verify   two-round zero-play check + served ledger
#   select   rank into shortlists (+ phase2: mix, critics, catalog)
#   availability  drop album-of-the-week candidates Spotify does not carry
#   issue    write issues/issue-NNN.json, receipts-validated
#   resolve  pick a track per artist-level lead + fill every Spotify URI
#   art      resolve cover art (oEmbed / MusicBrainz / iTunes / NTS)
#   cover    palette from the week's covers -> render the two covers -> set on Spotify
#   publish  push the companion playlist to Spotify from exact URIs
#   serve    append everything published to the served ledger
#
# Every stage is re-runnable. Network stages are cached on disk, so a repeat
# run inside the cache TTL costs almost nothing. Nothing here is paid: the
# APIs are free tiers or keyless, and prose is templated from receipts unless
# a curated copy file is supplied via --copy.
set -euo pipefail

cd "$(dirname "$0")"
export PYTHONPATH="$PWD"

N=""
DRY=0
PLAYLIST=1
COPY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --n) N="$2"; shift 2 ;;
    --dry-run) DRY=1; PLAYLIST=0; shift ;;
    --no-playlist) PLAYLIST=0; shift ;;
    --copy) COPY="$2"; shift 2 ;;
    *) echo "unknown flag: $1" >&2; exit 2 ;;
  esac
done

# Next issue number = highest existing + 1, unless forced.
if [ -z "$N" ]; then
  N=$(python3 - <<'PY'
import re, pathlib
ns = [int(m.group(1)) for p in pathlib.Path("issues").glob("issue-*.json")
      for m in [re.search(r"issue-(\d+)\.json$", p.name)] if m]
print(max(ns) + 1 if ns else 1)
PY
)
fi
PREV=$((N - 1))
say() { printf '\n\033[1m== %s\033[0m\n' "$1"; }

say "issue $(printf '%03d' "$N")"

# Listens since the history export, from ListenBrainz. Optional: without a
# LISTENBRAINZ_USER the model runs on the export alone and says so.
say "fresh listens"
python3 -m engine.model.fresh_listens || echo "  fresh listens unavailable — model runs on the export alone"

say "model"
python3 -m engine.model.build_taste_model
# Labels the reader lives on (MusicBrainz, URL-cached 30 days: slow once,
# cheap weekly). Optional: without it the labels source reports skipped.
say "label model"
python3 -m engine.model.build_label_model || echo "  label model unavailable — label leads skipped this week"

if [ "$PREV" -ge 1 ] && [ -f "issues/issue-$(printf '%03d' "$PREV").json" ]; then
  say "ledger (grading issue $(printf '%03d' "$PREV"))"
  # Never fatal: no scrobbles yet is a normal state, not a failure.
  python3 -m engine.ledger.build_ledger --issue "$PREV" || \
    echo "  ledger unavailable — issue will publish without it"
else
  say "ledger — skipped (no previous issue)"
  rm -f out/ledger.json
fi

say "harvest"
python3 -m engine.harvest.run_harvest

say "mixes (nts, kexp, mixesdb)"
python3 -m engine.harvest.nts || echo "  NTS unavailable"
python3 -m engine.harvest.kexp || echo "  KEXP unavailable"
python3 -m engine.harvest.mixesdb || echo "  MixesDB unavailable"

say "verify"
python3 -m engine.verify.zero_play
# How many weeks of never-played artists the pool holds; a warning here is
# the early signal, a short rack is the late one.
python3 -m engine.harvest.supply || echo "  supply gauge unavailable"

say "select"
python3 -m engine.select.select_issue --n "$N"
python3 -m engine.select.phase2

# Which album-of-the-week candidates Spotify carries. Must precede `issue`:
# the module's receipts and prose are built around whichever record is
# chosen, so the choice cannot be revisited afterwards.
say "availability"
python3 -m engine.deliver.availability || \
  echo "  availability unchecked — album of the week may not be streamable"

say "issue"
if [ -n "$COPY" ]; then
  python3 -m engine.editorial.writer --n "$N" --copy "$COPY"
else
  python3 -m engine.editorial.writer --n "$N" --no-llm
fi
python3 -m engine.editorial.validate "issues/issue-$(printf '%03d' "$N").json"

# Picks -> Spotify URIs. Must precede `art`: cover art for tracks and the
# album of the week comes from Spotify oEmbed, which needs the URI first.
say "resolve"
python3 -m engine.deliver.resolve_tracks --n "$N" || \
  echo "  track resolution skipped — the playlist will be short"

# The semantic gate on the final document: right records, still new,
# nothing served twice, picks unchanged since selection. Fatal on purpose.
say "final check"
python3 -m engine.editorial.final_check --n "$N"

say "cover art"
python3 -m engine.art --n "$N" || echo "  cover art unresolved — covers fall back to tiles"
python3 -m engine.site_index
python3 -m engine.releases || echo "  release calendar skipped"
python3 -m engine.cover.palette --n "$N" || true
python3 -m engine.cover.render --n "$N" || echo "  cover render skipped"
# The robots on the personal app hold this week's disc: repaint the live
# pose set from the issue's palette. The public site's set is untouched.
python3 brand/mascot/produce.py --live-only \
  --live-palette "site/public/issues/palette-$(printf '%03d' "$N").json" \
  || echo "  live disc skipped"

if [ "$DRY" = "1" ]; then
  say "dry run — nothing published"
  exit 0
fi

if [ "$PLAYLIST" = "1" ]; then
  say "publish playlist"
  python3 -m engine.deliver.publish_playlist --n "$N" || \
    echo "  playlist publish failed — the issue itself is fine"
fi

# Again once the playlist exists, so the issue's archive cover resolves.
python3 -m engine.art --n "$N" >/dev/null 2>&1 || true
python3 -m engine.cover.upload --n "$N" || echo "  cover upload skipped"

say "served ledger"
python3 -m engine.serve_ledger --n "$N"

say "done — issue $(printf '%03d' "$N")"
echo "read it:  npm --prefix site run dev   ->  http://localhost:3010/?n=$N"
