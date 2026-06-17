# Actors Overlap

A starter web app on the way to a "Degrees of Kevin Bacon" explorer. Enter two
movies or TV shows and see the list of cast members that appear in both. Data
comes from IMDB via the open-source [`cinemagoer`](https://github.com/cinemagoer/cinemagoer)
library (formerly IMDbPY).

## Stack

- **Backend**: Python 3.11+, FastAPI, Uvicorn, `cinemagoer`
- **Frontend**: Vite + Vue 3 (`<script setup>` SFCs) + TypeScript
- **Dev**: backend on `:8000`, frontend dev server on `:5173` (proxies `/api/*` to the backend)

## Prerequisites

- Python 3.11 or newer
- Node.js 20+ and npm

## Backend

### One-time setup

```bash
cd backend
python -m venv .venv

# Activate the venv:
#   cmd.exe / PowerShell:  .venv\Scripts\activate
#   Git Bash / MSYS:       source .venv/Scripts/activate
#   macOS / Linux:         source .venv/bin/activate

python -m pip install --upgrade pip
pip install -e .
```

### Run the backend

After setup, every-day startup is one command. None of these require the venv
to be activated — they all call the venv's Python directly:

```bash
# Git Bash / macOS / Linux:
./run.sh

# cmd.exe / PowerShell:
run.bat

# Or if you do have the venv activated:
python main.py
```

The API will be available at <http://localhost:8000>, with interactive docs at
<http://localhost:8000/docs>. Auto-reload is on by default; pass `--no-reload`
or `--port 9000` to override:

```bash
./run.sh --port 9000 --no-reload
```

## Run the frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. The dev server proxies `/api/*` to the backend, so
both must be running.

## API surface

| Method | Path                       | Description                                                    |
| ------ | -------------------------- | -------------------------------------------------------------- |
| GET    | `/api/health`              | Liveness probe.                                                |
| GET    | `/api/search?q=&limit=`    | Search IMDB titles by name. Returns up to `limit` (max 20).    |
| GET    | `/api/title/{imdb_id}`     | Full title detail including cast.                              |
| GET    | `/api/overlap?id1=&id2=`   | Cast members that appear in both titles.                       |

IMDB ids are passed as bare digits (no `tt` prefix). The id is the value from
`/api/search` results.

## How it works

`backend/app/imdb_service.py` wraps `cinemagoer`:

- `search_titles(query, limit)` -> `[TitleHit]` via `Cinemagoer().search_movie(...)`.
- `get_title_with_cast(imdb_id)` -> `TitleDetail` via `get_movie(...)`, with cast
  projected into a small DTO. Process-lifetime in-memory cache keyed by id.
- `overlap(id1, id2)` -> intersects cast on person IMDB id and surfaces each
  actor's role in both titles.

The cinemagoer calls are blocking, so FastAPI handlers dispatch them with
`asyncio.to_thread(...)` to keep the event loop responsive.

## Caveats / next steps

- **IMDB Terms of Service.** Cinemagoer scrapes IMDB's public pages. Be a good
  citizen: low request rates, no redistribution. For a production deployment,
  consider an official source (TMDB, OMDb) instead.
- **First lookups are slow.** Fetching a movie's full cast can take 10–30s,
  especially for large TV shows. The in-memory cache makes subsequent overlap
  comparisons against the same title near-instant for the life of the process.
- **No persistent cache yet.** Restarting the backend re-fetches everything. A
  SQLite cache is an easy next iteration.
- **Not the Kevin Bacon feature yet.** This is v0: a one-hop intersection.
  Multi-hop shortest-path search across actors and titles is the next step.

## Project layout

```
actors/
  README.md
  backend/
    pyproject.toml
    main.py              # dev entrypoint: `python main.py`
    run.sh / run.bat     # one-command launcher (no venv activation needed)
    app/
      __init__.py
      main.py            # FastAPI app, routes, CORS
      imdb_service.py    # cinemagoer wrapper + in-memory cache
      models.py          # pydantic response models
  frontend/
    package.json
    vite.config.ts       # dev proxy /api -> :8000
    tsconfig*.json
    index.html
    src/
      main.ts
      App.vue
      api.ts
      types.ts
      styles.css
      env.d.ts
      components/
        TitleSearch.vue
        OverlapResults.vue
```
