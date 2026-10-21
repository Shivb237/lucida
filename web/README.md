# lucida-web

The Lucida site: React 19, Vite 8 and TypeScript. One page frame, hash routes, no router library.

## Two builds

| Build | Command | What it does |
|---|---|---|
| Lab (default) | `npm run build` | Looks for a server at the same address (`/api/health`, `/api/ready`). If one answers, visitors can choose **Try it live** and search their own words. |
| Viewer | `VITE_VIEWER=1 npm run build` | Never calls a server of its own. It replays the recorded runs in `src/recorded/runs.json` and shows the logged evidence. This is the GitHub Pages build. |

`?mode=viewer` on any build behaves like the Viewer build for that visit.

## Run it

```sh
npm ci
npm run dev        # http://localhost:5173, proxies /api to the server on :7860 (set GENKART_API to override)
npm run lint       # oxlint
npm run build      # type check, then the production build in dist/
npm run preview    # serve dist/ locally
```

The server is the Python app in `../src/genkart` (see the repository README). Start it with `bash ../space/start.sh` (port 7860) or directly: `.venv/bin/uvicorn genkart.server:app --app-dir src --port 7860`.

## Environment variables

| Variable | Used for |
|---|---|
| `VITE_VIEWER=1` | The Viewer build (above). |
| `VITE_BASE` | The path the site is served under, for example `/lucida/` on GitHub Pages. Default `/`. |
| `VITE_PHOTO_BASE` | Address of the hosted Lab. The Viewer loads product photos from it and wakes it from `#/wake`. It is also added to the page's Content-Security-Policy. Empty: no photos, labelled frames instead. |
| `VITE_CSP_META` | Set by `.env.production` and `.env.development`; do not set it yourself. It switches the CSP meta tag on in production only. |
| `EVIDENCE_STRICT=1` | Fail the build when a logged run file cannot be read (CI). |

## Routes

`#/` Search · `#/evidence` and `#/evidence/<claim-id>` · `#/docs` and `#/docs/<section>` (How it works) · `#/system` · `#/words` (Glossary) · `#/wake` (wakes the hosted Lab) · `#/study`.

Links can also start a run: `?run=<recorded-run-id>` (Viewer), `?q=<request>` (Lab; the text is sent in a POST body), `?demo=1`.

## Rules the code keeps

- Numbers come only from logged runs (`runs/*.summary.json` through `virtual:evidence`, and `runs.json`). Nothing is typed by hand.
- A visitor's API key lives in React memory only. It is sent in POST bodies, never in an address, storage, a log or an error message.
- The design system is in `DESIGN.md` (the Light Table): greys plus one magenta for pressable or picked things, square corners, text at least 12px, targets at least 44px.
