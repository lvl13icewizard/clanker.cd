# Demo persona catalog — the contract

A **catalog** is one JSON file describing a fictional (or fictionalised)
Clanker.CD reader: their listening lanes, the music their weekly issues drew
from, and the names of those issues. `demo/build_demo.py` turns a catalog
into a run of weekly issues that the real site renders and the real
receipts validator accepts.

You author the *music and the words*. The generator adds every number, every
receipt, the dates, the ledger grades and the cover art. That split is the
whole reason this works: you never have to keep statistics consistent.

## Hard rules

1. **Real music only.** Every artist, album, track, label, radio show and
   release must actually exist. No invented records, no invented album
   titles, no plausible-sounding fakes. A demo that name-drops a record
   that does not exist is worse than an empty demo.
2. **No digits anywhere in a `note`.** Not "1,200 plays", not "his 1985
   debut", not "two decades". Years and counts live in structured fields
   and get rendered from receipts by the generator. Spell small numbers as
   words if you truly need them ("a pair of", "seven"). This rule is what
   makes the receipts validator pass.
3. **Voice** (see `engine/editorial/VOICE.md`, all of it): warm, plain,
   specific, about the music. **No em dashes.** No twist endings, no
   setup-and-reveal. No system talk: never mention the engine, ranking,
   verification, "the record", "the log", "lanes" as machinery. No
   streaming diction: banger, slaps, "for fans of", curated, sonic journey.
4. **Notes are one sentence.** Two short ones at most. They describe what
   the music sounds like or why it belongs to this listener. The generator
   appends the receipt sentence, so do not write "you've played X a lot" —
   write what the music *is*.
   **A note may be `null`.** Without one, the generator writes the pick's
   sturdy receipt prose alone, which is exactly what the engine does in
   `--no-llm` mode and reads as a person, not a report. Use that freedom to
   spend your writing where it shows: every album of the week and every
   catalog room speaks, and at least a fifth of every other pool. Bare rows
   are a legitimate choice, thin writing is not.
5. **No repeats.** An artist may appear in several modules across a run,
   but never the same *record or track twice* anywhere in the catalog. The
   product promise is that nothing is ever recommended twice.
6. Every `lane` value must be an id declared in `lanes`.

## File

Write to `demo/catalogs/<slug>.json`. Then run:

```
python3 demo/check_catalog.py demo/catalogs/<slug>.json
```

It checks the schema, the pool counts, digit-free notes, lane references,
duplicate picks and em dashes. Fix everything it reports before finishing.

## Schema

```json
{
  "slug": "kebab-case, matches the filename",
  "name": "Display name of the persona, 1-3 words",
  "persona": "One line: who this listener is.",
  "blurb": "Two sentences for the demo switcher card. Third person.",
  "issue_count": 14,
  "first_date": "2026-05-16",            // a SATURDAY; issues run weekly from here
  "palette": ["#hex", "#hex", "#hex", "#hex"],  // 4-6 colours; this persona's cover signature
  "history": {
    "plays": 88400, "hours": 3120.5, "tracks": 24100, "artists": 6480,
    "window_start": "2017-02-11", "window_end": "2026-08-15"
  },
  "per_issue": {"singles": 6, "mixes": 2, "revivals": 3, "critics": 4, "releases": 6},

  "lanes": [
    {
      "id": "kebab-case-id",
      "name": "Display Name",
      "hue": 240,                        // 0-359, >= 18 apart from every other lane here
      "description": "One sentence naming what holds the lane together.",
      "state": "active",                 // rising | active | dormant | burned  (state TODAY)
      "members": 34,
      "hours": 412.5,
      "seeds": ["Artist", "Artist", "Artist"],
      "arc": "One sentence on how this lane moved over the run.",
      "top": [
        {"artist": "Name", "hours": 50.9, "plays": 917, "skip_rate": 0.12, "affinity": 0.88, "via": "seed"}
      ]
    }
  ],

  "artists": [
    {"name": "Khruangbin", "hours": 62.8, "plays": 1252, "skip_rate": 0.09, "lane": "cosmic-groove"}
  ],

  "albums": [
    {"artist": "", "title": "", "year": 2025, "label": "", "lane": "", "anchor": "an artists[].name",
     "pitchfork": 8.4, "bnm": true, "note": ""}
  ],
  "singles": [
    {"artist": "", "title": "", "lane": "", "anchor": "an artists[].name", "note": ""}
  ],
  "mixes": [
    {"show": "", "host": "", "date": "2026-07-25", "lane": "", "tracks_total": 34,
     "known": 9, "anchor": "an artists[].name", "note": ""}
  ],
  "critics": [
    {"artist": "", "title": "", "year": 1985, "score": 9.1, "genre": "", "lane": "",
     "bnm": false, "anchor": "an artists[].name", "note": ""}
  ],
  "revivals": [
    {"artist": "", "title": "", "album": "", "plays": 55, "last_played": "2024-06-27",
     "lane": "", "note": ""}
  ],
  "releases": [
    {"artist": "an artists[].name", "title": "", "release_type": "album",
     "note": ""}
  ],
  "catalogs": [
    {"artist": "an artists[].name", "unique_tracks": 34, "top3_share": 39,
     "heard": ["Title", "Title", "Title"],
     "unheard": [{"title": "", "year": 2021}, {"title": "", "year": 2023}],
     "note": ""}
  ],
  "issues": [
    {"n": 1, "title": "Two or three words", "dek": "One or two sentences."}
  ]
}
```

