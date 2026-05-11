# 分析模块扩展设计

## 概述

在现有的"相关性分析"基础上，新增三个量化分析指标：最大回撤、夏普比率、收益率分布。四个指标通过 tab 切换展示，**每个 tab 独立请求各自的 endpoint**，各自维护自己的结果和状态。

## 一、架构

### 1.1 数据流

```
DuckDB 提取日收益率
    │
    ├──→ 最大回撤：    nav = cumprod(1+r) → cummax → drawdown curve
    ├──→ 夏普比率：    年化收益 / 年化波动 → ratio + rolling window
    ├──→ 收益率分布：  直方图 → scipy.stats.skew/kurtosis/jarque_bera + QQ plot
    └──→ 相关性分析：  stock↔benchmark JOIN → statsmodels OLS → β/α/p/CI
```

### 1.2 前后端分工

| 层 | 职责 |
|----|------|
| DuckDB | 从 parquet 提取收益率序列（列式扫描，O(n) 窗口函数） |
| scipy / statsmodels | 统计计算（偏度峰度、JB 检验、OLS 回归） |
| numpy | 向量化数值计算（nav、cummax、滚动窗口） |
| FastAPI | 四个独立端点，各自返回结构化 JSON |
| Vue 3 + ECharts | tab 切换 + 图表渲染 + 指标卡片 |

### 1.3 输入校验策略

所有端点共享同一套参数校验规则，在业务逻辑入口处统一拦截：

```python
import re

STOCK_CODE_RE = re.compile(r'^\d{6}\.(SZ|SH|SI|CI)$')

def _validate_params(stock: str, start_date: str, end_date: str) -> None:
    """Raise HTTPException(422) on invalid input before any DuckDB call."""
    if not STOCK_CODE_RE.match(stock):
        raise HTTPException(status_code=422, detail=f"Invalid stock code: {stock}")
    if start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must be <= end_date")
    # DuckDB's BETWEEN is inclusive; date strings are safe after regex+comparison check
```

DuckDB 不支持 `?` 占位符在 `read_parquet()` 的 WHERE 子句中的参数绑定，但经过正则校验后的 `stock`（只含数字和 `.SZ/.SH/.SI/.CI`）和经过日期比较的 `start_date` / `end_date`（`YYYY-MM-DD` 格式）已不包含 SQL 元字符，字符串插值是安全的。若未来扩展参数类型，必须改为 DuckDB 的 `$1` 命名参数。

## 二、依赖

scipy 是此设计的**硬依赖**（偏度、峰度、JB 检验、QQ 分位数均来自 `scipy.stats`），需同时更新 `requirements.txt` 和 `pyproject.toml`：

```
# requirements.txt
scipy>=1.10.0

# pyproject.toml dependencies
"scipy>=1.10.0",
```

## 三、API 设计

### 3.1 收益率提取（内部函数）

三个单股票端点（回撤、夏普、分布）共用。**相关性端点不使用此函数**——它需要股票和基准两个序列按交易日内连接对齐，逻辑更复杂，保持独立的双序列路径。

```python
def _get_daily_returns(stock: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Extract daily returns for a single stock.
    Returns DataFrame with columns: trade_date, daily_return.
    Used by: drawdown, sharpe, returns-distribution.
    NOT used by: correlation (which needs benchmark alignment).
    """
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
```

### 3.2 最大回撤 `GET /analysis/drawdown`

**请求参数**

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|:---:|------|------|
| stock | string | ✅ | — | 股票代码 |
| start_date | string | | 2024-01-01 | |
| end_date | string | | 2025-12-31 | |
| top_n | int | | 5 | 历史最大 N 次回撤，min=1, max=10 |

**返回结构**

```json
{
  "stock": "000001.SZ",
  "data_points": 484,
  "start_date": "2024-01-01",
  "end_date": "2025-12-31",

  "summary": {
    "max_drawdown": -0.1845,
    "peak_date": "2024-09-20",
    "trough_date": "2025-01-10",
    "recovery_date": "2025-04-15",
    "recovery_days": 95,
    "current_drawdown": -0.032
  },

  "top_drawdowns": [
    {
      "rank": 1,
      "drawdown": -0.1845,
      "peak_date": "2024-09-20",
      "trough_date": "2025-01-10",
      "recovery_date": "2025-04-15",
      "duration_days": 207,
      "recovery_days": 95
    }
  ],

  "equity_curve": [
    { "trade_date": "2024-01-02", "nav": 1.0, "drawdown": 0 },
    { "trade_date": "2024-01-03", "nav": 0.9989, "drawdown": -0.0011 }
  ]
}
```

