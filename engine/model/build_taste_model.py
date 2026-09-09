"""Build the taste model + revival pools from the cleaned Spotify history.

Outputs (schemas per CONTRACTS.md)
----------------------------------
out/taste-model.json    clusters (states, affinities, receipts) + artists_index
out/revival-pools.json  barely_played / fade_outs / time_capsule

Reference "now"
---------------
All recency math uses the LAST PLAY in the dataset (window.last_play), not the
wall clock, so results are stable when re-run against a stale export. The
180-day / 12-month / 24-month cutoffs below are relative to that date.

Affinity formula (contract: "normalized blend of hours x completion x recency")
-------------------------------------------------------------------------------
    affinity = 0.55*H + 0.25*C + 0.20*R        (rounded to 3 dp)
    H = min(1, ln(1 + hours) / ln(1 + 60))     log-scaled lifetime hours,
                                               saturating near the #1 artist
                                               (Westside Gunn, 64.8 h)
    C = completion_rate                        from artists.csv (0..1)
    R = recency_weight = 0.5 ** (days_since_last_play / 548)
                                               half-life ~18 months (548 d)

Cluster state (contract thresholds)
-----------------------------------
    lifetime_share = cluster member lifetime hours / global hours
    recent_share   = cluster member last-180-day hours / global last-180-day hours
    ratio = recent_share / lifetime_share
    ratio > 1.5  -> rising
    ratio < 0.35 -> dormant, or burned when cluster lifetime hours > 25
    else         -> active

Membership expansion (seeds -> members), method labeled per member in "via"
---------------------------------------------------------------------------
via "seed"      hand-authored seeds.json artists (all confirmed played).
via "playlist"  co-membership in his own playlists — an artist joins with
                >= 2 tracks in ONE anchor, or by appearing in >= 3 anchors.
                (The old "one track in each of two anchors" path was weak
                enough to leak: two stray tracks are shuffle residue, not
                curation.) Anchors resolve from (PLAYLIST_JSON,
                playlists[].items[].track.{trackName,artistName}). A playlist
                is an ANCHOR for a cluster when its name matches seeds.json
                anchor_playlists_hint, OR its tracks by that cluster's seeds
                are >= 5% of the playlist (min 2 seed tracks). CATCH-ALL
                playlists — seed-relevant (>= 2 seed tracks and >= 4%) to 3+
                different clusters, e.g. the 845-track "front to back" — are
                never anchors: they encode overall taste, not a lane, and
                flood every cluster with the same top artists. An artist
                joins via playlist with >= 2 tracks in one anchor or >= 1
                track in each of two anchors. (The engine's own "Listening
                Record" playlist is excluded — output, not curation.)
via "session"   co-occurrence in listening sessions — plays grouped by gap
                <= 35 min between consecutive play starts, single pass over
                plays.csv. Three guards, because naive co-occurrence made the
                top of every cluster identical (Khruangbin led underground-rap;
                Drake joined jazz-bridge):
                1. Sessions with > 25 distinct artists contribute NOTHING to
                   co-occurrence (they still count toward an artist's own
                   session total). A 35-min-gap chain across an all-day
                   shuffle is noise, and counting it as association is what
                   dragged every high-volume artist into every lane.
                2. An artist joins only when it shares >= 5 qualifying
                   sessions with the cluster's seeds AND those are >= 30% of
                   the artist's own sessions.
                3. SPECIFICITY: the cluster must account for >= 22% of the
                   artist's total cluster-association mass (its shared-session
                   counts summed over all clusters). A ubiquitous artist
                   spreads flat across nine clusters (~11% each) and is
                   rejected everywhere via session — it can still enter a
                   cluster as a seed or through the listener's own playlists,
                   which is curation, not co-incidence. Session members carry
                   their spec value in the output for audit.
Every member must exist in the cleaned history with >= 5 plays or >= 0.5 h —
nothing is fabricated. Members capped at 40/cluster by affinity.

Revival pools (contract criteria, relative to reference date)
-------------------------------------------------------------
barely_played  aggregated track plays <= 2, never skipped, last played >= 12
               months ago, artist lifetime hours >= 3. Sorted by artist
               affinity. Cap 60 (max 4 tracks per artist for variety).
fade_outs      aggregated track plays >= 40 with >= 25% of plays inside one
               calendar month (per-month counts from the plays.csv pass) and
               zero plays in the last 24 months. Sorted by plays. Cap 40.
time_capsule   plays >= 5, never skipped, last played >= 24 months ago.
               Sorted by plays. Cap 60 (max 4 per artist).
Track rows are aggregated by normalized (artist, title) so "Song" and
"Song - Original Mix" count as one track; the reported plays come from that
aggregation of tracks.csv, fade_out plays/months from the plays.csv pass.

Run:  PYTHONPATH=<root> python3 -m engine.model.build_taste_model
"""

