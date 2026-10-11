# python

## GOTCHA

- App code is `config/` and `web/` at the repo root, not inside `python/`. Docker must set `PYTHONPATH=/app` and put the venv on `PATH` (`/app/python/.venv/bin`).

## TASTE

- `pyproject.toml` and `uv.lock` live in `python/`. `requires-python = ">=3.12"`, `[tool.uv] package = false`.
- Change deps with `cd python && uv add …` / `uv lock`; commit both toml and lock.
