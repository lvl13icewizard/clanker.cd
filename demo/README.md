# Demo personas

Four synthetic readers with months of weekly issues each, for UX testing,
demos, product video and screenshots. The app renders them through exactly
the same code as the real thing: open `/?view=demo`, pick a persona, and
every view (reader, archive, list, lane pages) reads as that person.

|  | persona | issues | shape |
|---|---|---|---|
| `andrew` | the owner's own listening, four months on | 18 | twelve real lanes carried forward, one burned out, house and garage grown into the gap |
| `electronic` | Mara, deep dance music | 13 | dub techno, UK bass, jungle, ambient; hard techno burned out in June |
| `altindie` | June, records not playlists | 11 | post-punk, shoegaze, slowcore, nineties indie; a folk habit rising |
| `pop` | Tasha, mainstream and unembarrassed | 9 | big pop, chart R&B, top-forty rap, country rising; every pick one step sideways |

## What is real and what is not

- **Every record, artist, radio show and release is real.** Nothing is
  invented. The picks are chosen to fit the persona and to be plausible
  things that reader has not played.
- **Every listening statistic is modelled.** Plays, hours, skip rates, lane
  sizes and ledger grades are composed by the generator. They are internally
  consistent and pass the real receipts validator, but they are not anyone's
  export. The `andrew` persona starts from the real taste model and is
  shifted off it deliberately.
- **No Spotify anything.** Demo playlists are marked `status: "demo"`, carry
  no URL, and render as a bracket with no destination. Item links point at a
  Spotify *search* for the record, which always resolves to the real thing
  and can never be a dead id.
- **Cover art is real** where it could be resolved (iTunes, MusicBrainz and
  the Cover Art Archive by name; the NTS show index for radio), which is
  about five in six picks. Anything unresolved renders the app's
  artwork-unavailable tile, never a wrong cover.
- **Radio shows without a lookup** (BBC, Apple Music, Rinse and the rest)
  get a plain generated tile in the persona's palette rather than a column
  of empty frames. It reads as house artwork and never as a station's logo,
  and those mixes carry no link rather than an invented one.
- **Issue covers are generated** by the site's own canvas renderer, with a
  palette and a recipe per persona, so each archive has its own look.

## Building

```
python3 demo/author_andrew.py && python3 demo/author_andrew_pools.py
python3 demo/author_electronic.py
python3 demo/author_altindie.py
python3 demo/author_pop.py
python3 demo/build_demo.py --all      # catalogs -> issues (validated)
python3 demo/covers.py                # issue covers, one browser for all
python3 demo/art.py                   # real cover art, cached on disk
python3 demo/mix_tiles.py             # house tiles for shows art.py could not find
```

`build_demo.py` runs the real `engine.editorial.validate` on every issue it
writes, reports any artist appearing twice in one issue, and repairs those by
moving single picks between issues. `art.py` is safe to re-run: every lookup
is cached in `demo/art-cache.json`.

## Layout

- `SPEC.md` — the catalog contract (what a persona file must contain).
- `check_catalog.py` — validates a catalog against the spec: pool counts,
  digit-free notes, lane references, duplicate picks, voice bans.
- `catalogs/*.json` — the authored catalogs. Committed; this is the source.
- `author_*.py` — the hand-authored music, as compact tuples. Committed.
- `author_lib.py` — shared assembly (lane `top` lists are derived from the
  artist table so no number is authored twice).
- `build_demo.py` — catalog to issues: every receipt, date, ledger grade and
  the prose that quotes them.
- `covers.py` + `render_covers.mjs` — batch cover rendering.
- `art.py` — real cover-art resolution.
- `mix_tiles.py` — generated tiles for radio shows with no resolvable art.

Generated output lives in `site/public/demo/<slug>/` and is gitignored: it
is fully reproducible from the catalogs.

## Notes for capture

- `?clean=1` on any demo route hides the persona badge. The demo room has a
  **capture mode** toggle that sets it for every link.
- Each persona's covers share a palette and a gradient recipe, and vary by
  issue number, so a gallery reads as one publication.
- The `andrew` catalog embeds an approximation of the owner's real listening.
  It is committed here because this repo has no remote; review it before any
  public release.
