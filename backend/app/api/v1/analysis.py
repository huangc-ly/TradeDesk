from fastapi import APIRouter, Query, HTTPException
from app.core.database import db
from app.core.config import settings
import statsmodels.api as sm
import re
import math

router = APIRouter()

STOCK_DAILY = str(settings.stock_daily).replace("\\", "/")
INDEXES_DIR = settings.indexes_dir

# Whitelist: only A-share codes and known index code patterns
_CODE_RE = re.compile(r"^\d{6}\.(SZ|SH|SI|CI)$")


def _validate_params(stock: str, start_date: str, end_date: str) -> None:
    """Reject malformed params before any DuckDB call."""
    if not _CODE_RE.match(stock):
        raise HTTPException(status_code=422, detail=f"Invalid stock code: {stock}")
    if start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must be <= end_date")


def _validate_benchmark(code: str) -> None:
    if not _CODE_RE.match(code):
        raise HTTPException(status_code=422, detail=f"Invalid benchmark code: {code}")


def _check_degenerate(series: "pd.Series", label: str) -> None:
    """Reject series with near-zero variance before OLS produces NaN."""
    if len(series) < 3:
        raise HTTPException(
            status_code=422,
            detail=f"Insufficient data: {label} has only {len(series)} observations (need >= 3)",
        )
    if series.std(ddof=1) < 1e-12:
        raise HTTPException(
            status_code=422,
            detail=f"Degenerate sample: {label} has zero variance (all returns identical)",
        )


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
    Uses statsmodels OLS for regression — provides p-values, confidence
    intervals, and standard errors in addition to point estimates.
    """
    if not settings.stock_daily.exists():
        raise HTTPException(status_code=404, detail="Stock data file not found")

    _validate_params(stock, start_date, end_date)
    _validate_benchmark(benchmark)

    bench_file = _find_benchmark_file(benchmark)
    if not bench_file:
        raise HTTPException(status_code=404, detail=f"Benchmark {benchmark} not found")

    bench_where = ""
    if bench_file.endswith("_daily.parquet"):
        bench_where = f"ts_code = '{benchmark}' AND"

    # stock / benchmark / dates have passed _validate_params — safe to interpolate
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
    )
    SELECT trade_date, stock_return, benchmark_return
    FROM joined
    ORDER BY trade_date
    """

    try:
        df = db.conn.execute(query).fetchdf()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if df.empty:
        raise HTTPException(status_code=404, detail="No overlapping trading days found")

    # Guard against degenerate samples before OLS (prevents NaN → 500)
    _check_degenerate(df["stock_return"], "stock returns")
    _check_degenerate(df["benchmark_return"], "benchmark returns")

    X = sm.add_constant(df["benchmark_return"])
    y = df["stock_return"]
    model = sm.OLS(y, X).fit()

    correlation = float(df["stock_return"].corr(df["benchmark_return"]))

    ci = model.conf_int(alpha=0.05)
    beta_ci = ci.loc["benchmark_return"]
    alpha_ci = ci.loc["const"]

    # Raw t-values from statsmodels (before rounding, consistent with p/CI)
    beta_tvalue_raw = float(model.tvalues["benchmark_return"])
    alpha_tvalue_raw = float(model.tvalues["const"])

    # Replace NaN with None so FastAPI serializes as null (valid JSON)
    def _nan_to_none(v: float) -> float | None:
        return None if math.isnan(v) else v

    returns = [
        {
            "trade_date": str(row["trade_date"]),
            "stock_return": float(row["stock_return"]),
            "benchmark_return": float(row["benchmark_return"]),
        }
        for _, row in df.iterrows()
    ]

    return {
        "stock": stock,
        "benchmark": benchmark,
        "start_date": start_date,
        "end_date": end_date,
        "data_points": int(model.nobs),
        # Point estimates
        "beta": round(float(model.params["benchmark_return"]), 4),
        "alpha": round(float(model.params["const"]), 6),
        "correlation": round(correlation, 4),
        "r_squared": round(float(model.rsquared), 4),
        "adj_r_squared": round(float(model.rsquared_adj), 4),
        # Statistical inference
        "beta_std_err": round(float(model.bse["benchmark_return"]), 6),
        "alpha_std_err": round(float(model.bse["const"]), 6),
        "beta_tvalue": round(beta_tvalue_raw, 4),
        "alpha_tvalue": round(alpha_tvalue_raw, 4),
        "beta_pvalue": _nan_to_none(float(model.pvalues["benchmark_return"])),
        "alpha_pvalue": _nan_to_none(float(model.pvalues["const"])),
        "beta_ci_lower": _nan_to_none(round(float(beta_ci[0]), 4)),
        "beta_ci_upper": _nan_to_none(round(float(beta_ci[1]), 4)),
        "alpha_ci_lower": _nan_to_none(round(float(alpha_ci[0]), 6)),
        "alpha_ci_upper": _nan_to_none(round(float(alpha_ci[1]), 6)),
        # Residual diagnostics
        "f_statistic": _nan_to_none(round(float(model.fvalue), 2)),
        "f_pvalue": _nan_to_none(float(model.f_pvalue)),
        "returns": returns,
    }
