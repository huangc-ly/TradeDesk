<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import * as echarts from 'echarts'

const props = defineProps<{ result: any }>()

const chartRef = ref<HTMLDivElement>()
const ddChartRef = ref<HTMLDivElement>()
let navChart: echarts.ECharts | null = null
let ddChart: echarts.ECharts | null = null

function disposeCharts() {
  if (navChart) { navChart.dispose(); navChart = null }
  if (ddChart) { ddChart.dispose(); ddChart = null }
}

onUnmounted(() => disposeCharts())

function renderCharts() {
  const eq = props.result?.equity_curve
  if (!eq?.length) return

  const dates = eq.map((d: any) => d.trade_date)
  const navData = eq.map((d: any) => d.nav)
  const ddData = eq.map((d: any) => d.drawdown)

  // --- NAV chart ---
  const nc = chartRef.value
  if (!nc) return
  if (navChart) navChart.dispose()
  navChart = echarts.init(nc)

  // Compute peak line
  let peakVal = navData[0]
  const peakData: number[] = []
  for (const v of navData) {
    peakVal = Math.max(peakVal, v)
    peakData.push(peakVal)
  }

  navChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['净值', '峰值'], bottom: 0 },
    grid: { left: '8%', right: '4%', top: '5%', bottom: '12%' },
    xAxis: { type: 'category', data: dates },
    yAxis: {
      type: 'value',
      name: '净值',
    },
    series: [
      {
        name: '净值',
        type: 'line',
        data: navData,
        lineStyle: { width: 2, color: '#409eff' },
        showSymbol: false,
      },
      {
        name: '峰值',
        type: 'line',
        data: peakData,
        lineStyle: { width: 1, color: '#e6a23c', type: 'dashed' },
        showSymbol: false,
      },
    ],
  })

  // --- Drawdown chart ---
  const dc = ddChartRef.value
  if (!dc) return
  if (ddChart) ddChart.dispose()
  ddChart = echarts.init(dc)

  ddChart.setOption({
    tooltip: {
      trigger: 'axis',
      formatter: (p: any) => `${p[0].name}<br/>回撤: ${p[0].value.toFixed(2)}%`,
    },
    grid: { left: '8%', right: '4%', top: '5%', bottom: '8%' },
    xAxis: { type: 'category', data: dates },
    yAxis: {
      type: 'value',
      name: '回撤 %',
      axisLabel: { formatter: (v: number) => v.toFixed(0) + '%' },
    },
    series: [
      {
        type: 'line',
        data: ddData.map((v: number) => +(v * 100).toFixed(2)),
        name: '回撤',
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(245,108,108,0.4)' },
            { offset: 1, color: 'rgba(245,108,108,0.02)' },
          ]),
        },
        showSymbol: false,
        lineStyle: { width: 0 },
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
          <template #header>最大回撤</template>
          <div style="font-size: 22px; font-weight: bold; color: #f56c6c">
            {{ (result.summary.max_drawdown * 100).toFixed(2) }}%
          </div>
        </el-card>
      </el-col>
      <el-col :span="5">
        <el-card shadow="hover">
          <template #header>峰值日期</template>
          <div style="font-size: 18px; font-weight: bold; color: #409eff">{{ result.summary.peak_date }}</div>
        </el-card>
      </el-col>
      <el-col :span="5">
        <el-card shadow="hover">
          <template #header>谷底日期</template>
          <div style="font-size: 18px; font-weight: bold; color: #f56c6c">{{ result.summary.trough_date }}</div>
        </el-card>
      </el-col>
      <el-col :span="5">
        <el-card shadow="hover">
          <template #header>恢复天数</template>
          <div style="font-size: 22px; font-weight: bold; color: #409eff">
            {{ result.summary.recovery_days ?? '未恢复' }}
          </div>
        </el-card>
      </el-col>
      <el-col :span="5">
        <el-card shadow="hover">
          <template #header>当前回撤</template>
          <div style="font-size: 22px; font-weight: bold"
            :style="{ color: result.summary.current_drawdown < 0 ? '#f56c6c' : '#67c23a' }">
            {{ (result.summary.current_drawdown * 100).toFixed(2) }}%
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- NAV + Drawdown charts -->
    <el-row :gutter="16" style="margin-bottom: 16px">
      <el-col :span="24">
        <el-card>
          <template #header>累计净值曲线</template>
          <div ref="chartRef" style="width: 100%; height: 320px" />
        </el-card>
      </el-col>
    </el-row>
    <el-row :gutter="16" style="margin-bottom: 20px">
      <el-col :span="24">
        <el-card>
          <template #header>回撤序列</template>
          <div ref="ddChartRef" style="width: 100%; height: 240px" />
        </el-card>
      </el-col>
    </el-row>

    <!-- Top N drawdowns table -->
    <el-card v-if="result.top_drawdowns?.length">
      <template #header>历史 Top {{ result.top_drawdowns.length }} 回撤</template>
      <el-table :data="result.top_drawdowns" stripe size="small">
        <el-table-column prop="rank" label="排名" width="60" />
        <el-table-column label="回撤幅度" width="120">
          <template #default="{ row }">
            <span style="color: #f56c6c; font-weight: bold">{{ (row.drawdown * 100).toFixed(2) }}%</span>
          </template>
        </el-table-column>
        <el-table-column prop="peak_date" label="峰值日期" width="120" />
        <el-table-column prop="trough_date" label="谷底日期" width="120" />
        <el-table-column prop="recovery_date" label="恢复日期" width="120">
          <template #default="{ row }">
            {{ row.recovery_date ?? '未恢复' }}
          </template>
        </el-table-column>
        <el-table-column prop="duration_days" label="持续天数" width="100" />
        <el-table-column prop="recovery_days" label="恢复天数" width="100">
          <template #default="{ row }">
            {{ row.recovery_days ?? '—' }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>