import csv
import json
import math
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from engine.lib.config import PROJECT_ROOT, load_config
from engine.lib import history
from engine.lib.history import iter_plays, load_artists
from engine.lib.normalize import norm_artist, norm_title, track_key

SESSION_GAP_S = 35 * 60
# Sessions with more distinct artists than this are shuffle noise: they still
# count toward an artist's own session total, but contribute no co-occurrence.
MAX_COOCCUR_SESSION_ARTISTS = 25
# A cluster must hold at least this share of an artist's total cluster
# association for a session-join — flat-everywhere artists fail everywhere.
SESSION_SPEC_MIN = 0.22
RECENT_DAYS = 180
HALF_LIFE_DAYS = 548          # ~18 months
HOURS_SATURATION = 60.0
MEMBER_CAP = 40
RISING_RATIO = 1.5
DORMANT_RATIO = 0.35
BURNED_MIN_HOURS = 25.0
MIN_MEMBER_PLAYS = 5
MIN_MEMBER_HOURS = 0.5
EXCLUDED_PLAYLISTS = {"the listening record, vol. 1: never played"}
PER_ARTIST_POOL_CAP = 4

SEEDS_PATH = Path(__file__).with_name("seeds.json")


# ---------------------------------------------------------------- utilities

def _f(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _i(x, default=0):
    try:
        return int(x)
    except (TypeError, ValueError):
        return default


def _epoch(ts):
    """'2015-04-23T03:56:05Z' -> unix seconds (assumes UTC)."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()


def recency_weight(last_played, ref_date):
    if not last_played:
        return 0.0
    try:
        d = date.fromisoformat(last_played[:10])
    except ValueError:
        return 0.0
    days = max(0, (ref_date - d).days)
    return 0.5 ** (days / HALF_LIFE_DAYS)


def affinity(hours, completion, rec_w):
    h = min(1.0, math.log1p(max(0.0, hours)) / math.log1p(HOURS_SATURATION))
    return round(0.55 * h + 0.25 * completion + 0.20 * rec_w, 3)


def _tail_last_play_date():
    """Cheap read of the final plays.csv row (file is chronological) so the
    single main pass can use exact date cutoffs. Verified against the true
    max ts during the pass."""
    return history.tail_last_play_ts() or "1970-01-01"


def reference_date(export_date, fresh):
    """The model's clock: the newer of the export's last event and the fresh
    overlay's watermark. Recency is measured from here, so the export
    going stale no longer freezes 'recent' at the export's own tail."""
    wm = (fresh or {}).get("watermark")
    try:
        fd = date.fromisoformat(str(wm)[:10]) if wm else None
    except ValueError:
        fd = None
    return max(export_date, fd) if fd else export_date


# ---------------------------------------------------------------- playlists

def load_playlists(cfg):
    """[{name, n_tracks, artist_counts: {norm_artist: n_tracks_by_artist}}]"""
    path = cfg.get("PLAYLIST_JSON")
    if not path or not Path(path).exists():
        return []
    data = json.loads(Path(path).read_text())
    out = []
    for pl in data.get("playlists", []):
        name = pl.get("name") or ""
        if name.strip().lower() in EXCLUDED_PLAYLISTS:
            continue
        counts = Counter()
        for item in pl.get("items") or []:
            tr = item.get("track") if isinstance(item, dict) else None
            if not tr or not tr.get("artistName"):
                continue
            counts[norm_artist(tr["artistName"])] += 1
        if counts:
            out.append({"name": name, "n_tracks": sum(counts.values()),
                        "artist_counts": counts})
    return out


# ------------------------------------------------------- single plays pass

def scan_plays(seed_clusters_by_artist, fade_titles_by_artist, recent_cutoff):
    """ONE pass over plays.csv. Returns global stats, per-artist last-180-day
    ms, session co-occurrence with cluster seeds, per-artist session counts,
    and per-month counts for fade-out candidate tracks."""
    total_plays = 0
    total_ms = 0
    skips = 0
    recent_total_ms = 0
    first_ts = None
    last_ts = None
    recent_ms = defaultdict(int)                    # norm_artist -> ms
    artist_sessions = Counter()                     # norm_artist -> n sessions
    co = {cid: Counter() for cids in seed_clusters_by_artist.values()
          for cid in cids}                          # cid -> artist -> n shared
    fade = {}                                       # key -> stats dict
    cutoff_str = recent_cutoff.isoformat()

    cur_artists = set()
    prev_epoch = None

    def close_session():
        if not cur_artists:
            return
        for a in cur_artists:
            artist_sessions[a] += 1
        # Mega-sessions still count toward own-session totals above (they are
        # real listening), but a 40-artist shuffle chain proves nothing about
        # which artists belong together — so it contributes no association.
        if len(cur_artists) <= MAX_COOCCUR_SESSION_ARTISTS:
            hit = set()
            for a in cur_artists:
                hit.update(seed_clusters_by_artist.get(a, ()))
            for cid in hit:
                co[cid].update(cur_artists)
        cur_artists.clear()

    for row in iter_plays():
        ts = row["ts"]
        if first_ts is None:
            first_ts = ts
        last_ts = ts
        na = norm_artist(row["artist"])
        ms = _i(row["ms_played"])
        total_plays += 1
        total_ms += ms
        if row["skipped"] == "True":
            skips += 1
        d = ts[:10]
        if d >= cutoff_str:
            recent_ms[na] += ms
            recent_total_ms += ms
        ep = _epoch(ts)
        if prev_epoch is not None and ep - prev_epoch > SESSION_GAP_S:
            close_session()
        prev_epoch = ep
        cur_artists.add(na)
        titles = fade_titles_by_artist.get(na)
        if titles:
            nt = norm_title(row["track"])
            if nt in titles:
                st = fade.setdefault((na, nt), {"months": Counter(),
                                                "plays": 0, "last": d})
                st["months"][ts[:7]] += 1
                st["plays"] += 1
                st["last"] = d
    close_session()

    return {
        "plays": total_plays,
        "ms": total_ms,
        "skips": skips,
        "recent_total_ms": recent_total_ms,
        "first_ts": first_ts,
        "last_ts": last_ts,
        "recent_ms": recent_ms,
        "artist_sessions": artist_sessions,
        "co": co,
        "fade": fade,
    }


# ------------------------------------------------------------ tracks table

def count_artist_rows(cfg):
    """Raw artists.csv row count (12,308 headline). load_artists() merges
    normalization collisions (e.g. case variants) so its len() undercounts."""
    with open(Path(cfg["SPOTIFY_CLEAN_DIR"]) / "artists.csv", newline="") as f:
        return sum(1 for _ in csv.reader(f)) - 1


def load_track_aggregates(cfg):
    """Aggregate tracks.csv rows by normalized (artist, title).
    Returns {key: {plays, ever_skipped, first, last, row}} where row is the
    most-played raw row (display names/album/uri)."""
    agg = {}
    n_rows = 0
    with open(Path(cfg["SPOTIFY_CLEAN_DIR"]) / "tracks.csv", newline="") as f:
        for row in csv.DictReader(f):
            n_rows += 1
            k = track_key(row["artist"], row["track"])
            plays = _i(row["plays"])
            a = agg.get(k)
            if a is None:
                a = agg[k] = {"plays": 0, "ever_skipped": False,
                              "first": row["first_played"],
                              "last": row["last_played"],
                              "row": row, "row_plays": plays}
            a["plays"] += plays
            if _f(row["skip_rate"]) > 0:
                a["ever_skipped"] = True
            if row["first_played"] and (not a["first"] or row["first_played"] < a["first"]):
                a["first"] = row["first_played"]
            if row["last_played"] and (not a["last"] or row["last_played"] > a["last"]):
                a["last"] = row["last_played"]
            if plays > a["row_plays"]:
                a["row"], a["row_plays"] = row, plays
    return agg, n_rows


# ----------------------------------------------------------------- members

ANCHOR_MIN_FRAC = 0.05        # seed tracks must be >= 5% of the playlist
ANCHOR_MIN_SEED_TRACKS = 3    # was 2: two stray seed tracks anchored mixed
                              # playlists onto lanes they barely touch
# A cluster must hold this share of an artist's total playlist-anchor
# evidence for a playlist-join (mirror of SESSION_SPEC_MIN). Evidence per
# anchor is capped at 3 tracks so one huge playlist cannot dominate.
PLAYLIST_SPEC_MIN = 0.30
PLAYLIST_EV_CAP = 3
CATCHALL_FRAC = 0.04          # "relevant to a cluster" bar for catch-all test
CATCHALL_MIN_CLUSTERS = 3     # relevant to >= this many clusters => catch-all


def find_anchors_by_cluster(clusters, playlists):
    """{cluster_id: [playlist]} — see module docstring for the anchor rule.

    Catch-all playlists (seed-relevant to >= 3 clusters, e.g. the 845-track
    "front to back" mega playlist) are globally excluded: they represent his
    whole taste, and anchoring on them collapses every cluster into the same
    top-hours artists. Hand-authored hints in seeds.json always win."""
    frac_matrix = []          # (playlist, {cid: (seed_tracks, frac)})
    for pl in playlists:
        per = {}
        for c in clusters:
            st = sum(pl["artist_counts"].get(s, 0) for s in c["_seed_norms"])
            per[c["id"]] = (st, st / pl["n_tracks"] if pl["n_tracks"] else 0.0)
        frac_matrix.append((pl, per))

    catchall = set()
    for pl, per in frac_matrix:
        relevant = sum(1 for st, fr in per.values()
                       if st >= ANCHOR_MIN_SEED_TRACKS and fr >= CATCHALL_FRAC)
        if relevant >= CATCHALL_MIN_CLUSTERS:
            catchall.add(pl["name"])

    out = {c["id"]: [] for c in clusters}
    for c in clusters:
        hints = {h.strip().lower()
                 for h in c.get("anchor_playlists_hint", [])}
        for pl, per in frac_matrix:
            st, fr = per[c["id"]]
            hinted = pl["name"].strip().lower() in hints
            organic = (st >= ANCHOR_MIN_SEED_TRACKS and fr >= ANCHOR_MIN_FRAC
                       and pl["name"] not in catchall)
            if hinted or organic:
                out[c["id"]].append(pl)
    return out, sorted(catchall)


def expand_members(cluster, anchors, scan, artists_by_norm, pl_ev):
    """-> ({norm_artist: via}, {norm_artist: spec}) with priority
    seed > playlist > session. spec is recorded for expanded joins."""
    members = {}
    for s in cluster["_seed_norms"]:
        if s in artists_by_norm:
            members[s] = "seed"
        else:
            print(f"  [warn] seed not found in history: {s!r} "
                  f"(cluster {cluster['id']}) — skipped")
    spec_map = {}
    # playlist co-membership: >=2 tracks in one anchor, or >=3 anchors — AND
    # this cluster must hold >= PLAYLIST_SPEC_MIN of the artist's total
    # anchor evidence across all clusters. Without the second gate, mixed
    # playlists ("kush friendly beats" is jazz-beats AND rap AND mist) flood
    # every lane they anchor with the same top-hours artists.
    strong = set()
    anchor_presence = Counter()
    for pl in anchors:
        for a, n in pl["artist_counts"].items():
            if a in members:
                continue
            anchor_presence[a] += 1
            if n >= 2:
                strong.add(a)
    my_ev = pl_ev.get(cluster["id"], {})
    for a in set(strong) | {a for a, k in anchor_presence.items() if k >= 3}:
        if a not in artists_by_norm:
            continue
        total_ev = sum(c.get(a, 0) for c in pl_ev.values())
        spec = my_ev.get(a, 0) / total_ev if total_ev else 0.0
        if spec < PLAYLIST_SPEC_MIN:
            continue
        if members.setdefault(a, "playlist") == "playlist":
            spec_map[a] = round(spec, 2)
    # session co-occurrence, with a cross-cluster specificity gate
    co = scan["co"].get(cluster["id"], {})
    all_co = scan["co"]
    sess = scan["artist_sessions"]
    for a, n_shared in co.items():
        if a in members or a not in artists_by_norm:
            continue
        own = sess.get(a, 1)
        if n_shared < 5 or n_shared < 0.3 * own:
            continue
        total_assoc = sum(c.get(a, 0) for c in all_co.values())
        spec = n_shared / total_assoc if total_assoc else 0.0
        if spec < SESSION_SPEC_MIN:
            continue
        members[a] = "session"
        spec_map[a] = round(spec, 2)
    # activity floor
    out = {}
    for a, via in members.items():
        row = artists_by_norm[a]
        if via == "seed" or _i(row["plays"]) >= MIN_MEMBER_PLAYS \
                or _f(row["hours"]) >= MIN_MEMBER_HOURS:
            out[a] = via
    return out, spec_map


# -------------------------------------------------------------------- main

def build():
    cfg = load_config()
    seeds = json.loads(SEEDS_PATH.read_text())
    artists_by_norm = load_artists()
    playlists = load_playlists(cfg)

    for c in seeds["clusters"]:
        c["_seed_norms"] = [norm_artist(s) for s in c["seed_artists"]]
    seed_clusters_by_artist = defaultdict(set)
    for c in seeds["clusters"]:
        for s in c["_seed_norms"]:
            seed_clusters_by_artist[s].add(c["id"])

    # tracks.csv aggregation (also powers the revival pools)
    track_agg, n_track_rows = load_track_aggregates(cfg)

    # fade-out candidates: aggregated plays >= 35 pre-filter (>= 40 enforced
    # on the exact plays.csv counts after the pass)
    fade_titles_by_artist = defaultdict(set)
    for (na, nt), a in track_agg.items():
        if a["plays"] >= 35:
            fade_titles_by_artist[na].add(nt)

    fresh = history.fresh_summary()
    export_date = date.fromisoformat(_tail_last_play_date()[:10])
    ref_date = reference_date(export_date, fresh)
    recent_cutoff = ref_date - timedelta(days=RECENT_DAYS)

    scan = scan_plays(seed_clusters_by_artist, dict(fade_titles_by_artist),
                      recent_cutoff)
    if scan["last_ts"][:10] != export_date.isoformat():
        print(f"  [warn] tail date {export_date} != scanned max "
              f"{scan['last_ts'][:10]}; using scanned max")
        export_date = date.fromisoformat(scan["last_ts"][:10])
        ref_date = reference_date(export_date, fresh)
    if fresh["listens"]:
        print(f"  fresh overlay: {fresh['listens']} listens since the export, "
              f"reference date {ref_date}")

    global_hours = scan["ms"] / 3.6e6
    recent_hours_total = scan["recent_total_ms"] / 3.6e6

    def artist_metrics(norm):
        row = artists_by_norm[norm]
        hours = _f(row["hours"])
        rw = recency_weight(row["last_played"], ref_date)
        aff = affinity(hours, _f(row["completion_rate"]), rw)
        return row, hours, rw, aff

    # ---- clusters
    anchors_by_cluster, catchall = find_anchors_by_cluster(
        seeds["clusters"], playlists)
    if catchall:
        print(f"  catch-all playlists excluded from anchoring: {catchall}")
    # Cross-cluster playlist-evidence matrix for the specificity gate:
    # per cluster, per artist, anchor tracks capped at PLAYLIST_EV_CAP per
    # playlist so one giant playlist cannot dominate the denominator.
    pl_ev = {}
    for cid, anchor_pls in anchors_by_cluster.items():
        cnt = Counter()
        for pl in anchor_pls:
            for a, n in pl["artist_counts"].items():
                cnt[a] += min(n, PLAYLIST_EV_CAP)
        pl_ev[cid] = cnt
    clusters_out = []
    member_norms_all = set()
    for c in seeds["clusters"]:
        anchors = anchors_by_cluster[c["id"]]
        members, spec_map = expand_members(c, anchors, scan, artists_by_norm,
                                           pl_ev)
        entries = []
        for a, via in members.items():
            row, hours, rw, aff = artist_metrics(a)
            e = {
                "artist": row["artist"], "affinity": aff,
                "hours": round(hours, 1), "plays": _i(row["plays"]),
                "skip_rate": _f(row["skip_rate"]),
                "last_played": row["last_played"], "via": via,
                "_norm": a,
            }
            if a in spec_map:
                e["spec"] = spec_map[a]  # auditability of the expanded join
            entries.append(e)
        entries.sort(key=lambda e: (-e["affinity"], -e["hours"]))
        entries = entries[:MEMBER_CAP]
        kept = {e["_norm"] for e in entries}
        member_norms_all |= kept

        life_h = sum(e["hours"] for e in entries)
        rec_h = sum(scan["recent_ms"].get(e["_norm"], 0) for e in entries) / 3.6e6
        life_share = life_h / global_hours if global_hours else 0.0
        rec_share = rec_h / recent_hours_total if recent_hours_total else 0.0
        ratio = (rec_share / life_share) if life_share else 0.0
        if ratio > RISING_RATIO:
            state = "rising"
        elif ratio < DORMANT_RATIO:
            state = "burned" if life_h > BURNED_MIN_HOURS else "dormant"
        else:
            state = "active"
        evidence = (
            f"{rec_share:.1%} of last-{RECENT_DAYS}-day hours vs {life_share:.1%} "
            f"lifetime share ({ratio:.2f}x) -> {state}. Members: "
            f"{sum(1 for e in entries if e['via'] == 'seed')} seeds + "
            f"{sum(1 for e in entries if e['via'] == 'playlist')} via playlist "
            f"co-membership + {sum(1 for e in entries if e['via'] == 'session')} "
            f"via shared sessions (gap <= 35 min); shares computed from member "
            f"artists' hours in plays.csv."
        )

        anchor_out = sorted(
            ({"name": pl["name"],
              "overlap_tracks": sum(n for a, n in pl["artist_counts"].items()
                                    if a in kept)}
             for pl in anchors),
            key=lambda x: -x["overlap_tracks"])
        anchor_out = [a for a in anchor_out if a["overlap_tracks"] >= 2][:6]

        receipts = [{
            "stat_id": f"cluster_hours:{c['id']}",
            "claim": (f"{c['name']}: {life_h:.1f} hours lifetime across "
                      f"{len(entries)} member artists"),
            "value": round(life_h, 1),
        }]
        if entries:
            top = entries[0]
            receipts.append({
                "stat_id": f"artist_hours:{top['_norm']}",
                "claim": (f"{top['artist']}: {top['hours']} hours at "
                          f"{round(top['skip_rate'] * 100)}% skip"),
                "value": top["hours"],
            })
            receipts.append({
                "stat_id": f"artist_skip:{top['_norm']}",
                "claim": (f"{top['artist']} skip rate "
                          f"{round(top['skip_rate'] * 100)}%"),
                "value": top["skip_rate"],
            })

        clusters_out.append({
            "id": c["id"], "name": c["name"], "description": c["description"],
            "state": state, "state_evidence": evidence,
            "seed_artists": c["seed_artists"],
            "members": [{k: v for k, v in e.items() if k != "_norm"}
                        for e in entries],
            "anchor_playlists": anchor_out,
            "receipts": receipts,
            "_ratio": ratio, "_life_h": life_h, "_rec_h": rec_h,
        })

    # ---- artists_index: all cluster members + top 300 artists by hours
    index_norms = set(member_norms_all)
    for norm, _row in sorted(artists_by_norm.items(),
                             key=lambda kv: -_f(kv[1]["hours"]))[:300]:
        index_norms.add(norm)
    cluster_of = defaultdict(list)
    for cl in clusters_out:
        for m in cl["members"]:
            cluster_of[norm_artist(m["artist"])].append(cl["id"])
    artists_index = {}
    for norm in sorted(index_norms):
        row = artists_by_norm[norm]
        rw = recency_weight(row["last_played"], ref_date)
        artists_index[norm] = {
            "artist": row["artist"],
            "clusters": cluster_of.get(norm, []),
            "hours": _f(row["hours"]), "plays": _i(row["plays"]),
            "skip_rate": _f(row["skip_rate"]),
            "completion_rate": _f(row["completion_rate"]),
            "first_played": row["first_played"],
            "last_played": row["last_played"],
            "recency_weight": round(rw, 3),
        }

    taste_model = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "window": {"first_play": scan["first_ts"], "last_play": scan["last_ts"]},
        "global": {
            "plays": scan["plays"],
            "hours": round(global_hours, 1),
            "tracks": n_track_rows,
            # Distinct artists the history actually resolves to, which is
            # what verification checks candidates against. The raw row
            # count is kept beside it; the two differed by 49 under the old
            # normalizer and the headline was quietly the wrong one.
            "artists": len(artists_by_norm),
            "artist_rows": count_artist_rows(cfg),
            "skip_rate": round(scan["skips"] / scan["plays"], 2),
            # Three clocks, kept apart on purpose: when the export ends,
            # when the fresh overlay ends, and the date recency was
            # measured from (the newer of the two).
            "export_cutoff": scan["last_ts"],
            "fresh_cutoff": fresh["watermark"],
            "fresh_listens": fresh["listens"],
            "reference_date": ref_date.isoformat(),
        },
        "clusters": [{k: v for k, v in cl.items() if not k.startswith("_")}
                     for cl in clusters_out],
        "artists_index": artists_index,
    }

    # ---- revival pools
    cutoff_12m = (ref_date - timedelta(days=365)).isoformat()
    cutoff_24m = (ref_date - timedelta(days=730)).isoformat()

    def artist_aff_note(raw_artist):
        norm = norm_artist(raw_artist)
        if norm not in artists_by_norm:
            return 0.0, 0.0, "artist not in artists.csv"
        row, hours, rw, aff = artist_metrics(norm)
        note = (f"{row['artist']}: {hours:.1f}h lifetime at "
                f"{round(_f(row['skip_rate']) * 100)}% skip, affinity {aff}")
        cl = cluster_of.get(norm)
        if cl:
            note += f" ({'/'.join(cl)})"
        return aff, hours, note

    barely = []
    for (na, nt), a in track_agg.items():
        if a["plays"] <= 2 and not a["ever_skipped"] and a["last"] \
                and a["last"] <= cutoff_12m:
            row = a["row"]
            if na not in artists_by_norm:
                continue
            hours = _f(artists_by_norm[na]["hours"])
            if hours < 3.0:
                continue
            aff, _h, note = artist_aff_note(row["artist"])
            barely.append({
                "artist": row["artist"], "track": row["track"],
                "album": row["album"], "plays": a["plays"],
                "skip_rate": 0.0, "first_played": a["first"],
                "last_played": a["last"], "artist_hours": hours,
                "note": note, "_aff": aff,
            })
    barely.sort(key=lambda x: (-x["_aff"], x["last_played"]))
    barely = _cap_per_artist(barely, PER_ARTIST_POOL_CAP, 60)
    for b in barely:
        del b["_aff"]

    fades = []
    for (na, nt), st in scan["fade"].items():
        if st["plays"] < 40 or st["last"] > cutoff_24m:
            continue
        peak_month, peak_n = st["months"].most_common(1)[0]
        if peak_n < 0.25 * st["plays"]:
            continue
        row = track_agg[(na, nt)]["row"]
        fades.append({
            "artist": row["artist"], "track": row["track"],
            "plays": st["plays"], "peak_month": peak_month,
            "peak_month_plays": peak_n, "last_played": st["last"],
        })
    fades.sort(key=lambda x: -x["plays"])
    fades = fades[:40]

    capsule = []
    for (na, nt), a in track_agg.items():
        if a["plays"] >= 5 and not a["ever_skipped"] and a["last"] \
                and a["last"] <= cutoff_24m:
            row = a["row"]
            capsule.append({
                "artist": row["artist"], "track": row["track"],
                "plays": a["plays"], "skip_rate": 0.0,
                "last_played": a["last"],
            })
    capsule.sort(key=lambda x: (-x["plays"], x["last_played"]))
    capsule = _cap_per_artist(capsule, PER_ARTIST_POOL_CAP, 60)

    pools = {"barely_played": barely, "fade_outs": fades,
             "time_capsule": capsule}

    out_dir = Path(cfg["OUT_DIR"])
    (out_dir / "taste-model.json").write_text(
        json.dumps(taste_model, indent=1, ensure_ascii=False) + "\n")
    (out_dir / "revival-pools.json").write_text(
        json.dumps(pools, indent=1, ensure_ascii=False) + "\n")

    return taste_model, pools, clusters_out


