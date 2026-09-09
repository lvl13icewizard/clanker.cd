"""Artist-level repeat guard for the served ledger.

The title-level served check (`zero_play._served_track_set`) answers "have we
served this exact track before". It cannot answer "have we served this
artist before", and for the Singles Rack that is the question that matters:
its leads are artist-level (`title: null`, per CONTRACTS.md "the curation
stage picks tracks"), so a title match can never fire and every previously
served artist walks straight back in. Issue 003 re-served five of ten.

Three states, deliberately not one:

  blocked   the artist has been played — either in the merged history or
            graded `played: true` in a previous issue's Ledger. They are not
            a stranger any more, so the Singles Rack's one promise ("an
            artist you have never played") no longer holds for them. They
            stay eligible for the modules built for familiar artists:
            Revival Desk and Catalog Room draw from the play history, not
            from here.

  cooldown  offered before and never played. Not a lie to offer again, just
            a repeat, so it expires: COOLDOWN_DAYS after the serve date the
            artist is eligible again.

  clear     never offered, or the cooldown has run out.

Only *discovery* contexts count as an offer. `new_this_week` is by
definition artists already deep in the log, and `the_mix` stores a radio
show in the artist field, so neither says anything about artist novelty.

Serve dates: `served_at` on the ledger item when present (serve_ledger
stamps it), else the issue's own date, else VOL1_DATE for Vol. 1 items.
An undatable item is treated as offered today, the conservative direction:
a repeat is suppressed rather than waved through on a missing field.

Library use:

    guard = build_guard()
    guard.status("Matt Duncan")   # -> {"state": "blocked", ...}
"""

import json
import re
from datetime import date, timedelta
from pathlib import Path

from ..lib import history
from ..lib.config import load_config
from ..lib.normalize import norm_artist
from . import served as served_mod

COOLDOWN_DAYS = 183  # six months

# Vol. 1 predates the issue series and its ledger items carry no date.
VOL1_DATE = "2026-07-19"

# Contexts that constitute "we offered you this artist as someone new".
DISCOVERY_CONTEXTS = ("singles_rack", "front_to_back", "critics_desk",
                      "catalog_room", "vol1")

_CONTEXT_RE = re.compile(r"^issue-(\d+):(.+)$")
# Ledger row labels are "Artist — Title" (em dash, per serve_ledger).
_LABEL_RE = re.compile(r"^(.*?)\s+—\s+", re.S)


def _context_kind(context):
    """The module a served item came from, or 'vol1'."""
    c = (context or "").strip()
    m = _CONTEXT_RE.match(c)
    return m.group(2) if m else c


def _context_issue(context):
    m = _CONTEXT_RE.match((context or "").strip())
    return int(m.group(1)) if m else None


def _issue_dates(issues_dir):
    """{issue number: date string} for every issue on disk."""
    out = {}
    for p in sorted(Path(issues_dir).glob("issue-*.json")):
        if ".bak" in p.name:
            continue
        try:
            doc = json.loads(p.read_text())
        except Exception:
            continue
        if isinstance(doc.get("issue"), int) and doc.get("date"):
            out[doc["issue"]] = doc["date"]
    return out


def _played_rows(played, rows, issue):
    for row in rows or []:
        if not row.get("played"):
            continue
        label = row.get("label") or ""
        hit = _LABEL_RE.match(label)
        name = (hit.group(1) if hit else label).strip()
        if name:
            played.setdefault(norm_artist(name), {
                "artist": name,
                "issue": issue,
                "plays": row.get("plays"),
                "first_play": row.get("first_play"),
            })


def _played_since(issues_dir, ledger_path=None):
    """Artists a Ledger graded as played, normalized.

    The merged history CSV is a periodic export, so it lags: an artist first
    played in the days after an issue went out is absent from it. The Ledger
    is built from ListenBrainz and does know. Without this, an artist the
    engine recommended last week and the reader actually played comes back
    as 'never played' the week after, which is how Matt Duncan happened.

    Two sources: the ledger modules of published issues, and the ledger
    built earlier in THIS run (out/ledger.json, grading the previous issue)
    which is not in any published issue yet — the press that reads it is
    the one being built.
    """
    played = {}
    for p in sorted(Path(issues_dir).glob("issue-*.json")):
        if ".bak" in p.name:
            continue
        try:
            doc = json.loads(p.read_text())
        except Exception:
            continue
        for m in doc.get("modules") or []:
            if m.get("type") == "ledger":
                _played_rows(played, m.get("rows"), doc.get("issue"))
    if ledger_path and Path(ledger_path).exists():
        try:
            doc = json.loads(Path(ledger_path).read_text())
        except Exception:
            doc = {}
        _played_rows(played, doc.get("picks"), doc.get("issue"))
    return played


