# site

The public site at clanker.cd and the reader it shares with your personal
app.

- `reader/`: the reader itself. `App.jsx`, `styles.css` and `util.js` render
  an issue, the desk, the collection and the lanes. `reader/cover/render.js`
  paints issue covers; the engine and the demo builder both call it.
- `src/`: the public landing (`Landing.jsx`, `ListeningRoom.jsx`), the demo
  room and the shell that routes `?demo=<slug>` to a persona.
- `public/`: fonts, the mascot and brand assets, the Saturday film, the
  demo datasets the builder writes, and `issues/` where the engine writes
  your own (never committed).

## Run

```
npm install
npm run dev          # http://127.0.0.1:3011
npm run build:public # dist/ with every personal issue pruned
```

The public build ships demo data only: `scripts/prune-public.mjs` removes
everything under `dist/issues` except the synthetic fixture, and drops the
live pose set. `vercel.json` deploys that build.

Your own issues are read by the personal app in `../reader`, which serves
this directory's `public/` live.