**字段说明**

| 字段 | 类型 | 含义 |
|------|------|------|
| `duration_days` | int | 交易日数：peak_date → recovery_date（若未恢复则到序列末尾） |
| `recovery_days` | int | 交易日数：trough_date → recovery_date（若未恢复则为 null） |
| `recovery_date` | string\|null | null 表示至序列末尾仍未恢复到峰值 |

**单次最大回撤计算**

```python
returns = df['daily_return'].values
nav = np.cumprod(1 + returns)                  # 累积净值
peak = np.maximum.accumulate(nav)              # 动态峰值
dd = nav / peak - 1                            # 回撤序列（≤ 0）

trough_idx = int(np.argmin(dd))                # 最深点
peak_idx = int(np.argmax(nav[:trough_idx + 1])) # 该最深点之前的峰值

recovery_mask = nav[trough_idx:] >= nav[peak_idx]
recovery_idx = int(trough_idx + np.argmax(recovery_mask)) if recovery_mask.any() else None
```

**Top-N 不重叠回撤提取算法**

```
输入: 回撤序列 dd[0..T-1], 净值序列 nav[0..T-1], 目标次数 N
输出: 按回撤幅度降序排列的 N 个不重叠回撤区间

算法:
  candidates = []            # [(depth, peak_idx, trough_idx, recovery_idx, ...)]
  visited = set()            # 已分配区间的索引范围

  # 1. 找出所有局部回撤波谷
  for each local minimum in dd (谷底):
      向前找 peak（nav 在此之前的最大值位置）
      向后找 recovery（nav ≥ nav[peak] 的第一个位置，或 None）

  # 2. 按回撤深度降序
  sort candidates by depth (most negative first)

  # 3. 贪心选取不重叠区间
  result = []
  for each candidate:
      if candidate 区间与任何已选区间无重叠:
          result.append(candidate)
          mark [peak_idx, recovery_idx or T-1] as visited
      if len(result) == N:
          break

"不重叠"定义: 区间 A 的 [peak_A, recovery_A] 与区间 B 的 [peak_B, recovery_B]
             没有交集。若某一区间未恢复（recovery = None），其终点为序列末尾。
             未恢复的区间排在最末（不论深度），且最多保留 1 个（最新的）。
```

### 3.3 夏普比率 `GET /analysis/sharpe`

**请求参数**

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|:---:|------|------|
| stock | string | ✅ | — | |
| start_date | string | | 2024-01-01 | |
| end_date | string | | 2025-12-31 | |
| window | int | | 252 | 滚动窗口长度（交易日），min=21, max=len(returns) |
| rf | float | | 0 | 年化无风险利率 |

**返回结构**

```json
{
  "stock": "000001.SZ",
  "data_points": 484,
  "window": 252,

  "summary": {
    "cagr": 0.0891,
    "ann_return_arithmetic": 0.0935,
    "ann_volatility": 0.2247,
    "sharpe_ratio": 0.397,
    "sortino_ratio": 0.523,
    "calmar_ratio": 0.483,
    "max_drawdown": -0.1845
  },

  "rolling_sharpe": [
    { "trade_date": "2025-01-02", "sharpe": 0.35, "cagr": 0.08, "ann_vol": 0.22 },
    { "trade_date": "2025-01-03", "sharpe": 0.34, "cagr": 0.08, "ann_vol": 0.23 }
  ]
}
```

**计算逻辑**

