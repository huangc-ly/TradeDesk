<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { marketApi, financeApi } from '@/api'

interface StockBasic {
  ts_code: string
  symbol: string
  name: string
}

interface GroupDef {
  label: string
  col: string | null
  is_total: boolean
}

interface FinanceData {
  code: string
  dates: string[]
  data: Record<string, number | null>[]
  groups: GroupDef[]
  comp_type?: string
  comp_type_label?: string
}

interface ForecastItem {
  ann_date: string
  end_date: string
  type: string
  p_change_min: number | null
  p_change_max: number | null
  net_profit_min: number | null
  net_profit_max: number | null
  summary: string
  change_reason: string
}

const stocks = ref<StockBasic[]>([])
const selectedCode = ref('')
const selectedName = ref('')
const stockSearch = ref('')
const compType = ref('1')
const periods = ref(8)
const activeTab = ref('balance')
const result = ref<FinanceData | null>(null)
const forecasts = ref<ForecastItem[]>([])
const loading = ref(false)
const error = ref('')

const filteredStocks = computed(() => {
  if (!stockSearch.value) return []
  const kw = stockSearch.value.toLowerCase()
  return stocks.value
    .filter(
      (s) =>
        s.ts_code.toLowerCase().includes(kw) ||
        s.name.toLowerCase().includes(kw) ||
        s.symbol.includes(kw),
    )
    .slice(0, 50)
})

const tabEndpoints: Record<string, (code: string) => Promise<any>> = {
  balance: (code) =>
    financeApi.getBalanceSheet({ code, periods: periods.value, comp_type: compType.value }),
  income: (code) =>
    financeApi.getIncomeStatement({ code, periods: periods.value, comp_type: compType.value }),
  cashflow: (code) =>
    financeApi.getCashFlow({ code, periods: periods.value, comp_type: compType.value }),
  indicators: (code) =>
    financeApi.getIndicators(code, periods.value),
  forecast: (code) =>
    financeApi.getForecast(code),
}

// ── Table rows for statement tabs ──
const tableRows = computed(() => {
  if (!result.value) return []
  const { groups, data, dates } = result.value

  return groups.map((g, gi) => {
    if (g.col === null) return { _key: `sp_${gi}`, label: '', _spacer: true }

    const row: any = {
      _key: `${g.col}_${gi}`,
      _col: g.col,
      label: g.label,
      _bold: g.is_total,
      _section: !g.is_total && g.label.length > 0 && !g.label.startsWith('  '),
      _sub: g.label.startsWith('  '),
    }

    dates.forEach((_, i) => {
      const rec = data[i]
      row[`v${i}`] = rec ? (rec as any)[g.col!] : null
    })

    return row
  })
})

// ── Forecast table rows ──
const forecastRows = computed(() => {
  return forecasts.value.map((f) => ({
    end_date: f.end_date,
    type: forecastTypeLabel(f.type),
    p_change: f.p_change_min != null && f.p_change_max != null
      ? `${(f.p_change_min * 100).toFixed(1)}% ~ ${(f.p_change_max * 100).toFixed(1)}%`
      : '--',
    net_profit:
      f.net_profit_min != null && f.net_profit_max != null
        ? `${fmtAmount(f.net_profit_min)} ~ ${fmtAmount(f.net_profit_max)}`
        : '--',
    summary: f.summary || '--',
    reason: f.change_reason || '',
  }))
})

// ── Lifecycle ──
onMounted(async () => {
  try {
    const res = await marketApi.getStocks()
    stocks.value = (res as any).stocks ?? []
  } catch (e) {
    console.error('Failed to load stocks:', e)
  }
})

watch([selectedCode, activeTab, periods, compType], () => {
  if (selectedCode.value) loadData()
})

function onSelect(code: string) {
  const found = stocks.value.find((s) => s.ts_code === code)
  selectedName.value = found ? `${found.ts_code} ${found.name}` : code
  if (code) loadData()
}

