"""Factor library — declarative registry + cross-sectional computation.

Each factor is defined once in FACTOR_REGISTRY.  Adding a factor is a
single metadata entry — no Python code required for simple SQL factors.
"""

from fastapi import APIRouter, Query, HTTPException
from app.core.database import db
from app.core.config import settings
import numpy as np

router = APIRouter()

STOCK_DAILY = str(settings.stock_daily).replace("\\", "/")

# ---------------------------------------------------------------------------
# Factor Registry
# ---------------------------------------------------------------------------
# type "raw"     → direct column read, no lookback required
# type "window"  → uses window functions over a lookback window
# category       → value | size | momentum | volatility | liquidity

FACTOR_REGISTRY: dict[str, dict] = {
    # ── Value ──────────────────────────────────────────────────────────
    "pe_ttm": {
        "name": "市盈率 (TTM)",
        "category": "value",
        "type": "raw",
        "expression": "pe_ttm",
        "lookback_days": 0,
        "description": "滚动市盈率",
    },
    "pb": {
        "name": "市净率",
        "category": "value",
        "type": "raw",
        "expression": "pb",
        "lookback_days": 0,
        "description": "每股股价 / 每股净资产",
    },
    # ── Size ───────────────────────────────────────────────────────────
    "total_mv": {
        "name": "总市值",
        "category": "size",
        "type": "raw",
        "expression": "total_mv",
        "lookback_days": 0,
        "description": "总市值（万元）",
    },
    "circ_mv": {
        "name": "流通市值",
        "category": "size",
        "type": "raw",
        "expression": "circ_mv",
        "lookback_days": 0,
        "description": "流通市值（万元）",
    },
    # ── Liquidity ──────────────────────────────────────────────────────
    "turnover_rate": {
        "name": "换手率",
        "category": "liquidity",
        "type": "raw",
        "expression": "turnover_rate",
        "lookback_days": 0,
        "description": "当日换手率",
    },
    "turnover_rate_5d": {
        "name": "5日平均换手率",
        "category": "liquidity",
        "type": "window",
        "expression": "AVG(turnover_rate) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS 4 PRECEDING)",
        "lookback_days": 15,
        "description": "近5个交易日平均换手率",
    },
    "turnover_rate_20d": {
        "name": "20日平均换手率",
        "category": "liquidity",
        "type": "window",
        "expression": "AVG(turnover_rate) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS 19 PRECEDING)",
        "lookback_days": 40,
        "description": "近20个交易日平均换手率",
    },
    "amount_5d": {
        "name": "5日平均成交额",
        "category": "liquidity",
        "type": "window",
        "expression": "AVG(amount) OVER (PARTITION BY ts_code ORDER BY trade_date ROWS 4 PRECEDING)",
        "lookback_days": 15,
        "description": "近5个交易日平均成交额",
    },
    "volume_ratio": {
        "name": "量比",
        "category": "liquidity",
        "type": "raw",
        "expression": "volume_ratio",
        "lookback_days": 0,
        "description": "当日成交量 / 5日均量",
    },
    # ── Momentum ───────────────────────────────────────────────────────
    "mom_20d": {
        "name": "20日动量",
        "category": "momentum",
        "type": "window",
        "expression": (
            "(close - LAG(close, 20) OVER (PARTITION BY ts_code ORDER BY trade_date))"
            " / NULLIF(LAG(close, 20) OVER (PARTITION BY ts_code ORDER BY trade_date), 0)"
        ),
        "lookback_days": 40,
        "description": "过去20个交易日累计收益率",
    },
    "mom_60d": {
        "name": "60日动量",
        "category": "momentum",
        "type": "window",
        "expression": (
            "(close - LAG(close, 60) OVER (PARTITION BY ts_code ORDER BY trade_date))"
            " / NULLIF(LAG(close, 60) OVER (PARTITION BY ts_code ORDER BY trade_date), 0)"
        ),
        "lookback_days": 100,
        "description": "过去60个交易日累计收益率",
    },
    # ── Volatility ─────────────────────────────────────────────────────
    "vol_20d": {
        "name": "20日波动率",
        "category": "volatility",
        "type": "window",
        "needs_daily_return": True,
        "expression": (
            "STDDEV_SAMP(daily_return) OVER ("
            "PARTITION BY ts_code ORDER BY trade_date ROWS 19 PRECEDING"
            ")"
        ),
        "lookback_days": 40,
        "description": "近20个交易日日收益率标准差",
    },
    "vol_60d": {
        "name": "60日波动率",
        "category": "volatility",
        "type": "window",
        "needs_daily_return": True,
        "expression": (
            "STDDEV_SAMP(daily_return) OVER ("
            "PARTITION BY ts_code ORDER BY trade_date ROWS 59 PRECEDING"
            ")"
        ),
        "lookback_days": 100,
        "description": "近60个交易日日收益率标准差",
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _latest_trading_date() -> str | None:
    q = (
        f"SELECT MAX(trade_date) FROM read_parquet('{STOCK_DAILY}')"
    )
    row = db.conn.execute(q).fetchone()
    return str(row[0])[:10] if row and row[0] else None


def _build_raw_query(factor_def: dict, date_: str) -> str:
    return (
        f"SELECT ts_code, {factor_def['expression']} AS value "
        f"FROM read_parquet('{STOCK_DAILY}') "
        f"WHERE trade_date = '{date_}' "
        f"AND {factor_def['expression']} IS NOT NULL "
        f"ORDER BY ts_code"
    )


def _build_window_query(factor_def: dict, date_: str) -> str:
    lookback = factor_def.get("lookback_days", 60)
    needs_dr = factor_def.get("needs_daily_return", False)

    daily_return_col = (
        "(close - LAG(close) OVER (PARTITION BY ts_code ORDER BY trade_date))"
        " / NULLIF(LAG(close) OVER (PARTITION BY ts_code ORDER BY trade_date), 0)"
        " AS daily_return,"
        if needs_dr
        else ""
    )

    return f"""
    WITH src AS (
        SELECT ts_code, trade_date, close, turnover_rate, amount,
               {daily_return_col}
               NULL AS _placeholder
        FROM read_parquet('{STOCK_DAILY}')
        WHERE trade_date BETWEEN '{date_}'::DATE - {lookback} AND '{date_}'
    )
    SELECT ts_code, value
    FROM (
        SELECT ts_code, trade_date,
               {factor_def['expression']} AS value
        FROM src
    ) sub
    WHERE trade_date = '{date_}'
      AND value IS NOT NULL
    ORDER BY ts_code
    """


def _compute_stats(values: np.ndarray) -> dict:
    """Descriptive stats on the factor cross-section."""
    valid = values[~np.isnan(values) & ~np.isinf(values)]
    n = len(valid)
    if n == 0:
        return {"count_valid": 0, "count_null": len(values)}

    return {
        "count_valid": n,
        "count_null": int(np.isnan(values).sum()),
        "mean": round(float(valid.mean()), 6),
        "std": round(float(valid.std(ddof=1)), 6),
        "min": round(float(valid.min()), 6),
        "max": round(float(valid.max()), 6),
        "q25": round(float(np.percentile(valid, 25)), 6),
        "median": round(float(np.percentile(valid, 50)), 6),
        "q75": round(float(np.percentile(valid, 75)), 6),
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/factors")
async def list_factors(category: str | None = Query(None, description="Filter by category")):
    """List all registered factors with metadata."""
    result = []
    for fid, fd in FACTOR_REGISTRY.items():
        if category and fd["category"] != category:
            continue
        result.append({
            "id": fid,
            "name": fd["name"],
            "category": fd["category"],
            "type": fd["type"],
            "description": fd["description"],
            "lookback_days": fd["lookback_days"],
        })
    # Sort: alphabetical by category, then id
    result.sort(key=lambda x: (x["category"], x["id"]))
    return {"factors": result, "count": len(result), "categories": sorted({r["category"] for r in result})}


@router.get("/factors/latest-date")
async def factor_latest_date():
    """Return the most recent trading date with data."""
    d = _latest_trading_date()
    if d is None:
        raise HTTPException(status_code=404, detail="No trading data found")
    return {"latest_date": d}


@router.get("/factors/{factor_id}/values")
async def compute_factor_values(
    factor_id: str,
    date: str | None = Query(None, description="Target date (YYYY-MM-DD). Defaults to latest."),
):
    """Compute a factor's cross-sectional values for all stocks on a given date."""
    fd = FACTOR_REGISTRY.get(factor_id)
    if fd is None:
        raise HTTPException(status_code=404, detail=f"Unknown factor: {factor_id}")

    date_ = date or _latest_trading_date()
    if date_ is None:
        raise HTTPException(status_code=404, detail="No trading data found")

    factor_type = fd["type"]
    try:
        if factor_type == "raw":
            df = db.conn.execute(_build_raw_query(fd, date_)).fetchdf()
        else:
            df = db.conn.execute(_build_window_query(fd, date_)).fetchdf()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")

    if df.empty:
        raise HTTPException(status_code=404, detail=f"No stocks with valid {factor_id} on {date_}")

    values = df["value"].to_numpy(dtype=float)
    stats = _compute_stats(values)

    return {
        "factor_id": factor_id,
        "factor_name": fd["name"],
        "date": date_,
        "category": fd["category"],
        "stats": stats,
        "top_10": df.nlargest(10, "value")[["ts_code", "value"]].to_dict(orient="records"),
        "bottom_10": df.nsmallest(10, "value")[["ts_code", "value"]].to_dict(orient="records"),
        "all_values": [
            {"ts_code": row["ts_code"], "value": round(float(row["value"]), 6)}
            for _, row in df.iterrows()
        ],
    }