```python
# ---- 全周期统计 ----

# 算术年化（适用于 Sharpe / Sortino，因为分子分母同口径）
ann_ret_arithmetic = returns.mean() * 252
ann_vol = returns.std(ddof=1) * np.sqrt(252)

# CAGR（几何年化，展示用）
total_ret = np.prod(1 + returns) - 1
years = len(returns) / 252
cagr = (1 + total_ret) ** (1 / years) - 1 if years > 0 else 0

# 夏普比率（分子用 CAGR 或算术年化均可，业界惯例用算术年化；这里明确分开）
sharpe = (ann_ret_arithmetic - rf) / ann_vol if ann_vol > 0 else 0

# 索提诺比率 — downside deviation over FULL sample
# Sortino 定义: (R - MAR) / sqrt(1/T * Σ min(r_i - MAR, 0)^2)
# MAR = minimum acceptable return = rf_daily = rf / 252
daily_rf = rf / 252
downside_sq = np.minimum(returns - daily_rf, 0) ** 2
downside_dev = np.sqrt(downside_sq.mean()) * np.sqrt(252) if len(returns) > 0 else 0
sortino = (ann_ret_arithmetic - rf) / downside_dev if downside_dev > 0 else 0

# 卡玛比率 — CAGR / |max_drawdown|
nav = np.cumprod(1 + returns)
peak = np.maximum.accumulate(nav)
dd = nav / peak - 1
max_dd = float(np.min(dd))
calmar = cagr / abs(max_dd) if max_dd < 0 else 0

# ---- 滚动窗口 ----
# 处理 window > len(returns) 的情况
window = min(window, len(returns))
if window < 21:
    rolling = []
else:
    rolling = []
    for i in range(len(returns) - window + 1):   # +1 确保最后一个合法窗口不被遗漏
        rw = returns[i:i + window]
        vol = rw.std(ddof=1) * np.sqrt(252)
        arith = rw.mean() * 252
        total_rw = np.prod(1 + rw) - 1
        yrs = window / 252
        cagr_rw = (1 + total_rw) ** (1 / yrs) - 1 if yrs > 0 else 0
        sh = (arith - rf) / vol if vol > 0 else 0
        rolling.append({
            "trade_date": str(df['trade_date'].iloc[i + window - 1]),
            "sharpe": round(float(sh), 4),
            "cagr": round(float(cagr_rw), 4),
            "ann_vol": round(float(vol), 4),
        })
```

**关键区别说明**

| 概念 | 公式 | 此处用途 |
|------|------|----------|
| CAGR | `(∏(1+r))^(252/n) - 1` | 展示、Calmar 分子 |
| 算术年化 | `mean(r) × 252` | Sharpe/Sortino 分子（与分母的年化 vol 同口径） |
| Downside deviation | `√(mean(min(r - rf, 0)²)) × √252` | Sortino 分母（全样本，非仅负收益子集） |

### 3.4 收益率分布 `GET /analysis/returns-distribution`

**请求参数**

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|:---:|------|------|
| stock | string | ✅ | — | |
| start_date | string | | 2024-01-01 | |
| end_date | string | | 2025-12-31 | |
| bins | int | | 50 | 直方图分桶数 |

**返回结构**（q_qplot 和 normal_fit 字段已补全）

```json
{
  "stock": "000001.SZ",
  "data_points": 484,

  "summary": {
    "mean_daily_return": 0.00035,
    "median_daily_return": 0.00012,
    "std_daily_return": 0.0142,
    "skewness": 0.312,
    "kurtosis": 1.457,
    "jarque_bera_stat": 54.2,
    "jarque_bera_pvalue": 1.7e-12,
    "is_normal": false,
    "up_days_ratio": 0.52,
    "avg_gain": 0.0102,
    "avg_loss": -0.0098,
    "gain_loss_ratio": 1.04
  },

  "histogram": [
    { "bin_center": -0.06, "count": 3 },
    { "bin_center": -0.05, "count": 5 }
  ],

  "qq_plot": [
    { "theoretical": -2.33, "sample": -0.031 },
    { "theoretical": -2.05, "sample": -0.029 }
  ],

  "normal_fit": [
    { "x": -0.06, "density": 0.5 },
    { "x": -0.058, "density": 0.7 }
  ]
}
```

**计算逻辑**

