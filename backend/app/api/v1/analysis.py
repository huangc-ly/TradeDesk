from fastapi import APIRouter, Query, HTTPException
from app.core.database import db
from app.core.config import settings
import statsmodels.api as sm
import numpy as np
from scipy import stats as sp_stats
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


def _get_daily_returns(stock: str, start_date: str, end_date: str) -> "pd.DataFrame":
    """Extract daily returns for a single stock.
    Returns DataFrame with columns: trade_date, daily_return.
    Used by: drawdown, sharpe, returns-distribution.
    NOT used by: correlation (which needs benchmark alignment).
    """
    import pandas as pd

    _validate_params(stock, start_date, end_date)

    query = f"""
    SELECT trade_date,
           (close - LAG(close) OVER (ORDER BY trade_date))
           / NULLIF(LAG(close) OVER (ORDER BY trade_date), 0) AS daily_return
    FROM read_parquet('{STOCK_DAILY}')
    WHERE ts_code = '{stock}'
      AND trade_date BETWEEN '{start_date}' AND '{end_date}'
    ORDER BY trade_date
    """
    df = db.conn.execute(query).fetchdf()
    df = df[df['daily_return'].notna()].reset_index(drop=True)
    return df


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


# ---------------------------------------------------------------------------
# Drawdown endpoint
# ---------------------------------------------------------------------------


def _find_drawdown_events(
    nav: np.ndarray, dd: np.ndarray
) -> list[dict]:
    """Find all local drawdown troughs with peak/recovery info."""
    n = len(dd)
    candidates = []

    for i in range(n):
        # Check if i is a local trough in dd (strictly negative, deeper than neighbors)
        if i == 0:
            is_trough = dd[i] < 0 and (n == 1 or dd[i] <= dd[i + 1])
        elif i == n - 1:
            is_trough = dd[i] < 0 and dd[i] < dd[i - 1]
        else:
            is_trough = dd[i] < 0 and dd[i] < dd[i - 1] and dd[i] <= dd[i + 1]

        if not is_trough:
            continue

        peak_idx = int(np.argmax(nav[: i + 1]))
        depth = float(dd[i])

        # Recovery: first index >= i where nav >= nav[peak_idx]
        recovery_mask = nav[i:] >= nav[peak_idx]
        if recovery_mask.any():
            recovery_idx = int(i + np.argmax(recovery_mask))
        else:
            recovery_idx = None

        candidates.append({
            "peak_idx": peak_idx,
            "trough_idx": i,
            "recovery_idx": recovery_idx,
            "depth": depth,
        })

    return candidates


def _intervals_overlap(
    a_start: int, a_end: int | None, b_start: int, b_end: int | None, n: int
) -> bool:
    """Check whether two drawdown intervals overlap. None end means series end (n-1)."""
    a_e = a_end if a_end is not None else n - 1
    b_e = b_end if b_end is not None else n - 1
    return not (a_e < b_start or b_e < a_start)