def _cap_per_artist(items, per_artist, total):
    seen = Counter()
    out = []
    for it in items:
        k = norm_artist(it["artist"])
        if seen[k] >= per_artist:
            continue
        seen[k] += 1
        out.append(it)
        if len(out) >= total:
            break
    return out


def summarize(taste_model, pools, clusters_out):
    g = taste_model["global"]
    w = taste_model["window"]
    print(f"\n=== taste model ===")
    print(f"window {w['first_play'][:10]} -> {w['last_play'][:10]}  |  "
          f"{g['plays']:,} plays  {g['hours']:,}h  {g['tracks']:,} tracks  "
          f"{g['artists']:,} artists  skip {g['skip_rate']:.0%}")
    for cl in clusters_out:
        print(f"\n[{cl['state'].upper():7}] {cl['name']}  "
              f"(ratio {cl['_ratio']:.2f}x, lifetime {cl['_life_h']:.0f}h, "
              f"last-180d {cl['_rec_h']:.1f}h, {len(cl['members'])} members)")
        via_counts = Counter(m["via"] for m in cl["members"])
        print(f"  via: {dict(via_counts)}")
        top = cl["members"][:8]
        for m in top:
            print(f"    {m['affinity']:.3f}  {m['artist'][:32]:32} "
                  f"{m['hours']:6.1f}h  skip {m['skip_rate']:.0%}  "
                  f"last {m['last_played']}  ({m['via']})")
        if cl["anchor_playlists"]:
            print("  anchors: " + ", ".join(
                f"{a['name']} ({a['overlap_tracks']})"
                for a in cl["anchor_playlists"][:4]))
    print(f"\n=== revival pools ===")
    for name, items in pools.items():
        print(f"{name}: {len(items)}")
        for it in items[:5]:
            extra = (f"peak {it['peak_month']} ({it['peak_month_plays']} plays)"
                     if "peak_month" in it else f"last {it['last_played']}")
            print(f"    {it['artist'][:28]:28} - {it['track'][:36]:36} "
                  f"plays {it['plays']:3}  {extra}")


def main():
    import time
    t0 = time.time()
    taste_model, pools, clusters_out = build()
    summarize(taste_model, pools, clusters_out)
    print(f"\nwrote out/taste-model.json + out/revival-pools.json "
          f"in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