```python
from scipy import stats
import numpy as np

returns = df['daily_return'].values
n = len(returns)

# 偏度 / 峰度
skew = float(stats.skew(returns, bias=False))
kurt = float(stats.kurtosis(returns, bias=False))  # excess kurtosis
jb_stat, jb_p = stats.jarque_bera(returns)

# 涨跌统计
up = returns[returns > 0]
down = returns[returns < 0]
up_ratio = len(up) / n if n > 0 else 0
avg_gain = float(up.mean()) if len(up) > 0 else 0
avg_loss = float(down.mean()) if len(down) > 0 else 0
gain_loss_ratio = abs(avg_gain / avg_loss) if avg_loss != 0 else 0

# ---- 直方图 ----
counts, bin_edges = np.histogram(returns, bins=bins)
bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
histogram = [{"bin_center": round(float(c), 6), "count": int(cnt)} for c, cnt in zip(bin_centers, counts)]

# ---- QQ Plot ----
# 理论分位数：标准正态分布
n_quantiles = min(n, 100)
quantiles = np.linspace(1 / (n_quantiles + 1), n_quantiles / (n_quantiles + 1), n_quantiles)
theoretical = stats.norm.ppf(quantiles)
sample = np.quantile(returns, quantiles)
qq_plot = [{"theoretical": round(float(t), 6), "sample": round(float(s), 6)} for t, s in zip(theoretical, sample)]

# ---- 正态拟合线 ----
# 基于样本 mean 和 std 的正态 PDF，x 范围覆盖直方图区间
mu, sigma = returns.mean(), returns.std(ddof=1)
x_fit = np.linspace(bin_edges[0], bin_edges[-1], 200)
density = stats.norm.pdf(x_fit, mu, sigma)
# 缩放至与直方图 count 匹配: scale = total_count * bin_width
bin_width = bin_edges[1] - bin_edges[0]
scale = n * bin_width
normal_fit = [{"x": round(float(x), 6), "density": round(float(d * scale), 4)} for x, d in zip(x_fit, density)]
```

### 3.5 相关性分析 `GET /analysis/correlation`（保持独立路径）

此端点**不使用** `_get_daily_returns()`。它需要执行两个收益率序列的 INNER JOIN 来确保交易日对齐，停牌日可能出现在一个序列而不在另一个序列中，JOIN 自动排除这些天。

```python
@router.get("/correlation")
async def correlation_analysis(stock, benchmark, start_date, end_date):
    _validate_params(stock, start_date, end_date)
    # benchmark code 也需要校验（指数代码可能格式不同，放宽检查）
    if not re.match(r'^\d{6}\.(SH|SZ|SI|CI)$', benchmark):
        raise HTTPException(status_code=422, detail=f"Invalid benchmark code: {benchmark}")

    # 保持现有的 _find_benchmark_file + DuckDB JOIN 逻辑
    ...
```

## 四、前端设计

### 4.1 组件树

```
Analysis.vue                           ← shell：tab 管理 + 公共控件
├── ControlsBar (inline)                ← stock + date range（所有 tab 共用）
│   └── benchmark picker                ← 仅 correlation tab 显示
├── el-tabs                             ← 按需懒加载策略
│   └── el-tab-pane × 4
└── <component :is="activeTabComp" />   ← 动态组件，按需挂载
    ├── CorrelationTab.vue
    ├── DrawdownTab.vue
    ├── SharpeTab.vue
    └── DistributionTab.vue
```

### 4.2 Tab 结果缓存策略

**每个 tab 独立管理自己的数据、loading、error 状态**。shell 不持有单一 `result`，而是持有按 tab name 索引的状态映射。

```typescript
// Analysis.vue (shell)
const stock = ref('000001.SZ')
const benchmark = ref('000001.SH')
const dateRange = ref<[string, string]>(['2024-01-01', '2025-12-31'])
const activeTab = ref('correlation')

// Per-tab state — 每个 tab 独立
interface TabState {
  loading: boolean
  error: string
  data: any | null
}

const tabStates = ref<Record<string, TabState>>({
  correlation: { loading: false, error: '', data: null },
  drawdown:    { loading: false, error: '', data: null },
  sharpe:      { loading: false, error: '', data: null },
  distribution:{ loading: false, error: '', data: null },
})

// Tab → Endpoint 映射
const ENDPOINTS: Record<string, Function> = {
  correlation:    () => analysisApi.getCorrelation({ stock: stock.value, benchmark: benchmark.value, ... }),
  drawdown:       () => analysisApi.getDrawdown({ stock: stock.value, ... }),
  sharpe:         () => analysisApi.getSharpe({ stock: stock.value, ... }),
  distribution: () => analysisApi.getDistribution({ stock: stock.value, ... }),
}

async function calculate() {
  const tab = activeTab.value
  const state = tabStates.value[tab]
  state.loading = true
  state.error = ''
  try {
    state.data = await ENDPOINTS[tab]()
  } catch (e: any) {
    state.error = e?.response?.data?.detail ?? e?.message ?? '请求失败'
  } finally {
    state.loading = false
  }
}

// 切换 tab 时不清空数据——已计算过的结果保留
// 用户可以为四个 tab 分别计算，结果各自独立
function onTabChange(name: string) {
  activeTab.value = name
}
```

