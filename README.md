# ALJS / Juicypedia — GitHub Pages edition

This branch/folder is a fully static migration of the original Flask site.

## What changed

- Flask/Jinja rendering was removed.
- `/api/match/<season>` was replaced by browser-side `fetch()` of `data/match/sN.json`.
- Events, players and records are rendered from JSON in the browser.
- Match URLs remain directory-style (`match/s15/`) so GitHub Pages can serve them naturally.
- All asset URLs are repository-relative, so the site works at `https://<user>.github.io/ALJS/` rather than assuming domain root `/`.
- A GitHub Actions Pages workflow is included.

## Deploy

1. Replace the contents of the repository with this static version and push to `main`.
2. In GitHub: **Settings → Pages → Build and deployment → Source → GitHub Actions**.
3. Push to `main` (or run the workflow manually). The included workflow deploys the site.

## Local preview

Do not double-click the HTML files because browsers block JSON `fetch()` from `file://` URLs. Start any static web server instead, e.g.:

```bash
python -m http.server 8000
```

Then open `http://localhost:8000/`.

## Runtime dependencies

There is no Python/Flask backend. Bootstrap is loaded from jsDelivr; all ALJS data and media are local static files.