def _parse_date(s):
    try:
        return date.fromisoformat(str(s)[:10])
    except Exception:
        return None


class Guard:
    """Artist -> repeat state, over one snapshot of the served ledger."""

    def __init__(self, offers, played, today, cooldown_days=COOLDOWN_DAYS,
                 history_lookup=None):
        self.offers = offers          # norm artist -> {"artist","last","contexts"}
        self.played = played          # norm artist -> ledger row info
        self.today = today
        self.cooldown_days = cooldown_days
        # Injectable so tests do not depend on the contents of the real
        # play-history export, which changes with every account sync.
        self.history_lookup = history_lookup or history.artist_played

    def status(self, artist):
        na = norm_artist(artist or "")
        offer = self.offers.get(na)
        row = self.played.get(na)
        hist = self.history_lookup(artist or "")

        if row or hist:
            return {
                "state": "blocked",
                "reason": ("played since it was served" if row and not hist
                           else "already in the play history"),
                "served_at": (offer or {}).get("last"),
                "contexts": (offer or {}).get("contexts", []),
                "ledger": row,
                "cooldown_until": None,
            }
        if offer:
            served_at = _parse_date(offer["last"]) or self.today
            until = served_at + timedelta(days=self.cooldown_days)
            if until > self.today:
                return {
                    "state": "cooldown",
                    "reason": f"served {offer['last']}, never played",
                    "served_at": offer["last"],
                    "contexts": offer["contexts"],
                    "ledger": None,
                    "cooldown_until": until.isoformat(),
                }
        return {
            "state": "clear",
            "reason": "cooldown expired" if offer else "never offered",
            "served_at": (offer or {}).get("last"),
            "contexts": (offer or {}).get("contexts", []),
            "ledger": None,
            "cooldown_until": None,
        }

    def blocked(self, artist):
        return self.status(artist)["state"] == "blocked"

    def summary(self):
        return {"offered_artists": len(self.offers),
                "played_since_serving": len(self.played),
                "cooldown_days": self.cooldown_days}


def build_guard(served=None, issues_dir=None, today=None, cooldown_days=COOLDOWN_DAYS,
                ledger_path=None):
    cfg = load_config()
    issues_dir = issues_dir or cfg["ISSUES_DIR"]
    if ledger_path is None:
        ledger_path = Path(cfg["OUT_DIR"]) / "ledger.json"
    served = served if served is not None else served_mod.load_or_build()
    today = today or date.today()
    dates = _issue_dates(issues_dir)

    offers = {}
    for item in served.get("items") or []:
        kind = _context_kind(item.get("context"))
        if kind not in DISCOVERY_CONTEXTS:
            continue
        name = item.get("artist")
        if not name:
            continue
        when = item.get("served_at")
        if not when:
            n = _context_issue(item.get("context"))
            when = dates.get(n) if n else (VOL1_DATE if kind == "vol1" else None)
        when = when or today.isoformat()
        na = norm_artist(name)
        rec = offers.setdefault(na, {"artist": name, "last": when, "contexts": []})
        if when > rec["last"]:
            rec["last"] = when
        if item.get("context") not in rec["contexts"]:
            rec["contexts"].append(item.get("context"))

    return Guard(offers, _played_since(issues_dir, ledger_path), today, cooldown_days)


def main():
    guard = build_guard()
    print(json.dumps(guard.summary(), indent=1))
    rows = []
    for na, offer in guard.offers.items():
        st = guard.status(offer["artist"])
        rows.append((st["state"], offer["artist"], st["reason"]))
    for state in ("blocked", "cooldown", "clear"):
        hits = [r for r in rows if r[0] == state]
        print(f"\n{state}: {len(hits)}")
        for _, artist, reason in sorted(hits)[:40]:
            print(f"  {artist:34s} {reason}")


if __name__ == "__main__":
    main()
