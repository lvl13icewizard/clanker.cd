# clanker.cd

A personalized music journal, pressed by your robot.

clanker.cd reads your entire Spotify streaming history and presses you an
issue of new music every Saturday: an album to sit inside, ten singles from
artists you have never played, two radio hours, second chances, the critics'
backfill, a catalog room, and a report card grading last week's picks
against what you actually played. Every number in the prose traces to a
computed receipt, and every recommendation is verified never-played against
your full history. No accounts, no uploads, no servers. It runs on your
machine, and the issue reads in your browser.

The public site with four demo readers is at [clanker.cd](https://clanker.cd).

## What you need

- Python 3.10 or newer. The engine is standard library only.
- Node 18 or newer, for the reader and the cover renderer.
- Your Spotify Extended Streaming History. Request it at
  [spotify.com/account/privacy](https://www.spotify.com/account/privacy/)
  under "Extended streaming history". Spotify emails a zip within a few
  days; it covers the life of the account.

Optional, each one widening a part of the issue: a free Last.fm API key, a
ListenBrainz account, and a Spotify developer app so the companion playlist
lands in your library. See `KEYS.md` and `SPOTIFY-APP.md`.

## Set up

```
git clone https://github.com/lvl13icewizard/clanker.cd
cd clanker.cd
cp .env.example .env
```

Turn the export into the history the engine reads. Point it at the zip, or
at the unzipped folder; several exports merge.

```
python3 -m engine.model.ingest_export ~/Downloads/my_spotify_data.zip --out ~/clanker-history
```

Set `SPOTIFY_CLEAN_DIR` in `.env` to that folder. That is the
only required setting.

Install the reader once. Playwright's Chromium is what paints the covers.

```
cd reader && npm install && npx playwright install chromium && cd ..
```

## Press an issue

```
./weekly.sh --dry-run
```

Ten minutes or so on free, cached APIs. It builds the taste model from your
history, harvests candidates, verifies every one against everything you have
played, selects, writes the issue with template prose, validates every
number against its receipt, resolves cover art, and paints the issue cover.
Nothing leaves your machine. Drop `--dry-run` once Spotify credentials are
in place and the companion playlist is created from exact track URIs.

Then read it:

```
cd reader && npm run dev
```

Open http://127.0.0.1:3010. Your desk, the issue, the collection, your lanes.

## The copy

The engine writes sturdy sentences from receipts on its own. The issues
read best when something with judgment writes the prose: a coding agent, a
script with your own model key, or you. The contract is one file per issue,
`out/copy-NNN.json`, in the shape the writer takes, applied with:

```
python3 -m engine.editorial.recopy --n 7 --copy out/copy-007.json
```

The validator refuses any number the receipts do not carry, whoever wrote
it. The voice rules are in `engine/editorial/VOICE.md`. `AUTOPRESS.md` is
the full Saturday procedure an agent follows, step by step.

## Your lanes

The taste model clusters your listening into lanes. `engine/model/seeds.json`
holds the seed artists per lane and ships with the author's; the builder
expands membership from your own playlists and sessions, but the lanes read
better when the seeds are yours. Edit the file before the first press.

## Layout

```
engine/   the pipeline: history, taste model, ledger, harvest, verify,
          select, issue, resolve, art, covers, publish
reader/   your personal app, a thin shell over site/reader
site/     the shared reader, the public site and the demo personas
demo/     four synthetic readers, generated from hand-authored catalogs
issues/   your pressed issues (never committed)
```

## More

- `AUTOPRESS.md`: the weekly press, step by step
- `KEYS.md`: the optional keys and what each unlocks
- `SPOTIFY-APP.md`: the Spotify developer app for playlist delivery
- `demo/README.md`: the personas and how to rebuild them
- `engine/editorial/VOICE.md`: how an issue is written

## License

MIT.