**每个 tab 组件只接收自己需要的数据和状态，互不交叉：**

```vue
<!-- CorrelationTab 接收 -->
<CorrelationTab
  v-if="tabStates.correlation.data"
  :result="tabStates.correlation.data"
/>

<!-- DrawdownTab 接收 -->
<DrawdownTab
  v-if="tabStates.drawdown.data"
  :result="tabStates.drawdown.data"
/>

<!-- 其他 tab 类似 -->
```

### 4.3 布局规范

每个 tab 内布局统一：**指标卡片行 → 主图行 → 辅助表格/图行**

```
┌──────────────────────────────────────────┐
│  指标卡 1  │  指标卡 2  │  指标卡 3  │ ... │   ← el-row(:gutter=16)
├──────────────────────────────────────────┤
│                                          │
│              主图表区                      │   ← el-card 内 ECharts (height: 420px)
│                                          │
├──────────────────────────────────────────┤
│         辅助图表 / 排名表格                 │   ← 可选
└──────────────────────────────────────────┘
```

### 4.4 各 Tab 详细布局

#### DrawdownTab

```
┌──────────────────────────────────────────────────────────────────┐
│ -18.45%  │ 2024-09-20  │ 2025-01-10  │ 95 天恢复  │ 当前 -3.2% │
│ 最大回撤   │ 峰值日期     │ 谷底日期     │ 恢复天数    │ 当前回撤    │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  累计净值曲线 + 回撤阴影                                           │
│  ┌────────────────────────────────────────────────────────┐     │
│  │   净值曲线（上方线）+ 回撤填充区域（下方阴影）              │     │
│  │   底部叠加单独的 drawdown% 副图                          │     │
│  └────────────────────────────────────────────────────────┘     │
│                                                                  │
├──────────────────────────────────────────────────────────────────┤
│  历史 Top 5 回撤（el-table）                                      │
│  排名 │ 回撤幅度 │ 峰值日期 │ 谷底日期 │ 恢复日期 │ 持续天数 │ 恢复天数│
│  1   │ -18.45% │ 09-20   │ 01-10   │ 04-15   │ 207     │ 95     │
└──────────────────────────────────────────────────────────────────┘
```

#### SharpeTab

```
┌──────────────────────────────────────────────────────────────┐
│ 0.397  │ 0.523  │ 0.483  │ 8.91%  │ 22.47% │ 304 样本       │
│ 夏普    │ 索提诺  │ 卡玛    │ CAGR   │ 年化波动 │ 含 roi window│
├──────────────────────────────────────────────────────────────┤
│  滚动夏普比率（252日窗口）                                      │
│  ┌────────────────────────────────────────────────────┐     │
│  │   夏普曲线 + 均值参考线                                │     │
│  └────────────────────────────────────────────────────┘     │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│  月度收益率热力图（可选，V2）                                    │
└──────────────────────────────────────────────────────────────┘
```

#### DistributionTab

前端直接从 `qq_plot` 和 `normal_fit` 字段取数据渲染，无需本地计算：

```
┌──────────────────────────────────────────────────────────────┐
│ 0.31  │ 1.46  │ 54.2  │ 1.7e-12  │ ✗ 非正态                  │
│ 偏度    │ 峰度   │ JB 统计│ JB p 值   │ 正态性                  │
├──────────────────────────────────────────────────────────────┤
│ 52%   │ +1.02%  │ -0.98%  │ 1.04  │ 0.035%                  │
│ 上涨比  │ 平均涨幅 │ 平均跌幅  │ 盈亏比  │ 日均收益                 │
├──────────────────────────────────────────────────────────────┤
│  收益率分布直方图 + 正态拟合                                     │
│  ┌────────────────────────────────────────────────────┐     │
│  │   bar: histogram (红绿分色)                          │     │
│  │   line: normal_fit (data.x, data.density)           │     │
│  └────────────────────────────────────────────────────┘     │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│  QQ Plot                                                     │
│  ┌────────────────────────────────────────────────────┐     │
│  │   scatter: qq_plot (theoretical vs sample)           │     │
│  │   line: y=x 对角线                                    │     │
│  └────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────┘
```

