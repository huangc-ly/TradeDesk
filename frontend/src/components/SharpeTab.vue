<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import * as echarts from 'echarts'

const props = defineProps<{ result: any }>()

const chartRef = ref<HTMLDivElement>()
let chart: echarts.ECharts | null = null

function disposeCharts() {
  if (chart) { chart.dispose(); chart = null }
}

onUnmounted(() => disposeCharts())

function renderCharts() {
  const rolling = props.result?.rolling_sharpe
  if (!rolling?.length) return

  const c = chartRef.value
  if (!c) return
  if (chart) chart.dispose()
  chart = echarts.init(c)

  const dates = rolling.map((r: any) => r.trade_date)
  const sharpeData = rolling.map((r: any) => r.sharpe)
  const cagrData = rolling.map((r: any) => +(r.cagr * 100).toFixed(2))
  const meanSharpe = +(sharpeData.reduce((a: number, b: number) => a + b, 0) / sharpeData.length).toFixed(4)

  chart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['滚动夏普', '滚动CAGR %', '均值'], bottom: 0 },
    grid: { left: '8%', right: '4%', top: '5%', bottom: '12%' },
    xAxis: { type: 'category', data: dates },
    yAxis: [
      {
        type: 'value',
        name: '夏普 / CAGR',
      },
    ],
    series: [
      {
        name: '滚动夏普',
        type: 'line',
        data: sharpeData,
        lineStyle: { width: 2, color: '#409eff' },
        showSymbol: false,
      },
      {
        name: '滚动CAGR %',
        type: 'line',
        data: cagrData,
        lineStyle: { width: 1.5, color: '#67c23a' },
        showSymbol: false,
      },
      {
        name: '均值',
        type: 'line',
        data: Array(sharpeData.length).fill(meanSharpe),
        lineStyle: { width: 1, color: '#e6a23c', type: 'dashed' },
        showSymbol: false,
        silent: true,
      },
    ],
  })
}

watch(() => props.result, async () => {
  disposeCharts()
  await nextTick()
  await nextTick()
  renderCharts()
}, { deep: true })

onMounted(async () => {
  await nextTick()
  await nextTick()
  renderCharts()
})
</script>

<template>
  <div v-if="result">
    <!-- Summary cards -->
    <el-row :gutter="16" style="margin-bottom: 16px">
      <el-col :span="4">
        <el-card shadow="hover">
          <template #header>夏普比率</template>
          <div style="font-size: 22px; font-weight: bold"
            :style="{ color: result.summary.sharpe_ratio > 0 ? '#67c23a' : '#f56c6c' }">
            {{ result.summary.sharpe_ratio }}
          </div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover">
          <template #header>索提诺比率</template>
          <div style="font-size: 22px; font-weight: bold; color: #409eff">
            {{ result.summary.sortino_ratio }}
          </div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover">
          <template #header>卡玛比率</template>
          <div style="font-size: 22px; font-weight: bold; color: #409eff">
            {{ result.summary.calmar_ratio }}
          </div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover">
          <template #header>CAGR</template>
          <div style="font-size: 22px; font-weight: bold"
            :style="{ color: result.summary.cagr > 0 ? '#67c23a' : '#f56c6c' }">
            {{ (result.summary.cagr * 100).toFixed(2) }}%
          </div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover">
          <template #header>年化波动率</template>
          <div style="font-size: 22px; font-weight: bold; color: #e6a23c">
            {{ (result.summary.ann_volatility * 100).toFixed(2) }}%
          </div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover">
          <template #header>样本 / 窗口</template>
          <div style="font-size: 22px; font-weight: bold; color: #409eff">
            {{ result.data_points }}
          </div>
          <div style="font-size: 11px; color: #909399">窗口: {{ result.window }} 日</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- Rolling sharpe chart -->
    <el-row :gutter="16" style="margin-bottom: 20px">
      <el-col :span="24">
        <el-card>
          <template #header>滚动夏普比率（{{ result.window }} 日窗口）</template>
          <div ref="chartRef" style="width: 100%; height: 420px" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>
