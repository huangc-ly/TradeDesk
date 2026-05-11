<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { marketApi, analysisApi } from '@/api'
import CorrelationTab from '@/components/CorrelationTab.vue'
import DrawdownTab from '@/components/DrawdownTab.vue'
import SharpeTab from '@/components/SharpeTab.vue'
import DistributionTab from '@/components/DistributionTab.vue'

interface StockBasic {
  ts_code: string
  symbol: string
  name: string
}

interface TabState {
  loading: boolean
  error: string
  data: any | null
}

// --- Pickers data ---
const stocks = ref<StockBasic[]>([])
const indexes = ref<string[]>([])
const stockSearch = ref('')
const benchSearch = ref('')

// --- Shared controls ---
const stock = ref('000001.SZ')
const benchmark = ref('000001.SH')
const dateRange = ref<[string, string]>(['2024-01-01', '2025-12-31'])

// --- Tab management ---
const activeTab = ref('correlation')

const tabStates = ref<Record<string, TabState>>({
  correlation:  { loading: false, error: '', data: null },
  drawdown:     { loading: false, error: '', data: null },
  sharpe:       { loading: false, error: '', data: null },
  distribution: { loading: false, error: '', data: null },
})

const tabComponents: Record<string, any> = {
  correlation: CorrelationTab,
  drawdown: DrawdownTab,
  sharpe: SharpeTab,
  distribution: DistributionTab,
}

const activeTabComp = computed(() => tabComponents[activeTab.value])

// --- Stock/index picker filtering ---
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

// --- Endpoint mapping ---
const ENDPOINTS: Record<string, () => Promise<any>> = {
  correlation: () =>
    analysisApi.getCorrelation({
      stock: stock.value,
      benchmark: benchmark.value,
      start_date: dateRange.value[0],
      end_date: dateRange.value[1],
    }),
  drawdown: () =>
    analysisApi.getDrawdown({
      stock: stock.value,
      start_date: dateRange.value[0],
      end_date: dateRange.value[1],
    }),
  sharpe: () =>
    analysisApi.getSharpe({
      stock: stock.value,
      start_date: dateRange.value[0],
      end_date: dateRange.value[1],
    }),
  distribution: () =>
    analysisApi.getDistribution({
      stock: stock.value,
      start_date: dateRange.value[0],
      end_date: dateRange.value[1],
    }),
}

async function calculate() {
  const tab = activeTab.value
  const state = tabStates.value[tab]
  state.loading = true
  state.error = ''
  state.data = null
  try {
    state.data = await ENDPOINTS[tab]()
  } catch (e: any) {
    state.error = e?.response?.data?.detail ?? e?.message ?? '请求失败'
  } finally {
    state.loading = false
  }
}

function onTabChange(_name: string) {
  // Switching tabs preserves results — no-op
}

function clearTabError(tab: string) {
  tabStates.value[tab].error = ''
}
</script>

<template>
  <div>
    <h2 style="margin-bottom: 20px">量化分析</h2>

    <!-- Controls bar -->
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

        <el-form-item v-if="activeTab === 'correlation'" label="基准">
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
          <el-button type="primary" @click="calculate" :loading="tabStates[activeTab].loading">
            {{ tabStates[activeTab].loading ? '计算中...' : '计算' }}
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- Tabs -->
    <el-tabs v-model="activeTab" @tab-change="onTabChange">
      <el-tab-pane name="correlation" label="相关性" />
      <el-tab-pane name="drawdown" label="回撤" />
      <el-tab-pane name="sharpe" label="夏普" />
      <el-tab-pane name="distribution" label="分布" />
    </el-tabs>

    <!-- Per-tab error display -->
    <el-alert
      v-if="tabStates[activeTab].error"
      :title="tabStates[activeTab].error"
      type="error"
      show-icon
      closable
      style="margin-bottom: 16px"
      @close="clearTabError(activeTab)"
    />

    <!-- Dynamic tab component -->
    <component
      :is="activeTabComp"
      v-if="tabStates[activeTab].data"
      :result="tabStates[activeTab].data"
      :stock-name="stock"
      :benchmark-name="benchmark"
    />

    <!-- Empty state -->
    <el-empty
      v-if="!tabStates[activeTab].data && !tabStates[activeTab].loading"
      description="选择股票和参数，点击「计算」开始分析"
    />
  </div>
</template>
