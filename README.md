# iiengineer.com

Static website for Integrity Inspecting Engineers — dilapidation reports across the Illawarra,
Shoalhaven and Sydney.

- `content/` — page content (edit these)
- `partials/` — quote form, call-to-action band, hero drawing
- `static/` — CSS, icons, share image (copied as-is)
- `site.json` — business details (phone, email, credentials, ABN line)
- `build.py` — builds everything into `site/` (no dependencies)
- `tools/check.py` — SEO and broken-link check
- `WEEKLY.md` — instructions and backlog for the weekly Claude update

```
python3 build.py && python3 tools/check.py
```

Netlify publishes `site/` (see `netlify.toml`). The quote form uses Netlify Forms.
