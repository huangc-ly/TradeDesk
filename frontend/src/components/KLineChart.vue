<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import * as echarts from 'echarts'
import { marketApi } from '@/api'

const props = defineProps<{ code: string }>()

const chartRef = ref<HTMLDivElement>()
const loading = ref(false)
let chart: echarts.ECharts | null = null

async function loadData() {
  if (!props.code) return
  loading.value = true
  try {
    const data = await marketApi.getStockDaily(props.code, { limit: 100 }) as unknown as any[]
    if (!data || data.length === 0) return

    const dates = data.map((d: any) => d.trade_date ?? d.date ?? '').reverse()
    const ohlc = data.map((d: any) => [d.open, d.close, d.low, d.high]).reverse()
    const volumes = data.map((d: any) => d.vol ?? d.volume ?? 0).reverse()

    renderChart(dates, ohlc, volumes)
  } catch (e) {
    console.error('Failed to load chart data:', e)
  } finally {
    loading.value = false
  }
}

function renderChart(dates: string[], ohlc: number[][], volumes: number[]) {
  if (!chartRef.value) return
  if (!chart) {
    chart = echarts.init(chartRef.value)
  }

  chart.setOption(
    {
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' },
      },
      grid: [
        { left: '10%', right: '8%', top: '5%', height: '60%' },
        { left: '10%', right: '8%', top: '72%', height: '20%' },
      ],
      dataZoom: [
        { type: 'inside', xAxisIndex: [0, 1], start: 0, end: 100 },
      ],
      xAxis: [
        { type: 'category', data: dates, gridIndex: 0 },
        { type: 'category', data: dates, gridIndex: 1 },
      ],
      yAxis: [
        { type: 'value', gridIndex: 0, scale: true },
        { type: 'value', gridIndex: 1 },
      ],
      series: [
        {
          name: props.code,
          type: 'candlestick',
          data: ohlc,
          xAxisIndex: 0,
          yAxisIndex: 0,
          itemStyle: {
            color: '#ef5350',
            color0: '#26a69a',
            borderColor: '#ef5350',
            borderColor0: '#26a69a',
          },
        },
        {
          name: '成交量',
          type: 'bar',
          data: volumes,
          xAxisIndex: 1,
          yAxisIndex: 1,
        },
      ],
    },
    { notMerge: true }
  )
}

function handleResize() {
  chart?.resize()
}

watch(() => props.code, loadData, { immediate: true })

onMounted(() => {
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  chart?.dispose()
})
</script>

<template>
  <div v-loading="loading" style="min-height: 200px">
    <div ref="chartRef" style="width: 100%; height: 500px" />
  </div>
</template>