#### CorrelationTab

```
┌──────────────────────────────────────────────────────────────┐
│  基准: [搜索指数]（仅本 tab 内显示）                            │
├──────────────────────────────────────────────────────────────┤
│  β=0.80 │ r=0.62 │ R²=0.39 │ α=0.001% │ 484 │ F=304        │
├──────────────────────────────────────────────────────────────┤
│  β 显著性  │  α 显著性                                        │
├──────────────────────────────────────────────────────────────┤
│  散点图                      │  累计收益对比                    │
└──────────────────────────────────────────────────────────────┘
```

### 4.5 公共控件

```vue
<el-card class="controls-bar">
  <el-form :inline="true">
    <el-form-item label="股票">
      <el-select v-model="stock" filterable remote />
    </el-form-item>
    <el-form-item label="区间">
      <el-date-picker v-model="dateRange" type="daterange" />
    </el-form-item>
    <!-- 仅 correlation tab 显示基准选择 -->
    <el-form-item v-if="activeTab === 'correlation'" label="基准">
      <el-select v-model="benchmark" filterable remote />
    </el-form-item>
    <el-form-item>
      <el-button @click="calculate" :loading="tabStates[activeTab].loading">计算</el-button>
    </el-form-item>
  </el-form>
</el-card>

<el-tabs v-model="activeTab">
  <el-tab-pane name="correlation" label="相关性" />
  <el-tab-pane name="drawdown" label="回撤" />
  <el-tab-pane name="sharpe" label="夏普" />
  <el-tab-pane name="distribution" label="分布" />
</el-tabs>

<!-- 动态组件，按 tab name 渲染，只传该 tab 自己的状态 -->
<component :is="activeTab + 'Tab'" :result="tabStates[activeTab].data" />
```

## 五、ECharts 图表规范

### 5.1 回撤图

```typescript
// 上轴: 净值曲线 (line) + 峰值线 (dashed)
// 下轴: 回撤% 面积图 (area, 红色渐变填充)
series: [
  { type: 'line', data: equityCurve.map(d => d.nav), name: '净值' },
  {
    type: 'line',
    data: equityCurve.map(d => d.drawdown * 100),
    name: '回撤 %',
    areaStyle: {
      color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: 'rgba(245,108,108,0.4)' },
        { offset: 1, color: 'rgba(245,108,108,0.02)' },
      ]),
    },
    showSymbol: false,
    lineStyle: { width: 0 },
  },
]
```

### 5.2 直方图 + 正态拟合

```typescript
// 直方图色柱：bar 根据 bin_center 正负分色
// 正态拟合：line 使用 API 返回的 normal_fit 数据
series: [
  {
    type: 'bar',
    data: histogram.map(b => [b.bin_center, b.count]),
    itemStyle: {
      color: (p: any) => p.value[0] >= 0 ? '#67c23a' : '#f56c6c',
    },
  },
  {
    type: 'line',
    data: normalFit.map(d => [d.x, d.density]),
    smooth: true,
    lineStyle: { color: '#e6a23c', type: 'dashed', width: 2 },
    symbol: 'none',
  },
]
```

### 5.3 QQ Plot

```typescript
// scatter: API 返回的 qq_plot 数据
// line: 对角线 y=x
series: [
  {
    type: 'scatter',
    data: qqPlot.map(d => [d.theoretical, d.sample]),
    symbolSize: 3,
    itemStyle: { opacity: 0.5 },
  },
  {
    type: 'line',
    data: [[-4, -4], [4, 4]],
    lineStyle: { color: '#e6a23c', type: 'dashed' },
    symbol: 'none',
    silent: true,
  },
]
```

## 六、文件清单

### 新增