## Field notes

- **lanes**: 8 to 12 of them. This is the listener's taste, split into the
  rooms they actually live in. Give each a `top` list of 4 to 12 member
  artists with plausible stats (hours and plays should agree roughly:
  ~3 minutes a play). `affinity` runs 0.3 to 0.95. `via` is `seed`,
  `playlist` or `session`. States should not all be `active`: a real
  reader has something rising and something going quiet.
- **artists**: 40 to 90 names, spread across the lanes. These are the
  *history* the receipts are drawn from, so they must be artists this
  person genuinely plays a lot. Every `anchor` field elsewhere must name
  one of these. Vary the numbers: a few big (1,000+ plays), many mid,
  some small. `skip_rate` is 0.03 to 0.45 and it is characterful (a
  devotional artist skips at 0.06; a difficult one at 0.35).
- **albums** (album of the week, one per issue): `issue_count` entries.
  These should be excellent, real, mostly recent-ish records this person
  has never played. `pitchfork` and `bnm` optional; use `null` when the
  record was never reviewed.
- **singles**: `issue_count × per_issue.singles` entries. One track each
  from an artist the reader has never played, each pointing at a lane and
  an anchor they do play. Sequence matters less than variety: across a
  single issue's slice, the lanes should differ.
- **mixes**: `issue_count × 2`. Real radio shows (NTS, Rinse, Worldwide
  FM, Dublab, The Lot, Balamii, Do!! You!!!). `known` < `tracks_total`,
  typically a quarter to a third of it.
- **critics**: `issue_count × per_issue.critics`. Highly-rated records,
  usually older, that this reader has never played but obviously should
  have. This is the canon-backfill module: roots of the things they love.
- **revivals**: `issue_count × 3`. Tracks from *their own* history that
  they played hard and then dropped. Real tracks by artists in `artists`
  (or adjacent). `plays` 20 to 90, `last_played` a date one to four years
  before `first_date`.
- **releases** (new this week): `issue_count × per_issue.releases`. Real
  recent-ish releases by artists in `artists`. `release_type` is `album`,
  `ep`, `single` or `compilation`. Roughly half should have `note: null`
  (the module lists more than it comments on).
- **catalogs**: `ceil(issue_count × 0.6)` entries. An artist the reader
  plays constantly but narrowly: real heard titles, real unheard albums.
- **issues**: exactly `issue_count` entries, `n` from 1 upward. Titles are
  playlist-style names, two or three words, **never a numbered series**
  ("Third Pressing" is banned) and never the same shape twice in a row.
  Deks rotate angle week to week: the music itself, a named artist or two,
  the thought behind the picks, a trend, a reaction to last week's
  results. One or two sentences, shorter than feels natural, and never an
  inventory of what is in the issue.

## What good looks like

A note for a single:

> "Ohio soul that moves like the Thai funk you already live in, unhurried
>  and sung slightly behind the beat."

A note for a critics pick:

> "The Berlin dub techno plates every ambient producer you love was
>  quietly rebuilding for years."

A dek:

> "Ana Roxanne sets the tone, a week for sitting still, with a few loud
>  exceptions from the bass and punk corners."
