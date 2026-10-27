# Meeting Minutes frontend

Next.js App Router frontend for the Meeting Minutes Assistant MVP.

## Run locally

From the repository root, install dependencies with `pnpm install`, copy `.env.example` to `.env`, then run:

```sh
pnpm --filter @meeting-minutes/web dev
```

Open `http://localhost:3000` for the workspace. The demo auth pages are at `/sign-in` and `/sign-up`.

## Current frontend behavior

- The workspace accepts an existing MP3, M4A, WAV, or WebM file up to 100 MiB and shows sample minutes from local fixture data. It does not upload or transcribe the file.
- Sign-in and sign-up forms validate entries in the browser. They do not create an account, establish a session, or store credentials.
- The theme follows the system setting until changed, then saves the selected theme in browser storage.
- Document download controls are visible placeholders.

## Checks

```sh
pnpm --filter @meeting-minutes/web test
pnpm --filter @meeting-minutes/web typecheck
pnpm --filter @meeting-minutes/web lint
pnpm --filter @meeting-minutes/web build
```
