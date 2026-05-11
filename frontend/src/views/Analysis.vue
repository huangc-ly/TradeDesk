<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch, nextTick } from 'vue'
import * as echarts from 'echarts'
import { marketApi, analysisApi } from '@/api'

interface StockBasic {
  ts_code: string
  symbol: string
  name: string
}

const stocks = ref<StockBasic[]>([])
const indexes = ref<string[]>([])

const stockSearch = ref('')
const benchSearch = ref('')
const stock = ref('000001.SZ')
const benchmark = ref('000001.SH')
const dateRange = ref<[string, string]>(['2024-01-01', '2025-12-31'])

const loading = ref(false)
const result = ref<any>(null)
const error = ref('')

const scatterRef = ref<HTMLDivElement>()
const cumulativeRef = ref<HTMLDivElement>()
let scatterChart: echarts.ECharts | null = null
let cumulativeChart: echarts.ECharts | null = null

const filteredStocks = computed(() => {
  if (!stockSearch.value) return []
  const kw = stockSearch.value.toLowerCase()
  return stocks.value
    .filter((s) => s.ts_code.toLowerCase().includes(kw) || s.name.toLowerCase().includes(kw) || s.symbol.includes(kw))
    .slice(0, 50)
})

const filteredIndexes = computed(() => {
  if (!benchSearch.value) return []
  const kw = benchSearch.value.toLowerCase()
  return indexes.value.filter((i) => i.toLowerCase().includes(kw)).slice(0, 50)
})

onMounted(async () => {
  try {
    const [sRes, iRes] = await Promise.all([
      marketApi.getStocks(),
      marketApi.getIndexes(),
    ])
    stocks.value = (sRes as any).stocks ?? []
    indexes.value = (iRes as any).indexes ?? []
  } catch (e) {
    console.error('Failed to load pickers:', e)
  }
})

function disposeCharts() {
  if (scatterChart) {
    scatterChart.dispose()
    scatterChart = null
  }
  if (cumulativeChart) {
    cumulativeChart.dispose()
    cumulativeChart = null
  }
}

onUnmounted(() => disposeCharts())

async function calculate() {
  if (!stock.value || !benchmark.value) return
  loading.value = true
  error.value = ''
  // Dispose old charts before clearing result (they reference DOM about to be removed)
  disposeCharts()
  result.value = null
  try {
    const res = await analysisApi.getCorrelation({
      stock: stock.value,
      benchmark: benchmark.value,
      start_date: dateRange.value[0],
      end_date: dateRange.value[1],
    })
    result.value = res
    // Wait for v-if render + Element Plus card layout
    await nextTick()
    await nextTick()
    renderCharts()
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? e?.message ?? '请求失败'
  } finally {
    loading.value = false
  }
}

function renderCharts() {
  if (!result.value?.returns?.length) {
    console.warn('renderCharts: no returns data')
    return
  }

  const returns = result.value.returns as any[]
  const stockRet: number[] = returns.map((r: any) => r.stock_return)
  const benchRet: number[] = returns.map((r: any) => r.benchmark_return)

  // --- Scatter chart ---
  const sc = scatterRef.value
  if (!sc) {
    console.warn('scatterRef is null')
    return
  }
  // Always create a fresh instance
  if (scatterChart) scatterChart.dispose()
  scatterChart = echarts.init(sc)

  const beta = result.value.beta ?? 0
  const alpha = result.value.alpha ?? 0
  const xMin = Math.min(...benchRet)
  const xMax = Math.max(...benchRet)

  scatterChart.setOption({
    tooltip: {
      trigger: 'item',
      formatter: (p: any) =>
        `个股: ${(p.value[1] * 100).toFixed(2)}%<br/>大盘: ${(p.value[0] * 100).toFixed(2)}%`,
    },
    xAxis: {
      name: '基准收益率',
      axisLabel: { formatter: (v: number) => (v * 100).toFixed(0) + '%' },
    },
    yAxis: {
      name: '个股收益率',
      axisLabel: { formatter: (v: number) => (v * 100).toFixed(0) + '%' },
    },
    series: [
      {
        type: 'scatter',
        data: benchRet.map((x: number, i: number) => [x, stockRet[i]]),
        symbolSize: 5,
        itemStyle: { color: '#409eff', opacity: 0.4 },
      },
      {
        type: 'line',
        data: [
          [xMin, alpha + beta * xMin],
          [xMax, alpha + beta * xMax],
        ],
        lineStyle: { color: '#e6a23c', width: 2, type: 'dashed' },
        silent: true,
        symbol: 'none',
      },
    ],
  })

  // --- Cumulative returns chart ---
  const cu = cumulativeRef.value
  if (!cu) {
    console.warn('cumulativeRef is null')
    return
  }
  if (cumulativeChart) cumulativeChart.dispose()
  cumulativeChart = echarts.init(cu)

  const dates: string[] = []
  const cumStock: number[] = []
  const cumBench: number[] = []
  let cs = 1
  let cb = 1
  for (const r of returns) {
    cs *= 1 + r.stock_return
    cb *= 1 + r.benchmark_return
    dates.push(r.trade_date.slice(0, 10)) // "2024-01-03"
    cumStock.push(+(cs - 1).toFixed(4))
    cumBench.push(+(cb - 1).toFixed(4))
  }

  cumulativeChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: [stock.value, benchmark.value], bottom: 0 },
    grid: { left: '10%', right: '4%', top: '5%', bottom: '12%' },
    xAxis: { type: 'category', data: dates },
    yAxis: {
      type: 'value',
      axisLabel: { formatter: (v: number) => (v * 100).toFixed(0) + '%' },
    },
    series: [
      {
        name: stock.value,
        type: 'line',
        data: cumStock,
        lineStyle: { width: 2 },
        showSymbol: false,
      },
      {
        name: benchmark.value,
        type: 'line',
        data: cumBench,
        lineStyle: { width: 2 },
        showSymbol: false,
      },
    ],
  })
}