@router.get("/drawdown")
async def drawdown_analysis(
    stock: str = Query(..., description="Stock code, e.g. 000001.SZ"),
    start_date: str = Query("2024-01-01"),
    end_date: str = Query("2025-12-31"),
    top_n: int = Query(5, ge=1, le=10, description="Number of top drawdowns to return"),
):
    if not settings.stock_daily.exists():
        raise HTTPException(status_code=404, detail="Stock data file not found")

    df = _get_daily_returns(stock, start_date, end_date)
    if df.empty:
        raise HTTPException(status_code=404, detail="No trading data found for the given period")

    returns = df["daily_return"].values
    dates = df["trade_date"].astype(str).tolist()
    n = len(returns)

    nav = np.cumprod(1 + returns)
    peak = np.maximum.accumulate(nav)
    dd = nav / peak - 1

    # --- Single max drawdown (global trough) ---
    trough_idx = int(np.argmin(dd))
    peak_idx = int(np.argmax(nav[: trough_idx + 1]))

    recovery_mask = nav[trough_idx:] >= nav[peak_idx]
    if recovery_mask.any():
        recovery_idx = int(trough_idx + np.argmax(recovery_mask))
        recovery_date = dates[recovery_idx] if recovery_idx != trough_idx else dates[trough_idx]
        recovery_days = recovery_idx - trough_idx
    else:
        recovery_idx = None
        recovery_date = None
        recovery_days = None

    max_dd = float(dd[trough_idx])

    # --- Top-N non-overlapping drawdowns ---
    candidates = _find_drawdown_events(nav, dd)
    candidates.sort(key=lambda x: x["depth"])  # most negative first

    recovered_candidates = [c for c in candidates if c["recovery_idx"] is not None]
    unrecovered_candidates = [c for c in candidates if c["recovery_idx"] is None]

    selected = []
    for c in recovered_candidates:
        if any(
            _intervals_overlap(c["peak_idx"], c["recovery_idx"], s["peak_idx"], s["recovery_idx"], n)
            for s in selected
        ):
            continue
        selected.append(c)
        if len(selected) == top_n:
            break

    # Unrecovered: at most 1, the latest (most recent trough), placed last
    if len(selected) < top_n and unrecovered_candidates:
        latest_urec = max(unrecovered_candidates, key=lambda x: x["trough_idx"])
        if not any(
            _intervals_overlap(
                latest_urec["peak_idx"], latest_urec["recovery_idx"],
                s["peak_idx"], s["recovery_idx"], n,
            )
            for s in selected
        ):
            selected.append(latest_urec)

    top_drawdowns = []
    for rank, c in enumerate(selected, 1):
        dur = (c["recovery_idx"] if c["recovery_idx"] is not None else n - 1) - c["peak_idx"]
        rec_days = c["recovery_idx"] - c["trough_idx"] if c["recovery_idx"] is not None else None
        rec_date = dates[c["recovery_idx"]] if c["recovery_idx"] is not None else None
        top_drawdowns.append({
            "rank": rank,
            "drawdown": round(c["depth"], 4),
            "peak_date": dates[c["peak_idx"]],
            "trough_date": dates[c["trough_idx"]],
            "recovery_date": rec_date,
            "duration_days": dur,
            "recovery_days": rec_days,
        })

    # --- Equity curve ---
    equity_curve = [
        {
            "trade_date": dates[i],
            "nav": round(float(nav[i]), 4),
            "drawdown": round(float(dd[i]), 4),
        }
        for i in range(n)
    ]

    return {
        "stock": stock,
        "data_points": n,
        "start_date": start_date,
        "end_date": end_date,
        "summary": {
            "max_drawdown": round(max_dd, 4),
            "peak_date": dates[peak_idx],
            "trough_date": dates[trough_idx],
            "recovery_date": recovery_date,
            "recovery_days": recovery_days,
            "current_drawdown": round(float(dd[-1]), 4),
        },
        "top_drawdowns": top_drawdowns,
        "equity_curve": equity_curve,
    }


# ---------------------------------------------------------------------------
# Sharpe ratio endpoint
# ---------------------------------------------------------------------------


@router.get("/sharpe")
async def sharpe_analysis(
    stock: str = Query(..., description="Stock code, e.g. 000001.SZ"),
    start_date: str = Query("2024-01-01"),
    end_date: str = Query("2025-12-31"),
    window: int = Query(252, ge=21, description="Rolling window in trading days"),
    rf: float = Query(0, description="Annualized risk-free rate"),
):
    if not settings.stock_daily.exists():
        raise HTTPException(status_code=404, detail="Stock data file not found")

    df = _get_daily_returns(stock, start_date, end_date)
    if df.empty:
        raise HTTPException(status_code=404, detail="No trading data found for the given period")

    returns = df["daily_return"].values
    dates = df["trade_date"].astype(str).tolist()
    n = len(returns)

    # --- Full-period stats ---
    ann_ret_arith = float(returns.mean() * 252)
    ann_vol = float(returns.std(ddof=1) * np.sqrt(252))

    total_ret = float(np.prod(1 + returns) - 1)
    years = n / 252
    cagr = float((1 + total_ret) ** (1 / years) - 1) if years > 0 else 0

    sharpe = float((ann_ret_arith - rf) / ann_vol) if ann_vol > 0 else 0

    # Sortino
    daily_rf = rf / 252
    downside_sq = np.minimum(returns - daily_rf, 0) ** 2
    dd_dev = float(np.sqrt(downside_sq.mean()) * np.sqrt(252)) if n > 0 else 0
    sortino = float((ann_ret_arith - rf) / dd_dev) if dd_dev > 0 else 0

    # Calmar
    nav = np.cumprod(1 + returns)
    peak = np.maximum.accumulate(nav)
    dd_series = nav / peak - 1
    max_dd = float(np.min(dd_series))
    calmar = float(cagr / abs(max_dd)) if max_dd < 0 else 0

    # --- Rolling window ---
    effective_window = min(window, n)
    rolling_sharpe = []
    if effective_window >= 21:
        for i in range(n - effective_window + 1):
            rw = returns[i : i + effective_window]
            vol = float(rw.std(ddof=1) * np.sqrt(252))
            arith = float(rw.mean() * 252)
            total_rw = float(np.prod(1 + rw) - 1)
            yrs = effective_window / 252
            cagr_rw = float((1 + total_rw) ** (1 / yrs) - 1) if yrs > 0 else 0
            sh = float((arith - rf) / vol) if vol > 0 else 0
            rolling_sharpe.append({
                "trade_date": dates[i + effective_window - 1],
                "sharpe": round(sh, 4),
                "cagr": round(cagr_rw, 4),
                "ann_vol": round(vol, 4),
            })

    return {
        "stock": stock,
        "data_points": n,
        "window": effective_window,
        "summary": {
            "cagr": round(cagr, 4),
            "ann_return_arithmetic": round(ann_ret_arith, 4),
            "ann_volatility": round(ann_vol, 4),
            "sharpe_ratio": round(sharpe, 4),
            "sortino_ratio": round(sortino, 4),
            "calmar_ratio": round(calmar, 4),
            "max_drawdown": round(max_dd, 4),
        },
        "rolling_sharpe": rolling_sharpe,
    }


