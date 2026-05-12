"""Financial statements API — balance sheet, income, cashflow, indicators, forecast."""

import numpy as np
from fastapi import APIRouter, Query, HTTPException
from app.core.database import db
from app.core.config import settings

router = APIRouter()

FINANCE_DIR = settings.project_root / "finances"

BS_FILE = str(FINANCE_DIR / "balancesheet.parquet").replace("\\", "/")
IS_FILE = str(FINANCE_DIR / "income.parquet").replace("\\", "/")
CF_FILE = str(FINANCE_DIR / "cashflow.parquet").replace("\\", "/")
FI_FILE = str(FINANCE_DIR / "fina_indicator.parquet").replace("\\", "/")
FC_FILE = str(FINANCE_DIR / "forecast.parquet").replace("\\", "/")

# ── Column definitions for each statement ──

BS_COLUMNS = [
    # Assets — current
    "money_cap", "trad_asset", "notes_receiv", "accounts_receiv",
    "prepayment", "inventories", "total_cur_assets",
    # Assets — non-current
    "fix_assets", "cip", "intan_assets", "goodwill",
    "defer_tax_assets", "total_nca",
    # Total assets
    "total_assets",
    # Liabilities — current
    "st_borr", "notes_payable", "acct_payable", "adv_receipts",
    "payroll_payable", "taxes_payable", "total_cur_liab",
    # Liabilities — non-current
    "lt_borr", "bond_payable", "total_ncl",
    # Total liabilities
    "total_liab",
    # Equity
    "total_share", "cap_rese", "surplus_rese", "undistr_porfit",
    "total_hldr_eqy_exc_min_int", "minority_int", "total_liab_hldr_eqy",
]

BS_GROUPS = [
    # (label, start_col, is_total)
    ("流动资产", "money_cap", False),
    (" 货币资金", "money_cap", False),
    (" 交易性金融资产", "trad_asset", False),
    (" 应收票据", "notes_receiv", False),
    (" 应收账款", "accounts_receiv", False),
    (" 预付款项", "prepayment", False),
    (" 存货", "inventories", False),
    ("流动资产合计", "total_cur_assets", True),
    ("", None, None),  # spacer
    ("非流动资产", "fix_assets", False),
    (" 固定资产", "fix_assets", False),
    (" 在建工程", "cip", False),
    (" 无形资产", "intan_assets", False),
    (" 商誉", "goodwill", False),
    (" 递延所得税资产", "defer_tax_assets", False),
    ("非流动资产合计", "total_nca", True),
    ("", None, None),
    ("资产总计", "total_assets", True),
    ("", None, None),
    ("流动负债", "st_borr", False),
    (" 短期借款", "st_borr", False),
    (" 应付票据", "notes_payable", False),
    (" 应付账款", "acct_payable", False),
    (" 预收款项", "adv_receipts", False),
    (" 应付职工薪酬", "payroll_payable", False),
    (" 应交税费", "taxes_payable", False),
    ("流动负债合计", "total_cur_liab", True),
    ("", None, None),
    ("非流动负债", "lt_borr", False),
    (" 长期借款", "lt_borr", False),
    (" 应付债券", "bond_payable", False),
    ("非流动负债合计", "total_ncl", True),
    ("", None, None),
    ("负债合计", "total_liab", True),
    ("", None, None),
    ("股东权益", "total_share", False),
    (" 股本", "total_share", False),
    (" 资本公积", "cap_rese", False),
    (" 盈余公积", "surplus_rese", False),
    (" 未分配利润", "undistr_porfit", False),
    ("归属母公司股东权益合计", "total_hldr_eqy_exc_min_int", True),
    (" 少数股东权益", "minority_int", False),
    ("负债和股东权益总计", "total_liab_hldr_eqy", True),
]

IS_COLUMNS = [
    "total_revenue", "revenue", "total_cogs", "oper_cost",
    "biz_tax_surchg", "sell_exp", "admin_exp", "rd_exp",
    "fin_exp", "operate_profit", "total_profit", "income_tax",
    "n_income", "n_income_attr_p", "basic_eps",
]

IS_GROUPS = [
    ("营业总收入", "total_revenue", False),
    (" 营业收入", "revenue", False),
    ("营业总成本", "total_cogs", False),
    (" 营业成本", "oper_cost", False),
    (" 营业税金及附加", "biz_tax_surchg", False),
    (" 销售费用", "sell_exp", False),
    (" 管理费用", "admin_exp", False),
    (" 研发费用", "rd_exp", False),
    (" 财务费用", "fin_exp", False),
    ("", None, None),
    ("营业利润", "operate_profit", True),
    ("利润总额", "total_profit", True),
    (" 所得税费用", "income_tax", False),
    ("净利润", "n_income", True),
    ("归属母公司净利润", "n_income_attr_p", True),
    ("", None, None),
    ("基本每股收益", "basic_eps", False),
]

