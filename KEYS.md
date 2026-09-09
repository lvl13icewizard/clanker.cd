# Adding your keys

Keys go in `.env` at the project root — **never into a chat window, a commit,
or a shell command** (shell history keeps a copy). `.env` is gitignored.

Open it:

```bash
open .env
```

Fill in the lines that are already there:

```
LASTFM_API_KEY=<paste>
LISTENBRAINZ_TOKEN=<paste>
```

Then verify — this reports whether each key works, printing only a length and
last-4 fingerprint, never the value:

```bash
python3 -m engine.checkkeys
```

Expected when both are live:

```
  LASTFM_API_KEY       ok  [32 chars, ends ab12] live — Khruangbin similar: ...
  LISTENBRAINZ_TOKEN   ok  [36 chars, ends cd34] valid — user 'you'
```

## Where each key comes from

- **Last.fm** — https://www.last.fm/api/account/create (instant). The page also
  shows a *shared secret*; this project never needs it (that's for write/scrobble
  auth), so leave it out of `.env` entirely.
- **ListenBrainz** — https://listenbrainz.org/settings/ , "User token".

## What each key unlocks

| Key | Required? | Effect if absent |
|---|---|---|
| `LASTFM_API_KEY` | no | harvest runs without similar-artist fan-out — the pool gets thinner, everything else works |
| `LISTENBRAINZ_TOKEN` | no | bonus tier only. The LB **labs** APIs this engine actually uses (similar-artists, tag lookup, MBID→Spotify) need no account at all |
| `ANTHROPIC_API_KEY` | no | reserved — no engine code calls Anthropic yet. Prose reaches an issue either from a copy file written outside the engine (`--copy` / `recopy`, which is what an agent session pressing the issue produces) or from the receipt-joined template (`--no-llm`). A bring-your-own-key writer would emit the same copy file and go through the same validator. |

## Key hygiene in this codebase

`engine/lib/http.py` redacts credential-bearing query params (`api_key`,
`token`, `secret`, …) before writing the cache sidecar, so a key passed in a
URL never lands in `cache/*.meta`. If you add an adapter that authenticates a
new way, keep that property.