async function loadData() {
  if (!selectedCode.value) return
  const tab = activeTab.value

  if (tab === 'forecast') {
    loading.value = true
    error.value = ''
    result.value = null
    try {
      const res = await tabEndpoints.forecast(selectedCode.value) as any
      forecasts.value = res.forecasts ?? []
    } catch (e: any) {
      error.value = e?.response?.data?.detail ?? e?.message ?? '加载失败'
    } finally {
      loading.value = false
    }
    return
  }

  loading.value = true
  error.value = ''
  result.value = null
  try {
    const res = await tabEndpoints[tab](selectedCode.value) as any
    result.value = res
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? e?.message ?? '加载失败'
  } finally {
    loading.value = false
  }
}

// ── Formatting ──
function quarterLabel(dateStr: string): string {
  if (!dateStr) return ''
  const m = dateStr.slice(5, 7)
  const y = dateStr.slice(2, 4)
  const qMap: Record<string, string> = { '03': 'Q1', '06': 'Q2', '09': 'Q3', '12': 'Q4' }
  return `${y}${qMap[m] || m}`
}

function fmtAmount(v: any): string {
  if (v == null || Number.isNaN(v)) return '--'
  const n = Number(v)
  const abs = Math.abs(n)
  const sign = n < 0 ? '-' : ''
  if (abs >= 1e8) return `${sign}${(abs / 1e8).toFixed(2)}亿`
  if (abs >= 1e4) return `${sign}${(abs / 1e4).toFixed(0)}万`
  if (abs >= 1) return `${sign}${abs.toFixed(2)}`
  return `${sign}${abs.toFixed(4)}`
}

function fmtPct(v: any): string {
  if (v == null || Number.isNaN(v)) return '--'
  return `${Number(v).toFixed(2)}%`
}

function fmtVal(col: string | null, v: any): string {
  if (v == null || Number.isNaN(v)) return '--'
  const indicatorCols = ['roe', 'roe_yearly', 'roa', 'roa_yearly', 'netprofit_margin',
    'profit_to_gr', 'op_of_gr', 'ocf_to_or', 'debt_to_assets']
  if (col && indicatorCols.includes(col)) return fmtPct(v)

  const ratioCols = ['current_ratio', 'quick_ratio', 'basic_eps', 'eps', 'bps']
  if (col && ratioCols.includes(col)) return Number(v).toFixed(4)

  return fmtAmount(v)
}

function fmtLabelDate(d: string): string {
  if (!d) return ''
  const parts = d.split('-')
  return `${parts[0]}-${parts[1]}-${parts[2]}`
}

function forecastTypeLabel(t: string): string {
  const map: Record<string, string> = {
    '1': '预增', '2': '预减', '3': '扭亏', '4': '首亏',
    '5': '续盈', '6': '续亏', '7': '略增', '8': '略减',
  }
  return map[t] || t
}

function forecastTypeTag(t: string): 'success' | 'danger' | 'warning' | 'info' {
  if (t === '1' || t === '3' || t === '7') return 'success'
  if (t === '2' || t === '4' || t === '8') return 'danger'
  if (t === '6') return 'danger'
  return 'info'
}
</script>