# ---------------------------------------------------------------------------
# Returns distribution endpoint
# ---------------------------------------------------------------------------


@router.get("/returns-distribution")
async def returns_distribution(
    stock: str = Query(..., description="Stock code, e.g. 000001.SZ"),
    start_date: str = Query("2024-01-01"),
    end_date: str = Query("2025-12-31"),
    bins: int = Query(50, ge=1, le=200, description="Histogram bin count"),
):
    if not settings.stock_daily.exists():
        raise HTTPException(status_code=404, detail="Stock data file not found")

    df = _get_daily_returns(stock, start_date, end_date)
    if df.empty:
        raise HTTPException(status_code=404, detail="No trading data found for the given period")

    returns = df["daily_return"].values
    n = len(returns)

    # --- Summary stats ---
    mean_ret = float(returns.mean())
    median_ret = float(np.median(returns))
    std_ret = float(returns.std(ddof=1))

    skew = float(sp_stats.skew(returns, bias=False))
    kurt = float(sp_stats.kurtosis(returns, bias=False))  # excess kurtosis
    jb_stat = float(sp_stats.jarque_bera(returns).statistic)
    jb_p = float(sp_stats.jarque_bera(returns).pvalue)
    is_normal = jb_p >= 0.05

    up = returns[returns > 0]
    down = returns[returns < 0]
    up_ratio = float(len(up) / n) if n > 0 else 0
    avg_gain = float(up.mean()) if len(up) > 0 else 0
    avg_loss = float(down.mean()) if len(down) > 0 else 0
    gain_loss_ratio = float(abs(avg_gain / avg_loss)) if avg_loss != 0 else 0

    # --- Histogram ---
    counts, bin_edges = np.histogram(returns, bins=bins)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
    histogram = [
        {"bin_center": round(float(c), 6), "count": int(cnt)}
        for c, cnt in zip(bin_centers, counts)
    ]

    # --- QQ Plot ---
    n_quantiles = min(n, 100)
    quantiles = np.linspace(
        1 / (n_quantiles + 1), n_quantiles / (n_quantiles + 1), n_quantiles
    )
    theoretical = sp_stats.norm.ppf(quantiles)
    sample = np.quantile(returns, quantiles)
    qq_plot = [
        {"theoretical": round(float(t), 6), "sample": round(float(s), 6)}
        for t, s in zip(theoretical, sample)
    ]

    # --- Normal fit line ---
    mu = float(returns.mean())
    sigma = float(returns.std(ddof=1))
    x_fit = np.linspace(bin_edges[0], bin_edges[-1], 200)
    density = sp_stats.norm.pdf(x_fit, mu, sigma)
    bin_width = bin_edges[1] - bin_edges[0]
    scale = n * bin_width
    normal_fit = [
        {"x": round(float(x), 6), "density": round(float(d * scale), 4)}
        for x, d in zip(x_fit, density)
    ]

    return {
        "stock": stock,
        "data_points": n,
        "summary": {
            "mean_daily_return": round(mean_ret, 6),
            "median_daily_return": round(median_ret, 6),
            "std_daily_return": round(std_ret, 6),
            "skewness": round(skew, 4),
            "kurtosis": round(kurt, 4),
            "jarque_bera_stat": round(jb_stat, 4),
            "jarque_bera_pvalue": jb_p,
            "is_normal": is_normal,
            "up_days_ratio": round(up_ratio, 4),
            "avg_gain": round(avg_gain, 6),
            "avg_loss": round(avg_loss, 6),
            "gain_loss_ratio": round(gain_loss_ratio, 4),
        },
        "histogram": histogram,
        "qq_plot": qq_plot,
        "normal_fit": normal_fit,
    }
