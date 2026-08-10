# Migration notes

Original server-only files intentionally removed from the deployable site:

- `app.py`
- `Procfile`
- `requirements.txt`
- `utils*.py`
- `utilsteam*.py`
- Jinja templates and old template copies
- preprocessing CSV/XLSX files under `data/csv/`
- unused legacy background-video variants (`bg.mp4`, `bg1080.mp4`, `bg480.mp4`, `bg720.mp4`); the currently referenced `bg1080_remix.mp4` is retained

Those Python utilities were not imported by `app.py`; they are offline data-preparation scripts rather than runtime website dependencies. The deployed website uses the generated JSON files in `data/` directly.

The source archive did not contain `data/match/s2.json` through `s7.json`, and `s13.json` uses a legacy schema. The static page includes a browser-side compatibility adapter for S13, and shows a friendly “暂无可用数据” message when a season JSON is missing instead of throwing a JavaScript error.