watch(stock, () => {
  disposeCharts()
  result.value = null
})
watch(benchmark, () => {
  disposeCharts()
  result.value = null
})
</script>

<template>
  <div>
    <h2 style="margin-bottom: 20px">相关性分析</h2>

    <el-card style="margin-bottom: 20px">
      <el-form :inline="true">
        <el-form-item label="股票">
          <el-select
            v-model="stock"
            filterable
            remote
            :remote-method="(q: string) => (stockSearch = q)"
            placeholder="搜索股票"
            style="width: 340px"
            clearable
          >
            <el-option
              v-for="s in filteredStocks"
              :key="s.ts_code"
              :label="`${s.ts_code}  ${s.name}`"
              :value="s.ts_code"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="基准">
          <el-select
            v-model="benchmark"
            filterable
            remote
            :remote-method="(q: string) => (benchSearch = q)"
            placeholder="搜索指数"
            style="width: 240px"
            clearable
          >
            <el-option
              v-for="idx in filteredIndexes"
              :key="idx"
              :label="idx"
              :value="idx"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="区间">
          <el-date-picker
            v-model="dateRange"
            type="daterange"
            range-separator="~"
            start-placeholder="开始"
            end-placeholder="结束"
            value-format="YYYY-MM-DD"
          />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="calculate" :loading="loading">
            {{ loading ? '计算中...' : '计算' }}
          </el-button>
        </el-form-item>
      </el-form>

      <el-alert v-if="error" :title="error" type="error" show-icon closable @close="error = ''" />
    </el-card>

    <div v-if="result">
      <!-- Row 1: Point estimates -->
      <el-row :gutter="16" style="margin-bottom: 16px">
        <el-col :span="4">
          <el-card shadow="hover">
            <template #header>Beta (β)</template>
            <div style="font-size: 22px; font-weight: bold; color: #409eff">{{ result.beta }}</div>
            <div style="font-size: 11px; color: #909399">
              {{ result.beta > 1 ? '波动大于大盘' : result.beta > 0 ? '波动小于大盘' : '与大盘反向' }}
            </div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card shadow="hover">
            <template #header>相关性 (r)</template>
            <div style="font-size: 22px; font-weight: bold"
              :style="{ color: result.correlation > 0.5 ? '#67c23a' : result.correlation > 0 ? '#e6a23c' : '#f56c6c' }">
              {{ result.correlation }}
            </div>
            <div style="font-size: 11px; color: #909399">
              {{ result.correlation > 0.7 ? '强相关' : result.correlation > 0.4 ? '中等相关' : '弱相关' }}
            </div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card shadow="hover">
            <template #header>R² / Adj R²</template>
            <div style="font-size: 22px; font-weight: bold; color: #409eff">
              {{ result.r_squared }} <span style="font-size: 14px; color: #909399">/ {{ result.adj_r_squared }}</span>
            </div>
            <div style="font-size: 11px; color: #909399">决定系数 / 调整后</div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card shadow="hover">
            <template #header>Alpha (α)</template>
            <div style="font-size: 22px; font-weight: bold"
              :style="{ color: result.alpha > 0 ? '#67c23a' : '#f56c6c' }">
              {{ (result.alpha * 100).toFixed(4) }}%
            </div>
            <div style="font-size: 11px; color: #909399">
              {{ result.alpha > 0 ? '超额为正' : '超额为负' }}
            </div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card shadow="hover">
            <template #header>样本数</template>
            <div style="font-size: 22px; font-weight: bold; color: #409eff">{{ result.data_points }}</div>
            <div style="font-size: 11px; color: #909399">个交易日</div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card shadow="hover">
            <template #header>F 统计量</template>
            <div style="font-size: 22px; font-weight: bold; color: #409eff">{{ result.f_statistic }}</div>
            <div style="font-size: 11px; color: #909399">p = {{ result.f_pvalue.toFixed(6) }}</div>
          </el-card>
        </el-col>
      </el-row>

      <!-- Row 2: Statistical inference -->
      <el-row :gutter="16" style="margin-bottom: 20px">
        <el-col :span="12">
          <el-card shadow="hover">
            <template #header>
              β 显著性检验
              <el-tag v-if="result.beta_pvalue < 0.01" type="success" size="small" style="margin-left: 8px">*** 1% 显著</el-tag>
              <el-tag v-else-if="result.beta_pvalue < 0.05" type="warning" size="small" style="margin-left: 8px">** 5% 显著</el-tag>
              <el-tag v-else-if="result.beta_pvalue < 0.1" size="small" style="margin-left: 8px">* 10% 显著</el-tag>
              <el-tag v-else type="danger" size="small" style="margin-left: 8px">不显著</el-tag>
            </template>
            <el-descriptions :column="3" size="small" border>
              <el-descriptions-item label="p 值">{{ result.beta_pvalue.toFixed(6) }}</el-descriptions-item>
              <el-descriptions-item label="标准误">{{ result.beta_std_err }}</el-descriptions-item>
              <el-descriptions-item label="t 值">{{ result.beta_tvalue }}</el-descriptions-item>
              <el-descriptions-item label="95% CI 下界">{{ result.beta_ci_lower }}</el-descriptions-item>
              <el-descriptions-item label="95% CI 上界">{{ result.beta_ci_upper }}</el-descriptions-item>
              <el-descriptions-item label="H₀">β = 0</el-descriptions-item>
            </el-descriptions>
          </el-card>
        </el-col>
        <el-col :span="12">
          <el-card shadow="hover">
            <template #header>
              α 显著性检验
              <el-tag v-if="result.alpha_pvalue < 0.01" type="success" size="small" style="margin-left: 8px">*** 1% 显著</el-tag>
              <el-tag v-else-if="result.alpha_pvalue < 0.05" type="warning" size="small" style="margin-left: 8px">** 5% 显著</el-tag>
              <el-tag v-else-if="result.alpha_pvalue < 0.1" size="small" style="margin-left: 8px">* 10% 显著</el-tag>
              <el-tag v-else type="danger" size="small" style="margin-left: 8px">不显著</el-tag>
            </template>
            <el-descriptions :column="3" size="small" border>
              <el-descriptions-item label="p 值">{{ result.alpha_pvalue.toFixed(6) }}</el-descriptions-item>
              <el-descriptions-item label="标准误">{{ result.alpha_std_err }}</el-descriptions-item>
              <el-descriptions-item label="t 值">{{ result.alpha_tvalue ?? 'N/A' }}</el-descriptions-item>
              <el-descriptions-item label="95% CI 下界">{{ result.alpha_ci_lower }}</el-descriptions-item>
              <el-descriptions-item label="95% CI 上界">{{ result.alpha_ci_upper }}</el-descriptions-item>
              <el-descriptions-item label="H₀">α = 0</el-descriptions-item>
            </el-descriptions>
          </el-card>
        </el-col>
      </el-row>

      <el-row :gutter="20">
        <el-col :span="12">
          <el-card>
            <template #header>收益率散点图</template>
            <div ref="scatterRef" style="width: 100%; height: 420px" />
          </el-card>
        </el-col>
        <el-col :span="12">
          <el-card>
            <template #header>累计收益对比</template>
            <div ref="cumulativeRef" style="width: 100%; height: 420px" />
          </el-card>
        </el-col>
      </el-row>
    </div>

    <el-empty v-else description="选择股票和基准指数，点击「计算」开始分析" />
  </div>
</template>