| 文件 | 说明 |
|------|------|
| `docs/analysis-module-design.md` | 本设计文档 |
| `frontend/src/components/CorrelationTab.vue` | 剥离自 Analysis.vue |
| `frontend/src/components/DrawdownTab.vue` | 回撤 tab |
| `frontend/src/components/SharpeTab.vue` | 夏普 tab |
| `frontend/src/components/DistributionTab.vue` | 分布 tab |

### 修改（灰度标出的是已有文件，需重构/扩展）

| 文件 | 变更 |
|------|------|
| `backend/app/api/v1/analysis.py` | 新增三个端点 + `_get_daily_returns()` + 参数校验；correlation 端点保持现有 JOIN 逻辑不变 |
| `frontend/src/views/Analysis.vue` | 重写为 tab shell（per-tab 状态管理 + 公共控件） |
| `frontend/src/api/index.ts` | analysisApi 新增 `getDrawdown` / `getSharpe` / `getDistribution` |
| `backend/requirements.txt` | +scipy |
| `backend/pyproject.toml` | +scipy |

## 七、实施顺序

| 步骤 | 内容 | 预计改动 |
|:---:|------|:---:|
| 1 | 后端：`_validate_params()` + `_get_daily_returns()` 公共函数 | ~40 行 |
| 2 | 后端：drawdown / sharpe / distribution 三个新端点 | ~180 行 |
| 3 | 后端：安装 scipy，更新 requirements.txt + pyproject.toml | 3 行 |
| 4 | 前端 API：analysisApi 新增三个方法 | ~10 行 |
| 5 | 前端：Analysis.vue → tab shell（per-tab 状态管理） | 重写 ~100 行 |
| 6 | 前端：CorrelationTab.vue（从现有 Analysis.vue 剥离） | ~150 行 |
| 7 | 前端：DrawdownTab.vue | ~120 行 |
| 8 | 前端：SharpeTab.vue | ~100 行 |
| 9 | 前端：DistributionTab.vue | ~150 行 |
| 10 | 验证（见第八节） | — |

## 八、验证方案

### 8.1 后端固定样本测试

用 **000001.SZ 的 2024-2025 固定区间**作为基准样本集（484 个交易日），对每个端点验证以下边界条件：

| 端点 | 测试用例 | 预期 |
|------|----------|------|
| drawdown | 正常区间 2024-2025 | max_dd ∈ (-0.25, 0)，有 recovery_date |
| drawdown | 极短区间 30 天 | 正常返回，至少 1 条 equity_curve |
| drawdown | top_n=1 | 返回 1 条 top_drawdowns |
| drawdown | 全涨区间（挑选某只持续上涨的股票） | max_dd = 0，top_drawdowns 为空或 depth=0 |
| sharpe | 正常区间 | rolling_sharpe 长度 = 484 - 252 + 1 = 233 |
| sharpe | window > len(returns) | window 自动缩小为 min(window, len(returns)) |
| sharpe | len(returns) < 21 | rolling_sharpe 为空，summary 正常计算 |
| sharpe | 零波动（选单只股票停牌区间） | ann_vol = 0 → sharpe = 0（非除零异常） |
| distribution | 正常区间 | is_normal = false（大概率），qq_plot 存在 |
| distribution | 全涨区间 | skew > 0，无负收益日 |
| distribution | bins 边界（1 个桶 vs 200 个桶） | 均正常返回，histogram 长度 = bins |
| correlation | stock 和 benchmark 无重叠交易日 | 404 + 明确错误信息，非 500 |
| 全部 | 无效 stock code（含 SQL 元字符） | 422 Unprocessable Entity |
| 全部 | start_date > end_date | 422 |
| 全部 | 数据文件不存在 | 404 |

### 8.2 前端编译验证

```
npx vue-tsc --noEmit           # 零错误
npm run build                   # 零 warning
```

### 8.3 交互验证

- 切换 tab 不触发 API 请求（只有点击"计算"才请求）
- 为 tab A 计算完后，切换到 tab B 再切回来，tab A 的结果仍在（不被清空）
- 修改股票代码后点击计算，同一 tab 的结果被新结果覆盖
- 修改日期区间后点击计算，结果正确反映新区间
- 错误状态在 tab 内展示，不影响其他 tab
