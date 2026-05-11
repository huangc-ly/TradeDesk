# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Reasoning Effort: Absolute maximum with no shortcuts permitted. You MUST be very thorough in your thinking and comprehensively decompose the problem to resolve the root cause, rigorously stress-testing your logic against all potential paths, edge cases, and adversarial scenarios. Explicitly write out your entire deliberation process, documenting every intermediate step, considered alternative, and rejected hypothesis to ensure absolutely no assumption is left unchecked.

## Quick Reference

```bash
# Backend
cd backend && uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm run dev

# Install deps
cd backend && pip install -r requirements.txt
cd frontend && npm install
```

## Architecture

Monorepo with two independent services. The frontend Vite dev server proxies `/api/*` to the backend at `localhost:8000`.

**Backend**: FastAPI application factory pattern. The `lifespan` context manager in `main.py` manages DuckDB connection lifecycle — connect on startup, close on shutdown. Routes are versioned under `/api/v1/`.

**Data layer**: No traditional database. DuckDB queries parquet files directly via `read_parquet()`. The `Database` class (`backend/app/core/database.py`) is a singleton holding a single DuckDB connection. All endpoints use `db.conn.execute(...).fetchdf()` to get pandas DataFrames, then convert with `.to_dict(orient="records")`.

## Data Files

| File | Size | Contents |
|------|------|----------|
| `stocks/stock_daily.parquet` | 1.2GB | All stocks daily OHLCV, keyed by `ts_code` + `trade_date`. 33 columns including indicators |
| `stocks/stock_basic_data.parquet` | 443KB | Stock metadata: `ts_code`, `name`, `industry`, `area`, `market`, `list_status`, `list_date`. Use for stock lists — never scan the daily file for codes |
| `indexes/ci_l1_daily.parquet` | 23MB | 申万一级行业指数日线, keyed by `ts_code` |
| `indexes/ci_l2_daily.parquet` | 32MB | 申万二级行业指数日线 |
| `indexes/sw_l1_daily.parquet` | 20MB | Alternative industry index source |
| `indexes/000001.SH.parquet` etc. | ~5MB | Per-index files for market indices (上证指数 etc.) |

## Key Conventions

- **Config**: `Settings` in `backend/app/core/config.py` uses `pydantic-settings`. Env vars prefixed with `TD_`. Parquet file paths are resolved from `project_root` (auto-detected relative to `config.py`).
- **API pattern**: Each domain module in `api/v1/` has its own `APIRouter`. The main router in `api/router.py` aggregates them under `/v1/{market,strategy,portfolio}`. New domain modules should follow the same pattern.
- **Frontend route pages use lazy loading** via `() => import(...)` in the router.
- **Element Plus configured with Chinese locale** (`zhCn`) in `main.ts`.
- **Path aliases**: Frontend uses `@/` mapped to `src/`.

## Performance Notes

The `stock_daily.parquet` at 1.2GB is the critical path. Always filter by `ts_code` before other predicates. The `stock_basic_data.parquet` file (443KB) should be used for any stock-list or metadata queries — it's 3000x smaller and returns in ~20ms vs 2000ms for scanning the daily file.

The indexes list endpoint (`/api/v1/market/indexes`) currently scans three consolidated files with DISTINCT queries — this is the next optimization target if index listing feels slow.