<template>
  <div>
    <h2 style="margin-bottom: 20px">财务报表</h2>

    <!-- ═══ Toolbar ═══ -->
    <el-card style="margin-bottom: 16px">
      <el-form :inline="true">
        <el-form-item label="股票">
          <el-select
            v-model="selectedCode"
            filterable
            remote
            :remote-method="(q: string) => (stockSearch = q)"
            placeholder="搜索代码或名称"
            style="width: 320px"
            clearable
            @change="onSelect"
          >
            <el-option
              v-for="s in filteredStocks"
              :key="s.ts_code"
              :label="`${s.ts_code}  ${s.name}`"
              :value="s.ts_code"
            />
          </el-select>
        </el-form-item>

        <el-form-item v-if="activeTab !== 'indicators' && activeTab !== 'forecast'" label="报表类型">
          <el-radio-group v-model="compType" size="small">
            <el-radio-button value="1">合并报表</el-radio-button>
            <el-radio-button value="2">母公司</el-radio-button>
          </el-radio-group>
          <el-tag v-if="result?.comp_type && result.comp_type !== compType" size="small" type="warning" style="margin-left: 8px">
            已切换至{{ result.comp_type_label }}
          </el-tag>
        </el-form-item>

        <el-form-item v-if="activeTab !== 'forecast'" label="期数">
          <el-select v-model="periods" style="width: 100px">
            <el-option :value="4" label="4期" />
            <el-option :value="8" label="8期" />
            <el-option :value="12" label="12期" />
            <el-option :value="20" label="20期" />
          </el-select>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- ═══ Tabs ═══ -->
    <el-card>
      <el-tabs v-model="activeTab" @tab-change="loadData">
        <el-tab-pane name="balance" label="资产负债表" />
        <el-tab-pane name="income" label="利润表" />
        <el-tab-pane name="cashflow" label="现金流量表" />
        <el-tab-pane name="indicators" label="财务指标" />
        <el-tab-pane name="forecast" label="业绩预告" />
      </el-tabs>

      <!-- Error -->
      <el-alert
        v-if="error"
        :title="error"
        type="error"
        show-icon
        closable
        style="margin-bottom: 12px"
        @close="error = ''"
      />

      <!-- Empty -->
      <el-empty v-if="!selectedCode" description="请选择股票查看财报" />

      <!-- Loading -->
      <div v-if="selectedCode" v-loading="loading" style="min-height: 200px">
        <!-- ═══ Statement / Indicators table ═══ -->
        <div
          v-if="result && activeTab !== 'forecast'"
          class="statement-table-wrapper"
        >
          <table class="statement-table">
            <thead>
              <tr>
                <th class="col-label">项目</th>
                <th
                  v-for="d in result.dates"
                  :key="d"
                  class="col-value"
                  :title="fmtLabelDate(d)"
                >
                  {{ quarterLabel(d) }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in tableRows"
                :key="row._key"
                :class="{
                  'row-bold': row._bold,
                  'row-section': row._section,
                  'row-spacer': row._spacer,
                }"
              >
                <td
                  class="col-label"
                  :class="{
                    'cell-bold': row._bold,
                    'cell-section': row._section,
                    'cell-sub': row._sub,
                  }"
                >
                  {{ row.label }}
                </td>
                <td
                  v-for="(d, i) in result.dates"
                  :key="d"
                  class="col-value"
                  :class="{ 'cell-bold': row._bold }"
                >
                  {{ fmtVal(row._col, row[`v${i}`]) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- ═══ Forecast table ═══ -->
        <div v-if="activeTab === 'forecast' && forecasts.length > 0">
          <el-table :data="forecastRows" stripe max-height="600">
            <el-table-column prop="end_date" label="报告期" width="110" sortable />
            <el-table-column prop="type" label="预告类型" width="90">
              <template #default="{ row }">
                <el-tag :type="forecastTypeTag(row.type)" size="small">
                  {{ row.type }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="p_change" label="净利润变动" width="160" />
            <el-table-column prop="net_profit" label="净利润区间" width="220" />
            <el-table-column prop="summary" label="摘要" min-width="200" show-overflow-tooltip />
            <el-table-column prop="reason" label="变动原因" min-width="200" show-overflow-tooltip />
          </el-table>
        </div>

        <el-empty
          v-if="activeTab === 'forecast' && !loading && forecasts.length === 0 && !error"
          description="该股票暂无业绩预告数据"
        />
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.statement-table-wrapper {
  overflow-x: auto;
}

.statement-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  white-space: nowrap;
}

.statement-table th,
.statement-table td {
  padding: 5px 12px;
  border-bottom: 1px solid #ebeef5;
  text-align: right;
}

.statement-table th {
  background: #f5f7fa;
  color: #606266;
  font-weight: 600;
  position: sticky;
  top: 0;
  z-index: 1;
}

.statement-table .col-label {
  text-align: left;
  min-width: 180px;
  position: sticky;
  left: 0;
  background: #fff;
  z-index: 1;
}

.statement-table th.col-label {
  background: #f5f7fa;
  z-index: 2;
}

.row-bold {
  background: #fafafa;
}

.row-section .col-label {
  font-weight: 600;
  color: #303133;
  background: #f5f7fa;
}

.row-spacer {
  height: 8px;
}

.row-spacer td {
  border-bottom: none;
  background: #fff;
}

.cell-bold {
  font-weight: 700;
  color: #303133;
}

.cell-section {
  font-weight: 600;
  color: #303133;
}

.cell-sub {
  padding-left: 24px !important;
  color: #606266;
}
</style>
