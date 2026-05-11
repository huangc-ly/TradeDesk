from fastapi import APIRouter, Query, HTTPException
from pathlib import Path
from app.core.database import db
from app.core.config import settings

router = APIRouter()

STOCK_DAILY = str(settings.stock_daily).replace("\\", "/")
INDEXES_DIR = settings.indexes_dir


def _find_benchmark_file(code: str) -> str:
    """Find the parquet file containing an index/benchmark."""
    file_path = INDEXES_DIR / f"{code}.parquet"
    if file_path.exists():
        return str(file_path).replace("\\", "/")

    for fname in ["ci_l1_daily.parquet", "ci_l2_daily.parquet", "sw_l1_daily.parquet"]:
        fp = INDEXES_DIR / fname
        if fp.exists():
            fp_str = str(fp).replace("\\", "/")
            try:
                cnt = db.conn.execute(
                    f"SELECT COUNT(*) FROM read_parquet('{fp_str}') WHERE ts_code = '{code}'"
                ).fetchone()[0]
                if cnt > 0:
                    return fp_str
            except Exception:
                pass
    return ""


@router.get("/correlation")
async def correlation_analysis(
    stock: str = Query(..., description="Stock code, e.g. 000001.SZ"),
    benchmark: str = Query("000001.SH", description="Benchmark index code"),
    start_date: str = Query("2024-01-01", description="Start date (YYYY-MM-DD)"),
    end_date: str = Query("2025-12-31", description="End date (YYYY-MM-DD)"),
):
    """
    Calculate return correlation between a stock and a benchmark.
    Returns beta, alpha, correlation coefficient, R-squared, and the return series.
    """
    if not settings.stock_daily.exists():
        raise HTTPException(status_code=404, detail="Stock data file not found")

    # Find benchmark file
    bench_file = _find_benchmark_file(benchmark)
    if not bench_file:
        raise HTTPException(status_code=404, detail=f"Benchmark {benchmark} not found")

    # Build date filter; if benchmark is a consolidated file, add ts_code filter
    bench_where = ""
    if bench_file.endswith("_daily.parquet"):
        bench_where = f"ts_code = '{benchmark}' AND"

    query = f"""
    WITH stock_ret AS (
        SELECT trade_date,
               (close - LAG(close) OVER w) / NULLIF(LAG(close) OVER w, 0) AS ret
        FROM read_parquet('{STOCK_DAILY}')
        WHERE ts_code = '{stock}'
          AND trade_date BETWEEN '{start_date}' AND '{end_date}'
        WINDOW w AS (ORDER BY trade_date)
    ),
    bench_ret AS (
        SELECT trade_date,
               (close - LAG(close) OVER w) / NULLIF(LAG(close) OVER w, 0) AS ret
        FROM read_parquet('{bench_file}')
        WHERE {bench_where} trade_date BETWEEN '{start_date}' AND '{end_date}'
        WINDOW w AS (ORDER BY trade_date)
    ),
    joined AS (
        SELECT s.trade_date, s.ret AS stock_return, b.ret AS benchmark_return
        FROM stock_ret s
        JOIN bench_ret b ON s.trade_date = b.trade_date
        WHERE s.ret IS NOT NULL AND b.ret IS NOT NULL
    ),
    metrics AS (
        SELECT
            regr_slope(stock_return, benchmark_return) AS beta,
            regr_intercept(stock_return, benchmark_return) AS alpha,
            corr(stock_return, benchmark_return) AS correlation,
            regr_r2(stock_return, benchmark_return) AS r_squared,
            COUNT(*) AS data_points
        FROM joined
    )
    SELECT
        m.beta, m.alpha, m.correlation, m.r_squared, m.data_points,
        LIST({{trade_date: j.trade_date, stock_return: j.stock_return, benchmark_return: j.benchmark_return}}) AS returns
    FROM metrics m, joined j
    GROUP BY m.beta, m.alpha, m.correlation, m.r_squared, m.data_points
    """

    try:
        row = db.conn.execute(query).fetchone()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if row is None or row[4] == 0:
        raise HTTPException(status_code=404, detail="No overlapping trading days found")

    return {
        "stock": stock,
        "benchmark": benchmark,
        "start_date": start_date,
        "end_date": end_date,
        "beta": round(row[0], 4) if row[0] is not None else None,
        "alpha": round(row[1], 6) if row[1] is not None else None,
        "correlation": round(row[2], 4) if row[2] is not None else None,
        "r_squared": round(row[3], 4) if row[3] is not None else None,
        "data_points": row[4],
        "returns": [
            {
                "trade_date": str(r["trade_date"]),
                "stock_return": r["stock_return"],
                "benchmark_return": r["benchmark_return"],
            }
            for r in (row[5] or [])
        ],
    }
