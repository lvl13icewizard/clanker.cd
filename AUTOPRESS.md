# Autopress: the weekly press

Every Saturday morning a scheduled agent session presses the week's issue
end to end: build dry, write the copy, publish. This file is the procedure
that session follows. A person can follow it too.

The engine does everything mechanical for free (`weekly.sh`). The one part
that is editorial judgment is the copy pass: the issue's name, the dek, and
every "why", written to `engine/editorial/VOICE.md`. That is why the press
is a Claude session and not a cron line around a shell script.

## Ground rules

- Work from this directory; call everything by absolute path. Never `cd`
  inside a compound shell command.
- Never `git commit` or `git push` during a press.
- A press normally touches `out/`, `issues/`, `site/public/issues/`,
  `served/` only. But when the press is BLOCKED by a defect in the engine
  itself, fixing the machine is sanctioned, with discipline: stop before
  publishing anything wrong; fix the root cause, not the symptom; cover the
  fix with hermetic tests; write down what broke, why, what changed and what
  is still open; leave every change uncommitted for the owner to review; and
  only then resume the press on the rebuilt issue. Fixing is for unblocking,
  never for refactoring or improving in passing.
- Prose rules live in `engine/editorial/VOICE.md`. Receipts are law: the
  validator refuses any number the receipts do not carry.
- On any failure below: stop, publish nothing further, and tell the owner
  what broke and where it stopped. A late issue beats a broken one.

## Procedure

1. **Preflight.**
   - `python3 -m engine.checkkeys` for a key status report (never prints values).
   - Idempotence guard: read the newest `issues/issue-*.json`; if its
     `date` is less than 5 days old, the week is already pressed. Stop and
     say so. (A re-run after a mid-press failure is fine: continue from the
     step that failed instead of starting over.)

2. **Build, dry.** `./weekly.sh --dry-run` (auto-numbers the issue; ~10
   minutes, all free APIs, cached on disk). This builds and validates
   `issues/issue-NNN.json` with template prose, picks a track for every
   artist-level lead and fills the Spotify URIs (`resolve`), resolves art,
   writes the palette, and renders placeholder covers. Nothing is published.
   - The `availability` stage drops album-of-the-week candidates Spotify
     does not carry, before the writer commits to one. If it reports that
     nothing in the top candidates resolved, the issue still builds but the
     playlist will have no album in it: stop and report rather than press
     that.
   - The `resolve` stage prints anything it could not match. A stray
     unresolved single is survivable, it just sits out of the playlist.

3. **Editorial pass.** Read `issues/issue-NNN.json`, `out/selection-proposal.json`,
   and `out/ledger.json` (if present).
   - **Alias check.** Verification catches never-played artists by string;
     it cannot catch a played artist under another name (Ye is Kanye West,
     Yasiin Bey is Mos Def, Triple Six Mafia is Three 6 Mafia). Check every
     pick for famous aliases.
     An alias is a **flag, not a stop**. A name you have not met before is
     itself worth knowing, so the pick can stand, but the copy has to say so
     rather than sell the act as a stranger. Issue 004 kept Triple Six Mafia
     on exactly that basis: "This is Three 6 Mafia before they settled on the
     spelling, which is worth knowing about a group you have only met in
     passing." Name the other name in the prose, in the reader's own terms,
     and note it in the press report.
     Two cases still stop the press. A pick whose *only* interest was that
     the artist seemed new, where naming the alias leaves nothing to say.
     And an alias inside the album of the week, which carries the issue and
     cannot be a footnote. Both mean choose a different pick.
     No alias table exists and none should be built casually: "triple six
     mafia" is not a near-miss of "three 6 mafia" by any string measure, so
     catching these needs a curated list or a model pass, not a matcher
     tweak. Until one exists this rule is yours to apply by reading.
   - **The final gate is `engine.editorial.final_check`.** `weekly.sh` runs
     it after `resolve`, and you run it again after every copy pass or
     correction (`python3 -m engine.editorial.final_check --n NNN`). It
     checks the document that will actually ship: every rack card has a
     track, no artist twice, every pick is one the selector chose, every
     never-played claim still holds against the history, nothing served
     before is back. A nonzero exit stops the press; a warning (a track
     with no Spotify id) does not.
   - **Repeats are handled in code now**, by `engine.verify.repeat_guard`:
     an artist played since being served is blocked outright, and an artist
     served but never played sits out a 183-day cooldown. Read the
     "Artist-level repeats" section of `out/verification-report.md` to see
     what it caught. It is a guard, not a substitute for reading the picks.
   - **Write `out/copy-NNN.json`** with a shell heredoc (`cat > ... <<'JSON'`)
     rather than the file-editing tools, so an unattended run never stops on
     a permission prompt; the same goes for corrections. Use the writer's
     copy structure (see
     `out/copy-002.json` for shape: title, dek, modules with why / intro /
     tracks[].why / mixes[].why / albums[].why / releases[].note, NTW notes
     carrying `artist` and, when an artist has several releases, `title`).
     Voice rules: VOICE.md, all of them. The issue name is unique, never a
     numbered series, never the same shape as last week; read every
     previous issue's title and dek first so neither repeats an angle.
   - **Apply:** `python3 -m engine.editorial.recopy --n N --copy out/copy-NNN.json`
     It validates; fix the copy and re-apply until it passes. Picks are
     never edited, only prose.

4. **Re-render the cover** with the real name (the dry-run covers carry the
   template name): `python3 -m engine.cover.render --n N`

5. **Publish**, in this order, stopping at the first failure:
   - `python3 -m engine.deliver.publish_playlist --n N`
   - `python3 -m engine.art --n N` (again, so the playlist's own art resolves)
   - `python3 -m engine.cover.upload --n N` (a 401/403 means the Spotify
     token needs a re-auth scope; report it, not fatal to the issue)
   - `python3 -m engine.serve_ledger --n N` (only after the playlist is live)
   - `python3 -m engine.site_index`
   - `python3 -m engine.releases` (refreshes the release calendar; not fatal)

6. **Verify and report.** The issue passes
   `python3 -m engine.editorial.validate issues/issue-NNN.json`; the
   playlist URL answers; `site/public/issues/cover-NNN.jpg` and
   `cover-NNN-plain.jpg` exist. Then tell the owner in one line: issue number
   and name, album of the week, playlist live or not, cover set or not.

## Notes

- Schedule it wherever your agent runs scheduled tasks (Saturdays, early),
  or run it by hand: the procedure is the same.
- `weekly.sh --dry-run` is always safe to run by hand; so is re-running any
  single stage. The served ledger is the only file that must not be
  appended twice for one issue.