CF_COLUMNS = [
    "c_inf_fr_operate_a", "st_cash_out_act", "n_cashflow_act",
    "stot_inflows_inv_act", "stot_out_inv_act", "n_cashflow_inv_act",
    "stot_cash_in_fnc_act", "stot_cashout_fnc_act", "n_cash_flows_fnc_act",
    "n_incr_cash_cash_equ", "c_cash_equ_beg_period", "c_cash_equ_end_period",
    "free_cashflow",
]

CF_GROUPS = [
    ("经营活动", "c_inf_fr_operate_a", False),
    (" 经营活动现金流入", "c_inf_fr_operate_a", False),
    (" 经营活动现金流出", "st_cash_out_act", False),
    ("经营活动现金流量净额", "n_cashflow_act", True),
    ("", None, None),
    ("投资活动", "stot_inflows_inv_act", False),
    (" 投资活动现金流入", "stot_inflows_inv_act", False),
    (" 投资活动现金流出", "stot_out_inv_act", False),
    ("投资活动现金流量净额", "n_cashflow_inv_act", True),
    ("", None, None),
    ("筹资活动", "stot_cash_in_fnc_act", False),
    (" 筹资活动现金流入", "stot_cash_in_fnc_act", False),
    (" 筹资活动现金流出", "stot_cashout_fnc_act", False),
    ("筹资活动现金流量净额", "n_cash_flows_fnc_act", True),
    ("", None, None),
    ("现金及等价物净增加额", "n_incr_cash_cash_equ", True),
    (" 期初现金及等价物余额", "c_cash_equ_beg_period", False),
    (" 期末现金及等价物余额", "c_cash_equ_end_period", False),
    ("", None, None),
    ("自由现金流", "free_cashflow", False),
]

FI_COLUMNS = [
    "roe", "roe_yearly", "roa", "roa_yearly",
    "netprofit_margin", "profit_to_gr", "op_of_gr",
    "ocf_to_or", "debt_to_assets", "current_ratio",
    "quick_ratio", "eps", "bps",
    "turn_days", "invturn_days",
    "ebit", "ebitda", "npta",
]

FI_GROUPS = [
    ("盈利能力", "roe", False),
    (" 净资产收益率 ROE (%)", "roe", False),
    (" 年化净资产收益率 ROE (%)", "roe_yearly", False),
    (" 总资产收益率 ROA (%)", "roa", False),
    (" 年化总资产收益率 ROA (%)", "roa_yearly", False),
    (" 净利率 (%)", "netprofit_margin", False),
    (" 毛利率 (%)", "profit_to_gr", False),
    (" 营业利润率 (%)", "op_of_gr", False),
    ("", None, None),
    ("现金流", "ocf_to_or", False),
    (" 经营现金流/营业收入", "ocf_to_or", False),
    ("", None, None),
    ("偿债能力", "debt_to_assets", False),
    (" 资产负债率 (%)", "debt_to_assets", False),
    (" 流动比率", "current_ratio", False),
    (" 速动比率", "quick_ratio", False),
    ("", None, None),
    ("每股指标", "eps", False),
    (" 每股收益 EPS", "eps", False),
    (" 每股净资产 BPS", "bps", False),
    ("", None, None),
    ("营运能力", "turn_days", False),
    (" 总资产周转天数", "turn_days", False),
    (" 存货周转天数", "invturn_days", False),
    ("", None, None),
    ("利润质量", "ebit", False),
    (" EBIT", "ebit", False),
    (" EBITDA", "ebitda", False),
    (" 扣非净利润", "npta", False),
]


COMP_TYPE_LABELS = {"1": "合并报表", "2": "母公司", "4": "合并调整", "3": "分部", "7": "未披露"}


def _col_list(columns: list[str]) -> str:
    return ", ".join(columns)


def _groups_json(groups: list) -> list[dict]:
    return [
        {"label": g[0], "col": g[1], "is_total": g[2] if len(g) > 2 else False}
        for g in groups
    ]


def _clean_value(val):
    if val is None:
        return None
    if isinstance(val, float):
        if np.isnan(val) or np.isinf(val):
            return None
    if hasattr(val, "dtype"):
        # numpy scalar — unwrap via .item() then recurse
        return _clean_value(val.item())
    return val


def _build_response(code: str, df, groups: list, comp_type: str = "") -> dict:
    df["end_date"] = df["end_date"].astype(str).str[:10]
    records = df.drop(columns=["end_date"]).to_dict(orient="records")
    cleaned = [{k: _clean_value(v) for k, v in row.items()} for row in records]
    resp = {
        "code": code,
        "dates": df["end_date"].tolist(),
        "data": cleaned,
        "groups": _groups_json(groups),
    }
    if comp_type:
        resp["comp_type"] = comp_type
        resp["comp_type_label"] = COMP_TYPE_LABELS.get(comp_type, comp_type)
    return resp


