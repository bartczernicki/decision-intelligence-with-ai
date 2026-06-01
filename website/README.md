# Decision Intelligence Static Website

This folder contains the source automation and generated output for the static website built from notebooks selected in `src/build_website_config.json`.

## Folder Layout

- `src/` contains the build and deploy scripts.
- `src/build_website_config.json` controls the book version and which notebooks are included.
- `dist/` contains the generated static website.

## Build

From the repository root:

```bash
python3 website/src/build_website.py
```

The build converts notebooks to HTML, wraps them in the static book shell, generates the Pagefind index, and validates local links.

To include or exclude notebooks, edit `src/build_website_config.json` and change `include_in_build`.

## Test Locally

```bash
python3 -m http.server 8765 --directory website/dist
```

Open `http://127.0.0.1:8765/`. Pagefind search is intended to run from a static server, not directly from `file://`.

To stop the local server, press `Ctrl+C` in the terminal where it is running.

If that terminal is no longer available, stop the process listening on port `8765`:

```bash
lsof -ti tcp:8765 | xargs kill
```

## Deploy To Azure Blob Static Website

Enable static website hosting on the storage account with `index.html` as the index document. Then deploy the contents of `website/dist/` to `$web`:

```bash
website/src/deploy_website.sh "<storage-account-name>" [resource-group]
```

The contents of `website/dist/` should land at the root of `$web`, so `$web/index.html`, `$web/assets/`, `$web/chapters/`, and `$web/pagefind/` are siblings.

## Cache Guidance

During active editing, keep `index.html` and chapter HTML on a short cache. Pagefind and asset files can use longer cache headers after content stabilizes, but regenerate Pagefind whenever notebook content changes.
