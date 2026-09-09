"""Module-specific repeat policies derived from the served ledger.

The served ledger is an exposure log: one row per item per issue module,
stamped with the issue's date (engine.serve_ledger). What "served before"
should mean differs by module, and audit F16 found the old readers each
inventing their own answer: Critics Desk and Catalog Room banned an artist
forever for having appeared ANYWHERE in the file, release announcements
included; NTS banned a show forever while its comment promised one issue
out; Revival Desk never looked at all.

The policies, each an expiring window over the exposure log:

  artist (discovery)  repeat_guard.Guard: blocked once played, COOLDOWN_DAYS
                      after an unplayed offer. Consulted by the Singles Rack
                      and, through here, by Critics Desk.
  album               a (artist, title) pair offered by Critics Desk or as
                      the album of the week sits out ALBUM_COOLDOWN_DAYS.
  catalog             an artist whose Catalog Room ran sits out
                      CATALOG_COOLDOWN_DAYS. Only catalog_room exposures
                      count; the module is built from familiar artists, so
                      the discovery guard does not apply to it.
  show                an NTS episode (URL, title) is never re-served; the
                      SHOW it came from sits out SHOW_SITOUT_ISSUES issues.
  revival             a (artist, track) pair the desk offered within
                      REVIVAL_COOLDOWN_ISSUES issues sits out.

Undatable exposures are treated as served today, the conservative direction.
"""

from datetime import date, timedelta

from ..lib.normalize import norm_artist, norm_title
from .repeat_guard import VOL1_DATE, _context_issue, _context_kind, _issue_dates

ALBUM_COOLDOWN_DAYS = 365
CATALOG_COOLDOWN_DAYS = 365
SHOW_SITOUT_ISSUES = 1


def exposures(served, issues_dir=None, today=None):
    """Flatten the ledger into dated rows: {artist, title, uri, kind, issue,
    served_at, na, nt}."""
    dates = _issue_dates(issues_dir) if issues_dir else {}
    today_s = (today or date.today()).isoformat()
    out = []
    for it in served.get("items") or []:
        kind = _context_kind(it.get("context"))
        n = _context_issue(it.get("context"))
        when = it.get("served_at") or dates.get(n) or \
            (VOL1_DATE if kind == "vol1" else None) or today_s
        out.append({
            "artist": it.get("artist"), "title": it.get("title"),
            "uri": it.get("uri"), "kind": kind, "issue": n,
            "served_at": str(when)[:10],
            "na": norm_artist(it.get("artist") or ""),
            "nt": norm_title(it.get("title") or ""),
        })
    return out


def _within(exps, kinds, days, today=None):
    cutoff = ((today or date.today()) - timedelta(days=days)).isoformat()
    return [e for e in exps if e["kind"] in kinds and e["served_at"] >= cutoff]


def artists_within(exps, kinds, days, today=None):
    return {e["na"] for e in _within(exps, kinds, days, today) if e["na"]}


def pairs_within(exps, kinds, days, today=None):
    return {(e["na"], e["nt"]) for e in _within(exps, kinds, days, today) if e["na"]}


def revival_pairs_recent(served, issue_n, within_issues):
    """(norm artist, norm track) pairs the Revival Desk offered in the last
    `within_issues` issues before issue_n. Rows with no issue number are
    included (undatable = recent)."""
    out = set()
    for it in served.get("items") or []:
        if _context_kind(it.get("context")) != "revival_desk":
            continue
        n = _context_issue(it.get("context"))
        if n is not None and n < issue_n - within_issues:
            continue
        out.add((norm_artist(it.get("artist") or ""),
                 norm_title(it.get("title") or "")))
    return out


def show_exclusions(served, sitout_issues=SHOW_SITOUT_ISSUES):
    """(urls, titles, shows) for the_mix. Episode URLs and titles are
    excluded for good; show aliases/names only from the most recent
    `sitout_issues` issues that carried a mix."""
    urls, titles, shows = set(), set(), set()
    rows = [it for it in served.get("items") or []
            if _context_kind(it.get("context")) == "the_mix"]
    issues = [_context_issue(it.get("context")) for it in rows]
    issues = [n for n in issues if n is not None]
    floor = (max(issues) - sitout_issues + 1) if issues else None
    for it in rows:
        u = str(it.get("uri") or "").split("?")[0]
        if u:
            urls.add(u)
        if it.get("title"):
            titles.add(str(it["title"]).strip().lower())
        n = _context_issue(it.get("context"))
        recent = floor is None or n is None or n >= floor
        if not recent:
            continue
        if u:
            parts = u.rstrip("/").split("/")
            if "shows" in parts:
                i = parts.index("shows")
                if i + 1 < len(parts):
                    shows.add(parts[i + 1])
        if it.get("artist"):
            shows.add(str(it["artist"]).strip().lower())
    return urls, titles, shows