def _fetch_statement(file_path: str, code: str, columns: str, periods: int, comp_type: str) -> tuple:
    """Query a statement file. Falls back from comp_type=1 to whatever is available."""
    comp_prefs = ["1", "2", "4", "3", "7"]

    # Build the comp_types to try: user preference first, then fallbacks
    candidates = [comp_type] + [c for c in comp_prefs if c != comp_type]

    for ct in candidates:
        query = f"""
        SELECT end_date, {columns}
        FROM read_parquet('{file_path}')
        WHERE ts_code = '{code}'
          AND comp_type = '{ct}'
        ORDER BY end_date DESC
        LIMIT {periods}
        """
        try:
            df = db.conn.execute(query).fetchdf()
        except Exception:
            continue
        if not df.empty:
            return df, ct

    return None, comp_type


@router.get("/statements/balance")
async def balance_sheet(
    code: str = Query(..., description="Stock code"),
    periods: int = Query(8, ge=1, le=20, description="Number of quarters"),
    comp_type: str = Query("1", description="1=合并 2=母公司"),
):
    if not FINANCE_DIR.exists():
        raise HTTPException(status_code=404, detail="Finance data directory not found")

    df, actual_ct = _fetch_statement(BS_FILE, code, _col_list(BS_COLUMNS), periods, comp_type)
    if df is None:
        raise HTTPException(status_code=404, detail=f"No balance sheet data for {code}")

    return _build_response(code, df, BS_GROUPS, actual_ct)


@router.get("/statements/income")
async def income_statement(
    code: str = Query(..., description="Stock code"),
    periods: int = Query(8, ge=1, le=20, description="Number of quarters"),
    comp_type: str = Query("1", description="1=合并 2=母公司"),
):
    if not FINANCE_DIR.exists():
        raise HTTPException(status_code=404, detail="Finance data directory not found")

    df, actual_ct = _fetch_statement(IS_FILE, code, _col_list(IS_COLUMNS), periods, comp_type)
    if df is None:
        raise HTTPException(status_code=404, detail=f"No income statement data for {code}")

    return _build_response(code, df, IS_GROUPS, actual_ct)


@router.get("/statements/cashflow")
async def cash_flow(
    code: str = Query(..., description="Stock code"),
    periods: int = Query(8, ge=1, le=20, description="Number of quarters"),
    comp_type: str = Query("1", description="1=合并 2=母公司"),
):
    if not FINANCE_DIR.exists():
        raise HTTPException(status_code=404, detail="Finance data directory not found")

    df, actual_ct = _fetch_statement(CF_FILE, code, _col_list(CF_COLUMNS), periods, comp_type)
    if df is None:
        raise HTTPException(status_code=404, detail=f"No cashflow data for {code}")

    return _build_response(code, df, CF_GROUPS, actual_ct)


@router.get("/indicators/{code}")
async def financial_indicators(
    code: str,
    periods: int = Query(8, ge=1, le=20),
):
    if not FINANCE_DIR.exists():
        raise HTTPException(status_code=404, detail="Finance data directory not found")

    cols = _col_list(FI_COLUMNS)
    query = f"""
    SELECT end_date, {cols}
    FROM read_parquet('{FI_FILE}')
    WHERE ts_code = '{code}'
    ORDER BY end_date DESC
    LIMIT {periods}
    """
    try:
        df = db.conn.execute(query).fetchdf()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if df.empty:
        raise HTTPException(status_code=404, detail=f"No indicator data for {code}")

    return _build_response(code, df, FI_GROUPS)


@router.get("/forecast/{code}")
async def earnings_forecast(code: str):
    if not FINANCE_DIR.exists():
        raise HTTPException(status_code=404, detail="Finance data directory not found")

    query = f"""
    SELECT ann_date, end_date, type, p_change_min, p_change_max,
           net_profit_min, net_profit_max, summary, change_reason
    FROM read_parquet('{FC_FILE}')
    WHERE ts_code = '{code}'
    ORDER BY end_date DESC
    LIMIT 20
    """
    try:
        df = db.conn.execute(query).fetchdf()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if df.empty:
        raise HTTPException(status_code=404, detail=f"No forecast data for {code}")

    for col in df.columns:
        if df[col].dtype.name.startswith("date"):
            df[col] = df[col].astype(str).str[:10]

    df = df.replace([np.inf, -np.inf], np.nan).where(df.notna(), None)
    return {"code": code, "forecasts": df.to_dict(orient="records")}
