"""Check a demo persona catalog against demo/SPEC.md.

Structure, pool counts, lane references, digit-free notes, banned voice
patterns, duplicate picks. Exits 0 clean, 1 with one line per problem.

Run:  python3 demo/check_catalog.py demo/catalogs/<slug>.json
"""

import json
import re


def sentence_ends(txt):
    """Terminal punctuation that actually ends a sentence: a run of . ! ?
    followed by whitespace and a capital, or by the end of the text. Names
    like Fred again.. and Anderson .Paak no longer count as sentences."""
    return len(re.findall(r'[.!?]+(?=\s+["“(]?[A-Z]|\s*$)', txt))
import math
import re
import sys
from datetime import date
from pathlib import Path

DIGIT = re.compile(r"\d")
BANNED = ["—", " -- ", "banger", "slaps", "for fans of", "you might like",
          "curated", "sonic journey", "elevate"]
STATES = {"rising", "active", "dormant", "burned"}
VIA = {"seed", "playlist", "session"}
REL_TYPES = {"album", "ep", "single", "compilation"}


def main(argv=None):
    argv = argv or sys.argv[1:]
    if not argv:
        print(__doc__)
        return 2
    p = Path(argv[0])
    try:
        cat = json.loads(p.read_text())
    except Exception as ex:
        print(f"cannot parse {p}: {ex}")
        return 2
    errs = []
    e = errs.append

    # --- top level -------------------------------------------------------
    for k in ("slug", "name", "persona", "blurb", "issue_count", "first_date",
              "palette", "history", "per_issue", "lanes", "artists", "albums",
              "singles", "mixes", "critics", "revivals", "releases",
              "catalogs", "issues"):
        if k not in cat:
            e(f"missing top-level key: {k}")
    if errs:
        for x in errs:
            print(x)
        return 1

    if cat["slug"] != p.stem:
        e(f"slug {cat['slug']!r} does not match filename {p.stem!r}")
    K = cat["issue_count"]
    if not isinstance(K, int) or K < 8:
        e(f"issue_count should be an int >= 8, got {K!r}")
    try:
        d0 = date.fromisoformat(cat["first_date"])
        if d0.weekday() != 5:
            e(f"first_date {cat['first_date']} is a {d0.strftime('%A')}, not a Saturday")
    except Exception:
        e(f"first_date is not an ISO date: {cat['first_date']!r}")
    pal = cat["palette"]
    if not (isinstance(pal, list) and 4 <= len(pal) <= 6
            and all(re.fullmatch(r"#[0-9a-fA-F]{6}", c or "") for c in pal)):
        e("palette must be 4-6 '#rrggbb' strings")
    for k in ("plays", "hours", "tracks", "artists", "window_start", "window_end"):
        if k not in cat["history"]:
            e(f"history missing {k}")
    per = cat["per_issue"]
    for k in ("singles", "mixes", "revivals", "critics", "releases"):
        if not isinstance(per.get(k), int) or per[k] < 1:
            e(f"per_issue.{k} must be a positive int")
    if errs:
        for x in errs:
            print(x)
        return 1

    # --- lanes -----------------------------------------------------------
    lane_ids, hues = set(), []
    if not 8 <= len(cat["lanes"]) <= 12:
        e(f"want 8-12 lanes, got {len(cat['lanes'])}")
    for i, l in enumerate(cat["lanes"]):
        tag = f"lanes[{i}]"
        for k in ("id", "name", "hue", "description", "state", "members",
                  "hours", "seeds", "arc", "top"):
            if k not in l:
                e(f"{tag} missing {k}")
        if "id" in l:
            if l["id"] in lane_ids:
                e(f"{tag}: duplicate lane id {l['id']!r}")
            lane_ids.add(l["id"])
            if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", l["id"] or ""):
                e(f"{tag}: id {l['id']!r} is not kebab-case")
        if l.get("state") not in STATES:
            e(f"{tag}: state {l.get('state')!r} not one of {sorted(STATES)}")
        h = l.get("hue")
        if not isinstance(h, int) or not 0 <= h <= 359:
            e(f"{tag}: hue must be an int 0-359, got {h!r}")
        else:
            hues.append((h, l.get("id")))
        if not isinstance(l.get("seeds"), list) or not l["seeds"]:
            e(f"{tag}: seeds must be a non-empty list")
        top = l.get("top") or []
        if not 4 <= len(top) <= 12:
            e(f"{tag}: want 4-12 top members, got {len(top)}")
        for j, t in enumerate(top):
            for k in ("artist", "hours", "plays", "skip_rate", "affinity", "via"):
                if k not in t:
                    e(f"{tag}.top[{j}] missing {k}")
            if t.get("via") not in VIA:
                e(f"{tag}.top[{j}]: via {t.get('via')!r} not one of {sorted(VIA)}")
            if not isinstance(t.get("skip_rate"), (int, float)) or not 0 <= t.get("skip_rate", -1) <= 0.6:
                e(f"{tag}.top[{j}]: skip_rate should be a fraction 0-0.6, got {t.get('skip_rate')!r}")
    hues.sort()
    for (h1, i1), (h2, i2) in zip(hues, hues[1:]):
        if h2 - h1 < 18:
            e(f"lane hues too close: {i1} ({h1}) and {i2} ({h2}) are {h2 - h1} apart, want >= 18")
    if len(hues) > 1 and (hues[0][0] + 360 - hues[-1][0]) < 18:
        e(f"lane hues too close across 0: {hues[-1][1]} ({hues[-1][0]}) and {hues[0][1]} ({hues[0][0]})")
    states = {l.get("state") for l in cat["lanes"]}
    if len(states) < 2:
        e("every lane has the same state; a real reader has something rising and something quiet")

    # --- artists ---------------------------------------------------------
    names = set()
    if not 40 <= len(cat["artists"]) <= 90:
        e(f"want 40-90 history artists, got {len(cat['artists'])}")
    for i, a in enumerate(cat["artists"]):
        tag = f"artists[{i}]"
        for k in ("name", "hours", "plays", "skip_rate", "lane"):
            if k not in a:
                e(f"{tag} missing {k}")
        if a.get("name") in names:
            e(f"{tag}: duplicate artist {a.get('name')!r}")
        names.add(a.get("name"))
        if a.get("lane") not in lane_ids:
            e(f"{tag}: lane {a.get('lane')!r} is not a declared lane")
        if not isinstance(a.get("skip_rate"), (int, float)) or not 0 <= a.get("skip_rate", -1) <= 0.6:
            e(f"{tag}: skip_rate should be a fraction 0-0.6, got {a.get('skip_rate')!r}")
        pl, hr = a.get("plays"), a.get("hours")
        if isinstance(pl, (int, float)) and isinstance(hr, (int, float)) and pl:
            mins = hr * 60 / pl
            if not 1.2 <= mins <= 16:
                e(f"{tag}: {pl} plays / {hr} hours is {mins:.1f} min per play, implausible")

    # --- pools -----------------------------------------------------------
    want = {
        "albums": K, "singles": K * per["singles"], "mixes": K * per["mixes"],
        "critics": K * per["critics"], "revivals": K * 3,
        "releases": K * per["releases"], "catalogs": math.ceil(K * 0.6),
        "issues": K,
    }
    for pool, n in want.items():
        got = len(cat.get(pool) or [])
        if got != n:
            e(f"{pool}: want exactly {n} entries ({'issue_count' if n == K else 'issue_count x per-issue'}), got {got}")

    def check_note(txt, tag, required=False):
        """Notes are optional: without one the generator writes sturdy
        receipt prose, exactly as the engine does in --no-llm mode."""
        if txt is None:
            if required:
                e(f"{tag}: note is required")
            return
        if not isinstance(txt, str) or not txt.strip():
            e(f"{tag}: note must be a non-empty string")
            return
        if DIGIT.search(txt):
            e(f"{tag}: note contains a digit (all numbers come from receipts): {txt[:70]!r}")
        low = txt.lower()
        for b in BANNED:
            if b in low or b in txt:
                e(f"{tag}: note contains banned {b!r}: {txt[:70]!r}")
        if sentence_ends(txt) > 2:
            e(f"{tag}: note runs longer than two sentences: {txt[:70]!r}")

    def check_why(txt, tag):
        """A written paragraph that replaces note + receipt line whole. It
        may carry numbers, which the issue validator checks against the
        item's receipts at build time; the voice bans still apply."""
        if txt is None:
            return
        if not isinstance(txt, str) or not txt.strip():
            e(f"{tag}: why must be a non-empty string")
            return
        low = txt.lower()
        for b in BANNED:
            if b in low or b in txt:
                e(f"{tag}: why contains banned {b!r}: {txt[:70]!r}")
        if sentence_ends(txt) > 4:
            e(f"{tag}: why runs longer than four sentences: {txt[:70]!r}")

    def check_anchor(a, tag):
        if a not in names:
            e(f"{tag}: anchor {a!r} is not in artists[]")

    def check_lane(l, tag):
        if l not in lane_ids:
            e(f"{tag}: lane {l!r} is not a declared lane")

    seen_picks = {}

    def uniq(key, tag):
        k = re.sub(r"\s+", " ", str(key).strip().lower())
        if k in seen_picks:
            e(f"{tag}: duplicate pick {key!r} (already at {seen_picks[k]})")
        else:
            seen_picks[k] = tag

    for i, x in enumerate(cat["albums"]):
        tag = f"albums[{i}]"
        for k in ("artist", "title", "year", "label", "lane", "anchor", "note"):
            if k not in x:
                e(f"{tag} missing {k}")
        check_note(x.get("note"), tag, required=True)  # the week's lead always speaks
        check_why(x.get("why"), tag)
        check_anchor(x.get("anchor"), tag)
        check_lane(x.get("lane"), tag)
        uniq(f"{x.get('artist')} / {x.get('title')}", tag)

    for i, x in enumerate(cat["singles"]):
        tag = f"singles[{i}]"
        for k in ("artist", "title", "lane", "anchor", "note"):
            if k not in x:
                e(f"{tag} missing {k}")
        check_note(x.get("note"), tag)
        check_why(x.get("why"), tag)
        if not x.get("label"):
            check_anchor(x.get("anchor"), tag)  # a label lead needs no anchor artist
        check_lane(x.get("lane"), tag)
        uniq(f"{x.get('artist')} / {x.get('title')}", tag)

    for i, x in enumerate(cat["mixes"]):
        tag = f"mixes[{i}]"
        for k in ("show", "host", "date", "lane", "tracks_total", "known", "anchor", "note"):
            if k not in x:
                e(f"{tag} missing {k}")
        check_note(x.get("note"), tag)
        check_why(x.get("why"), tag)
        check_anchor(x.get("anchor"), tag)
        check_lane(x.get("lane"), tag)
        tt, kn = x.get("tracks_total"), x.get("known")
        if isinstance(tt, int) and isinstance(kn, int) and not 0 < kn < tt:
            e(f"{tag}: known ({kn}) must be > 0 and < tracks_total ({tt})")
        uniq(f"mix {x.get('show')} {x.get('date')}", tag)

    for i, x in enumerate(cat["critics"]):
        tag = f"critics[{i}]"
        for k in ("artist", "title", "year", "score", "genre", "lane", "bnm", "anchor", "note"):
            if k not in x:
                e(f"{tag} missing {k}")
        check_note(x.get("note"), tag)
        check_anchor(x.get("anchor"), tag)
        check_lane(x.get("lane"), tag)
        s = x.get("score")
        if not isinstance(s, (int, float)) or not 6 <= s <= 10:
            e(f"{tag}: score should be 6-10, got {s!r}")
        uniq(f"{x.get('artist')} / {x.get('title')}", tag)

    for i, x in enumerate(cat["revivals"]):
        tag = f"revivals[{i}]"
        for k in ("artist", "title", "album", "plays", "last_played", "lane", "note"):
            if k not in x:
                e(f"{tag} missing {k}")
        check_note(x.get("note"), tag)
        check_lane(x.get("lane"), tag)
        if not isinstance(x.get("plays"), int) or not 15 <= x.get("plays", 0) <= 120:
            e(f"{tag}: plays should be 15-120, got {x.get('plays')!r}")
        try:
            date.fromisoformat(x["last_played"])
        except Exception:
            e(f"{tag}: last_played is not an ISO date: {x.get('last_played')!r}")
        uniq(f"{x.get('artist')} / {x.get('title')}", tag)

    for i, x in enumerate(cat["releases"]):
        tag = f"releases[{i}]"
        for k in ("artist", "title", "release_type", "note"):
            if k not in x:
                e(f"{tag} missing {k}")
        check_note(x.get("note"), tag)
        check_anchor(x.get("artist"), tag)
        if x.get("release_type") not in REL_TYPES:
            e(f"{tag}: release_type {x.get('release_type')!r} not one of {sorted(REL_TYPES)}")
        uniq(f"{x.get('artist')} / {x.get('title')}", tag)
    noted = sum(1 for x in cat["releases"] if x.get("note"))
    if cat["releases"] and not 0.25 <= noted / len(cat["releases"]) <= 0.75:
        e(f"releases: {noted}/{len(cat['releases'])} carry a note; want roughly a third to two thirds")

    for i, x in enumerate(cat["catalogs"]):
        tag = f"catalogs[{i}]"
        for k in ("artist", "unique_tracks", "top3_share", "heard", "unheard", "note"):
            if k not in x:
                e(f"{tag} missing {k}")
        check_note(x.get("note"), tag, required=True)
        check_anchor(x.get("artist"), tag)
        if not isinstance(x.get("top3_share"), int) or not 20 <= x.get("top3_share", 0) <= 80:
            e(f"{tag}: top3_share should be 20-80 (a percent), got {x.get('top3_share')!r}")
        if not isinstance(x.get("heard"), list) or len(x["heard"]) < 3:
            e(f"{tag}: heard needs at least 3 titles")
        un = x.get("unheard") or []
        if not 2 <= len(un) <= 4:
            e(f"{tag}: want 2-4 unheard albums, got {len(un)}")
        for j, u in enumerate(un):
            if "title" not in u or "year" not in u:
                e(f"{tag}.unheard[{j}] needs title and year")
            else:
                uniq(f"{x.get('artist')} / {u['title']}", f"{tag}.unheard[{j}]")

    titles = set()
    for i, x in enumerate(cat["issues"]):
        tag = f"issues[{i}]"
        if x.get("n") != i + 1:
            e(f"{tag}: n should be {i + 1}, got {x.get('n')!r}")
        t, dek = x.get("title"), x.get("dek")
        if not t or not isinstance(t, str):
            e(f"{tag}: title required")
        else:
            if t.lower() in titles:
                e(f"{tag}: duplicate issue title {t!r}")
            titles.add(t.lower())
            if len(t.split()) > 4:
                e(f"{tag}: title {t!r} is longer than four words")
            if re.search(r"\b(pressing|edition|volume|issue|vol)\b", t, re.I):
                e(f"{tag}: title {t!r} reads as a numbered series")
        if not dek or not isinstance(dek, str):
            e(f"{tag}: dek required")
        else:
            if DIGIT.search(dek):
                e(f"{tag}: dek contains a digit: {dek[:70]!r}")
            for b in BANNED:
                if b in dek.lower() or b in dek:
                    e(f"{tag}: dek contains banned {b!r}")
            if sentence_ends(dek) > 2:
                e(f"{tag}: dek runs longer than two sentences")

    # Bare pools are allowed, empty voice is not: some share must speak.
    for pool in ("singles", "critics", "mixes", "revivals"):
        rows = cat.get(pool) or []
        noted = sum(1 for x in rows if x.get("note"))
        if rows and noted / len(rows) < 0.2:
            e(f"{pool}: only {noted}/{len(rows)} carry a note; at least a fifth should")

    for x in errs:
        print(x)
    if not errs:
        print(f"ok: {p.name} — {cat['name']} ({cat['slug']}), {K} issues, "
              f"{len(cat['lanes'])} lanes, {len(cat['artists'])} history artists, "
              f"{len(seen_picks)} distinct picks")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
