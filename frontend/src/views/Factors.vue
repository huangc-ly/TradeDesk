<script setup lang="ts">
import { ref, onMounted, computed, nextTick } from 'vue'
import * as echarts from 'echarts'
import { factorsApi } from '@/api'

interface FactorMeta {
  id: string
  name: string
  category: string
  type: string
  description: string
  lookback_days: number
}

interface FactorStats {
  count_valid: number
  count_null: number
  mean: number
  std: number
  min: number
  max: number
  q25: number
  median: number
  q75: number
}

interface FactorResult {
  factor_id: string
  factor_name: string
  date: string
  category: string
  stats: FactorStats
  top_10: { ts_code: string; value: number }[]
  bottom_10: { ts_code: string; value: number }[]
  all_values: { ts_code: string; value: number }[]
}

const CATEGORIES = ['all', 'value', 'size', 'momentum', 'volatility', 'liquidity']
const CATEGORY_LABELS: Record<string, string> = {
  all: '全部', value: '价值', size: '规模', momentum: '动量', volatility: '波动', liquidity: '流动性',
}

const factors = ref<FactorMeta[]>([])
const activeCategory = ref('all')
const result = ref<FactorResult | null>(null)
const loading = ref(false)
const error = ref('')
const computeDate = ref('')
const latestDate = ref('')
const showDateDialog = ref(false)
const activeFactor = ref<FactorMeta | null>(null)

const histogramRef = ref<HTMLDivElement>()
let histogramChart: echarts.ECharts | null = null

const filteredFactors = computed(() => {
  if (activeCategory.value === 'all') return factors.value
  return factors.value.filter((f) => f.category === activeCategory.value)
})

onMounted(async () => {
  try {
    const [fRes, dRes] = await Promise.all([
      factorsApi.listFactors(),
      factorsApi.getLatestDate(),
    ])
    factors.value = (fRes as any).factors ?? []
    latestDate.value = (dRes as any).latest_date ?? ''
    computeDate.value = latestDate.value
  } catch (e) {
    console.error('Failed to load factors:', e)
  }
})

function openCompute(factor: FactorMeta) {
  activeFactor.value = factor
  computeDate.value = latestDate.value || ''
  showDateDialog.value = true
}

async function doCompute() {
  if (!activeFactor.value || !computeDate.value) return
  showDateDialog.value = false
  loading.value = true
  error.value = ''
  result.value = null
  try {
    const res = await factorsApi.computeValues(activeFactor.value.id, computeDate.value)
    result.value = res as any
    await nextTick()
    await nextTick()
    renderHistogram()
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? e?.message ?? '计算失败'
  } finally {
    loading.value = false
  }
}

function renderHistogram() {
  if (!histogramRef.value || !result.value) return
  if (histogramChart) histogramChart.dispose()

  const values = result.value.all_values.map((v) => v.value)
  histogramChart = echarts.init(histogramRef.value)

  const mean = result.value.stats.mean
  const std = result.value.stats.std

  // Build histogram bins
  const binCount = 50
  const vmin = Math.min(...values)
  const vmax = Math.max(...values)
  const binW = (vmax - vmin) / binCount || 1
  const bins: number[] = new Array(binCount).fill(0)
  values.forEach((v) => {
    const idx = Math.min(Math.floor((v - vmin) / binW), binCount - 1)
    bins[idx]++
  })
  const xData = bins.map((_, i) => +(vmin + (i + 0.5) * binW).toFixed(4))

  // Normal curve
  const normalData = xData.map((x) => {
    const d = (1 / (std * Math.sqrt(2 * Math.PI))) * Math.exp(-0.5 * ((x - mean) / std) ** 2)
    return +(d * values.length * binW).toFixed(4)
  })

  histogramChart.setOption({
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: xData, axisLabel: { show: false } },
    yAxis: { type: 'value' },
    series: [
      {
        type: 'bar', data: bins,
        itemStyle: { color: (p: any) => +xData[p.dataIndex] >= 0 ? '#67c23a' : '#f56c6c', opacity: 0.7 },
      },
      {
        type: 'line', data: normalData, smooth: true,
        lineStyle: { color: '#e6a23c', type: 'dashed', width: 2 },
        symbol: 'none',
      },
    ],
  })
}

</script>

