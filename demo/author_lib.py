"""Shared assembly for hand-authored persona catalogs.

A persona file declares its music as compact tuples and calls `write()`.
Lane `top` lists are derived from the artist table so no number is authored
twice, and affinity uses the taste model's own hours term.
"""

import json
import math
from pathlib import Path

CATALOGS = Path(__file__).resolve().parent / "catalogs"


def build_lanes(LANES, ARTISTS):
    out = []
    for (lid, name, hue, desc, state, members, hours, seeds, arc) in LANES:
        mem = sorted([a for a in ARTISTS if a[4] == lid], key=lambda a: -a[1])
        top = []
        for i, (nm, hrs, plays, skip, _l) in enumerate(mem[:10]):
            h_term = math.log1p(hrs) / math.log1p(61)
            aff = round(min(0.95, 0.55 * h_term + 0.25 * (1 - skip) + 0.20 * (0.9 - i * 0.04)), 3)
            top.append({"artist": nm, "hours": hrs, "plays": plays, "skip_rate": skip,
                        "affinity": aff, "via": "seed" if nm in seeds else
                        ("playlist" if i % 3 else "session")})
        out.append({"id": lid, "name": name, "hue": hue, "description": desc, "state": state,
                    "members": members, "hours": hours, "seeds": seeds, "arc": arc, "top": top})
    return out


def write(meta, LANES, ARTISTS, ISSUES, ALBUMS, CRITICS, SINGLES, MIXES,
          REVIVALS, RELEASES, CATALOGS_POOL):
    cat = dict(meta)
    cat["lanes"] = build_lanes(LANES, ARTISTS)
    cat["artists"] = [{"name": n, "hours": h, "plays": p, "skip_rate": s, "lane": l}
                      for (n, h, p, s, l) in ARTISTS]
    cat["issues"] = [{"n": i + 1, "title": t, "dek": d} for i, (t, d) in enumerate(ISSUES)]
    cat["albums"] = [{"artist": a, "title": t, "year": y, "label": lb, "lane": ln,
                      "anchor": an, "pitchfork": pf, "bnm": bnm, "note": nt}
                     for (a, t, y, lb, ln, an, pf, bnm, nt) in ALBUMS]
    cat["critics"] = [{"artist": a, "title": t, "year": y, "score": sc, "genre": g,
                       "lane": ln, "bnm": bnm, "anchor": an, "note": nt}
                      for (a, t, y, sc, g, ln, bnm, an, nt) in CRITICS]
    cat["singles"] = [{"artist": a, "title": t, "lane": l, "anchor": an, "note": nt}
                      for (a, t, l, an, nt) in SINGLES]
    cat["mixes"] = [{"show": s, "host": h, "date": d, "lane": l, "tracks_total": tt,
                     "known": k, "anchor": an, "note": nt}
                    for (s, h, d, l, tt, k, an, nt) in MIXES]
    cat["revivals"] = [{"artist": a, "title": t, "album": al, "plays": p,
                        "last_played": lp, "lane": l, "note": nt}
                       for (a, t, al, p, lp, l, nt) in REVIVALS]
    cat["releases"] = [{"artist": a, "title": t, "release_type": rt, "note": nt}
                       for (a, t, rt, nt) in RELEASES]
    cat["catalogs"] = [{"artist": a, "unique_tracks": ut, "top3_share": ts, "heard": hd,
                        "unheard": [{"title": t, "year": y} for (t, y) in uh], "note": nt}
                       for (a, ut, ts, hd, uh, nt) in CATALOGS_POOL]
    CATALOGS.mkdir(parents=True, exist_ok=True)
    out = CATALOGS / f"{cat['slug']}.json"
    out.write_text(json.dumps(cat, indent=1, ensure_ascii=False) + "\n")
    counts = {k: len(v) for k, v in cat.items() if isinstance(v, list) and k != "palette"}
    print(f"wrote {out.name}: {counts}")
    return out
