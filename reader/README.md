# reader

Your personal edition. A thin shell around the shared reader in
`../site/reader`, serving `../site/public` live, so an issue shows up here
the moment the press writes it.

```
npm install
npx playwright install chromium   # once; paints the issue covers
npm run dev                       # http://127.0.0.1:3010
```

The server binds to the local machine only. Nothing here is deployed.

- `/`: your desk, the latest issue and the shelf of every issue pressed
- `/?view=issue&n=7`: an issue, section by section, with its companion playlist
- `/?view=archive`: the collection
- `/?view=lanes`: your lanes, the artists in them, and where they led
- `/?view=releases`: the release calendar for the artists you play