<template>
  <div>
    <h2 style="margin-bottom: 20px">因子库</h2>

    <!-- Category tabs -->
    <el-card style="margin-bottom: 20px">
      <el-radio-group v-model="activeCategory" size="default">
        <el-radio-button v-for="c in CATEGORIES" :key="c" :value="c">
          {{ CATEGORY_LABELS[c] }}
        </el-radio-button>
      </el-radio-group>
    </el-card>

    <!-- Error -->
    <el-alert v-if="error" :title="error" type="error" show-icon closable style="margin-bottom: 16px" @close="error = ''" />

    <!-- Factor cards grid -->
    <el-row :gutter="16" v-loading="loading">
      <el-col v-for="f in filteredFactors" :key="f.id" :span="8" style="margin-bottom: 16px">
        <el-card shadow="hover">
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center">
              <span style="font-weight: 600">{{ f.name }}</span>
              <div>
                <el-tag size="small" type="info" style="margin-right: 4px">{{ CATEGORY_LABELS[f.category] || f.category }}</el-tag>
                <el-tag size="small" :type="f.type === 'raw' ? 'success' : 'warning'">{{ f.type === 'raw' ? '原始' : '窗口' }}</el-tag>
              </div>
            </div>
          </template>
          <div style="font-size: 13px; color: #606266; margin-bottom: 12px; min-height: 36px">
            {{ f.description }}
          </div>
          <div style="font-size: 12px; color: #909399; margin-bottom: 12px">
            <span v-if="f.type === 'window'">回溯 {{ f.lookback_days }} 个交易日</span>
            <span v-else>实时字段</span>
          </div>
          <el-button type="primary" size="small" @click="openCompute(f)">计算</el-button>
        </el-card>
      </el-col>
    </el-row>

    <!-- Empty state -->
    <el-empty v-if="!loading && filteredFactors.length === 0" description="暂无因子" />

    <!-- Date picker dialog -->
    <el-dialog v-model="showDateDialog" title="选择计算日期" width="400px">
      <el-form>
        <el-form-item label="因子">
          <span style="font-weight: 600">{{ activeFactor?.name }}</span>
        </el-form-item>
        <el-form-item label="日期">
          <el-date-picker v-model="computeDate" type="date" value-format="YYYY-MM-DD" placeholder="选择日期" style="width: 100%" />
        </el-form-item>
        <div style="font-size: 12px; color: #909399">
          最新交易日：{{ latestDate }}
        </div>
      </el-form>
      <template #footer>
        <el-button @click="showDateDialog = false">取消</el-button>
        <el-button type="primary" @click="doCompute">确定</el-button>
      </template>
    </el-dialog>

    <!-- Results -->
    <div v-if="result">
      <h3 style="margin: 20px 0 12px">
        {{ result.factor_name }}
        <span style="font-size: 14px; color: #909399; margin-left: 8px">{{ result.date }}</span>
      </h3>

      <!-- Stats cards -->
      <el-row :gutter="12" style="margin-bottom: 16px">
        <el-col :span="4">
          <el-card shadow="hover">
            <template #header>有效样本</template>
            <div style="font-size: 20px; font-weight: bold; color: #409eff">{{ result.stats.count_valid }}</div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card shadow="hover">
            <template #header>均值</template>
            <div style="font-size: 20px; font-weight: bold; color: #409eff">{{ result.stats.mean }}</div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card shadow="hover">
            <template #header>标准差</template>
            <div style="font-size: 20px; font-weight: bold; color: #409eff">{{ result.stats.std }}</div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card shadow="hover">
            <template #header>中位数</template>
            <div style="font-size: 20px; font-weight: bold; color: #409eff">{{ result.stats.median }}</div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card shadow="hover">
            <template #header>Q25 / Q75</template>
            <div style="font-size: 18px; font-weight: bold; color: #409eff">{{ result.stats.q25 }} / {{ result.stats.q75 }}</div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card shadow="hover">
            <template #header>范围</template>
            <div style="font-size: 18px; font-weight: bold; color: #409eff">[{{ result.stats.min }}, {{ result.stats.max }}]</div>
          </el-card>
        </el-col>
      </el-row>

      <!-- Histogram -->
      <el-card style="margin-bottom: 16px">
        <template #header>因子分布直方图</template>
        <div ref="histogramRef" style="width: 100%; height: 350px" />
      </el-card>

      <!-- Top / Bottom 10 -->
      <el-row :gutter="16">
        <el-col :span="12">
          <el-card>
            <template #header>Top 10</template>
            <el-table :data="result.top_10" size="small" max-height="400">
              <el-table-column type="index" label="#" width="50" />
              <el-table-column prop="ts_code" label="代码" width="110" />
              <el-table-column prop="name" label="名称" min-width="100" show-overflow-tooltip />
              <el-table-column prop="value" label="因子值" sortable />
            </el-table>
          </el-card>
        </el-col>
        <el-col :span="12">
          <el-card>
            <template #header>Bottom 10</template>
            <el-table :data="result.bottom_10" size="small" max-height="400">
              <el-table-column type="index" label="#" width="50" />
              <el-table-column prop="ts_code" label="代码" width="110" />
              <el-table-column prop="name" label="名称" min-width="100" show-overflow-tooltip />
              <el-table-column prop="value" label="因子值" sortable />
            </el-table>
          </el-card>
        </el-col>
      </el-row>
    </div>

    <el-empty v-if="!result && !loading" description="选择一个因子，点击「计算」查看截面分布" />
  </div>
</template>
