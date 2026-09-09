# The dev-mode Spotify app (delivery rail)

Why: the companion playlist has to be written from **exact track URIs**,
deterministically and unattended, so a remix or a remaster can never stand
in for the record the issue names. A registered app is how a script does that.

## What "a Spotify app" actually is

Not something you publish or that anyone installs. It's a **credential pair**
(Client ID + Client Secret) registered at developer.spotify.com, which lets
your own code call the Spotify Web API as you. Free, and the account you
already have is the only one involved.

Every new app lives permanently in **Development Mode**:

| | Development Mode | Extended Quota |
|---|---|---|
| Users | up to 5, listed by hand | unlimited |
| Requires | a Premium developer account (since Feb 2026) | registered business, 250k+ MAU, launched product |
| Fit here | exactly right — you are the only user | unreachable and unnecessary |

Dev mode is not a trial that expires. For a personal tool it is the permanent,
intended home.

## What it gets us

- `POST /me/playlists` — create the weekly issue playlist
- `POST /playlists/{id}/tracks` — add **exact URIs**, so a remix or a
  "Remastered 2025" edition can never silently resolve to the wrong version
  (the failure mode a playlist built from search would invite)
- `PUT /playlists/{id}` + `/tracks` — update an existing issue playlist in
  place instead of spawning duplicates
- Runs from a Saturday cron with no chat session in the loop

Scopes needed: `playlist-modify-private` (add `playlist-modify-public` only if
issues should be public).

## Verification status (checked against primary sources 2026-07-28)

**Confirmed — the endpoints exist and work in Development Mode.** Spotify's own
[February 2026 migration guide](https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide)
answers "does this work in Development Mode" with yes, and names
`POST /me/playlists` for creation and `POST /playlists/{id}/items` for adding
tracks. The
[create-playlist reference](https://developer.spotify.com/documentation/web-api/reference/create-playlist)
carries no deprecation banner and lists the scopes below.

**What the February 2026 purge actually did to playlists** — renamed, not
removed:

| Before | After |
|---|---|
| `POST /users/{user_id}/playlists` | **removed** → use `POST /me/playlists` |
| `POST /playlists/{id}/tracks` | **renamed** → `POST /playlists/{id}/items` |
| `DELETE|PUT|GET .../tracks` | **renamed** → `.../items` |
| response `tracks` field | renamed → `items` |

**NOT confirmed — whether new app registration is open right now.** Spotify
froze it in late Dec 2025 ("New integrations are currently on hold while we
make updates to improve reliability and performance"); the
[Feb 6 blog](https://developer.spotify.com/blog/2026-02-06-update-on-developer-access-and-platform-security)
implies it reopened 11 Feb under the new rules, but no source confirms the
state as of July 2026, and the community forum blocks automated fetches.
**Step 0 below settles it in 30 seconds — do that before anything else.**

Also note: `concepts/apps` still claims "25 apps per developer" and an
extension-request link. That page is **stale** — the Feb 2026 rules cap
Development Mode at 1 Client ID per developer, and extended quota now requires
a registered business with 250k+ MAU. Don't plan around that page.

## Setup (~15 minutes, one time)

0. **Check registration is open.** Log in at
   https://developer.spotify.com/dashboard and look at the *Create an App*
   button. If it is greyed out with an "integrations on hold" notice, stop —
   nothing else here is worth doing until it clears. If you already have a
   Client ID from an earlier project, reuse it: the one-per-developer cap
   applies to creating new ones.
1. **Register** at https://developer.spotify.com/dashboard → *Create app*.
   - App name / description: anything ("discovery-dashboard", personal use").
   - **Redirect URI: `http://127.0.0.1:8888/callback`** — must match the
     engine's value exactly, character for character.
   - Check "Web API".
2. **Copy credentials** from the app's Settings into `.env`:
   ```
   SPOTIFY_CLIENT_ID=<paste>
   SPOTIFY_CLIENT_SECRET=<paste>
   ```
   Same hygiene as the other keys — never into chat or a shell command. The
   Client Secret is the sensitive one; it can be rotated from the dashboard at
   any time if it ever leaks.
3. **Authorize once**: `python3 -m engine.deliver.spotify_auth`. It opens a
   browser, you click *Agree*, it captures the callback and stores a
   **refresh token** in a gitignored local file. `--check` verifies it later.
4. From then on the engine mints its own short-lived access tokens from that
   refresh token. No further logins unless you revoke access.

## Failure modes worth knowing

- *INVALID_CLIENT: Invalid redirect URI* — the dashboard value and the engine
  value differ (trailing slash, `localhost` vs `127.0.0.1`). Spotify now
  requires an explicit loopback IP rather than `localhost`.
- *403 on playlist write* — missing scope; re-run the authorize step.
- *Premium requirement* — the developer account itself must be Premium.
- Refresh tokens are long-lived but revocable at
  spotify.com/account/apps; revoking there means re-running step 3.
