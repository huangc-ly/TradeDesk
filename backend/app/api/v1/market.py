from fastapi import APIRouter, Query, HTTPException
from app.core.database import db
from app.core.config import settings

router = APIRouter()

STOCK_DAILY_FILE = str(settings.stock_daily).replace("\\", "/")
STOCK_BASIC_FILE = str(settings.stock_basic).replace("\\", "/")


@router.get("/stocks")
async def list_stocks():
    """List all stocks with basic info (from stock_basic_data.parquet)."""
    if not settings.stock_basic.exists():
        return {"stocks": [], "count": 0}

    result = db.conn.execute(
        f"SELECT ts_code, symbol, name, area, industry, market, exchange, "
        f"list_status, list_date, is_hs "
        f"FROM read_parquet('{STOCK_BASIC_FILE}') "
        f"ORDER BY ts_code"
    ).fetchdf()

    return {"stocks": result.to_dict(orient="records"), "count": len(result)}


@router.get("/stock/{code}")
async def get_stock_daily(
    code: str,
    start_date: str | None = Query(None, description="Start date (YYYYMMDD)"),
    end_date: str | None = Query(None, description="End date (YYYYMMDD)"),
    limit: int = Query(100, ge=1, le=10000, description="Max rows to return"),
):
    """Get daily OHLCV data for a single stock."""
    if not settings.stock_daily.exists():
        raise HTTPException(status_code=404, detail="Stock data file not found")

    where_clause = f"ts_code = '{code}'"
    if start_date:
        where_clause += f" AND trade_date >= '{start_date}'"
    if end_date:
        where_clause += f" AND trade_date <= '{end_date}'"

    query = (
        f"SELECT open, high, low, close, vol, amount, trade_date "
        f"FROM read_parquet('{STOCK_DAILY_FILE}') "
        f"WHERE {where_clause} "
        f"ORDER BY trade_date DESC "
        f"LIMIT {limit}"
    )

    try:
        result = db.conn.execute(query).fetchdf()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if result.empty:
        raise HTTPException(status_code=404, detail=f"No data for stock {code}")

    # Convert trade_date to string for JSON serialization
    result["trade_date"] = result["trade_date"].astype(str)
    return result.to_dict(orient="records")


@router.get("/stock/{code}/latest")
async def get_stock_latest(code: str):
    """Get the most recent daily bar for a stock."""
    if not settings.stock_daily.exists():
        raise HTTPException(status_code=404, detail="Stock data file not found")

    query = (
        f"SELECT * FROM read_parquet('{STOCK_DAILY_FILE}') "
        f"WHERE ts_code = '{code}' "
        f"ORDER BY trade_date DESC LIMIT 1"
    )

    try:
        result = db.conn.execute(query).fetchdf()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if result.empty:
        raise HTTPException(status_code=404, detail=f"No data for stock {code}")

    # Convert all non-serializable columns
    for col in result.columns:
        if result[col].dtype.name.startswith("date"):
            result[col] = result[col].astype(str)

    return result.to_dict(orient="records")[0]


@router.get("/indexes")
async def list_indexes():
    """List all available indexes (consolidated + per-file)."""
    indexes_dir = settings.indexes_dir
    if not indexes_dir.exists():
        return {"indexes": [], "count": 0}

    # Collect codes from both consolidated files and per-file indexes
    codes = set()
    consolidated_files = ["ci_l1_daily.parquet", "ci_l2_daily.parquet", "sw_l1_daily.parquet"]

    for fname in consolidated_files:
        fp = indexes_dir / fname
        if fp.exists():
            try:
                fp_str = str(fp).replace("\\", "/")
                result = db.conn.execute(
                    f"SELECT DISTINCT ts_code FROM read_parquet('{fp_str}')"
                ).fetchdf()
                codes.update(result["ts_code"].tolist())
            except Exception:
                pass

    # Add per-file indexes (*.SH.parquet)
    for fp in indexes_dir.glob("*.SH.parquet"):
        codes.add(fp.stem)

    sorted_codes = sorted(codes)
    return {"indexes": sorted_codes, "count": len(sorted_codes)}


@router.get("/index/{code}")
async def get_index_daily(
    code: str,
    limit: int = Query(100, ge=1, le=10000),
):
    """Get daily data for a single index."""
    indexes_dir = settings.indexes_dir
    file_path = indexes_dir / f"{code}.parquet"

    # Try per-file first, then search consolidated files
    if file_path.exists():
        fp_str = str(file_path).replace("\\", "/")
    else:
        # Search in consolidated files for this ts_code
        found = None
        for fname in ["ci_l1_daily.parquet", "ci_l2_daily.parquet", "sw_l1_daily.parquet"]:
            fp = indexes_dir / fname
            if fp.exists():
                fp_str = str(fp).replace("\\", "/")
                try:
                    check = db.conn.execute(
                        f"SELECT COUNT(*) as cnt FROM read_parquet('{fp_str}') WHERE ts_code = '{code}'"
                    ).fetchone()
                    if check[0] > 0:
                        found = fp_str
                        break
                except Exception:
                    pass
        if found is None:
            raise HTTPException(status_code=404, detail=f"Index {code} not found")
        fp_str = found

    query = (
        f"SELECT * FROM read_parquet('{fp_str}') "
        f"WHERE ts_code = '{code}' "
        f"ORDER BY trade_date DESC LIMIT {limit}"
    )

    try:
        result = db.conn.execute(query).fetchdf()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if result.empty:
        raise HTTPException(status_code=404, detail=f"No data for index {code}")

    for col in result.columns:
        if result[col].dtype.name.startswith("date"):
            result[col] = result[col].astype(str)

    return result.to_dict(orient="records")
