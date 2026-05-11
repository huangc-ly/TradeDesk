<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import * as echarts from 'echarts'

const props = defineProps<{ result: any }>()

const histRef = ref<HTMLDivElement>()
const qqRef = ref<HTMLDivElement>()
let histChart: echarts.ECharts | null = null
let qqChart: echarts.ECharts | null = null

function disposeCharts() {
  if (histChart) { histChart.dispose(); histChart = null }
  if (qqChart) { qqChart.dispose(); qqChart = null }
}

onUnmounted(() => disposeCharts())

function renderCharts() {
  // --- Histogram + normal fit ---
  const histogram = props.result?.histogram
  const normalFit = props.result?.normal_fit
  if (histogram?.length) {
    const hc = histRef.value
    if (hc) {
      if (histChart) histChart.dispose()
      histChart = echarts.init(hc)
      histChart.setOption({
        tooltip: {
          trigger: 'axis',
          axisPointer: { type: 'shadow' },
        },
        grid: { left: '8%', right: '4%', top: '5%', bottom: '8%' },
        xAxis: {
          type: 'value',
          name: '日收益率',
          axisLabel: { formatter: (v: number) => (v * 100).toFixed(1) + '%' },
        },
        yAxis: { type: 'value', name: '频次' },
        series: [
          {
            type: 'bar',
            data: histogram.map((b: any) => [b.bin_center, b.count]),
            itemStyle: {
              color: (p: any) => (p.value?.[0] ?? p.data?.[0]) >= 0 ? '#67c23a' : '#f56c6c',
            },
          },
          ...(normalFit?.length ? [{
            type: 'line',
            data: normalFit.map((d: any) => [d.x, d.density]),
            smooth: true,
            lineStyle: { color: '#e6a23c', type: 'dashed', width: 2 },
            symbol: 'none',
            silent: true,
          }] : []),
        ],
      })
    }
  }

  // --- QQ Plot ---
  const qqData = props.result?.qq_plot
  if (qqData?.length) {
    const qc = qqRef.value
    if (qc) {
      if (qqChart) qqChart.dispose()
      qqChart = echarts.init(qc)
      qqChart.setOption({
        tooltip: {
          trigger: 'item',
          formatter: (p: any) =>
            `理论: ${p.value[0].toFixed(4)}<br/>样本: ${p.value[1].toFixed(4)}`,
        },
        grid: { left: '10%', right: '4%', top: '5%', bottom: '8%' },
        xAxis: { type: 'value', name: '理论分位数' },
        yAxis: { type: 'value', name: '样本分位数' },
        series: [
          {
            type: 'scatter',
            data: qqData.map((d: any) => [d.theoretical, d.sample]),
            symbolSize: 3,
            itemStyle: { opacity: 0.5, color: '#409eff' },
          },
          {
            type: 'line',
            data: [[-4, -4], [4, 4]],
            lineStyle: { color: '#e6a23c', type: 'dashed' },
            symbol: 'none',
            silent: true,
          },
        ],
      })
    }
  }
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
    <!-- Summary cards — Row 1: distribution stats -->
    <el-row :gutter="16" style="margin-bottom: 16px">
      <el-col :span="4">
        <el-card shadow="hover">
          <template #header>偏度</template>
          <div style="font-size: 22px; font-weight: bold"
            :style="{ color: result.summary.skewness > 0 ? '#67c23a' : result.summary.skewness < 0 ? '#f56c6c' : '#409eff' }">
            {{ result.summary.skewness }}
          </div>
          <div style="font-size: 11px; color: #909399">
            {{ result.summary.skewness > 0.5 ? '右偏' : result.summary.skewness < -0.5 ? '左偏' : '大致对称' }}
          </div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover">
          <template #header>峰度（超额）</template>
          <div style="font-size: 22px; font-weight: bold; color: #e6a23c">
            {{ result.summary.kurtosis }}
          </div>
          <div style="font-size: 11px; color: #909399">
            {{ result.summary.kurtosis > 1 ? '厚尾分布' : '接近正态' }}
          </div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover">
          <template #header>JB 统计量</template>
          <div style="font-size: 22px; font-weight: bold; color: #409eff">
            {{ result.summary.jarque_bera_stat }}
          </div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover">
          <template #header>JB p 值</template>
          <div style="font-size: 22px; font-weight: bold"
            :style="{ color: result.summary.jarque_bera_pvalue < 0.05 ? '#f56c6c' : '#67c23a' }">
            {{ result.summary.jarque_bera_pvalue < 0.0001 ? result.summary.jarque_bera_pvalue.toExponential(2) : result.summary.jarque_bera_pvalue.toFixed(4) }}
          </div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover">
          <template #header>正态性</template>
          <div style="font-size: 22px; font-weight: bold"
            :style="{ color: result.summary.is_normal ? '#67c23a' : '#f56c6c' }">
            {{ result.summary.is_normal ? '接受 H₀' : '拒绝 H₀' }}
          </div>
          <div style="font-size: 11px; color: #909399">
            {{ result.summary.is_normal ? '符合正态分布' : '非正态分布' }}
          </div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover">
          <template #header>日均收益</template>
          <div style="font-size: 22px; font-weight: bold"
            :style="{ color: result.summary.mean_daily_return > 0 ? '#67c23a' : '#f56c6c' }">
            {{ (result.summary.mean_daily_return * 100).toFixed(3) }}%
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- Summary cards — Row 2: up/down stats -->
    <el-row :gutter="16" style="margin-bottom: 16px">
      <el-col :span="5">
        <el-card shadow="hover">
          <template #header>上涨比例</template>
          <div style="font-size: 22px; font-weight: bold; color: '#67c23a'">
            {{ (result.summary.up_days_ratio * 100).toFixed(1) }}%
          </div>
        </el-card>
      </el-col>
      <el-col :span="5">
        <el-card shadow="hover">
          <template #header>平均涨幅</template>
          <div style="font-size: 22px; font-weight: bold; color: #67c23a">
            +{{ (result.summary.avg_gain * 100).toFixed(2) }}%
          </div>
        </el-card>
      </el-col>
      <el-col :span="5">
        <el-card shadow="hover">
          <template #header>平均跌幅</template>
          <div style="font-size: 22px; font-weight: bold; color: #f56c6c">
            {{ (result.summary.avg_loss * 100).toFixed(2) }}%
          </div>
        </el-card>
      </el-col>
      <el-col :span="5">
        <el-card shadow="hover">
          <template #header>盈亏比</template>
          <div style="font-size: 22px; font-weight: bold"
            :style="{ color: result.summary.gain_loss_ratio > 1 ? '#67c23a' : '#f56c6c' }">
            {{ result.summary.gain_loss_ratio }}
          </div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover">
          <template #header>样本数</template>
          <div style="font-size: 22px; font-weight: bold; color: #409eff">{{ result.data_points }}</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- Charts -->
    <el-row :gutter="20" style="margin-bottom: 20px">
      <el-col :span="13">
        <el-card>
          <template #header>收益率分布直方图</template>
          <div ref="histRef" style="width: 100%; height: 420px" />
        </el-card>
      </el-col>
      <el-col :span="11">
        <el-card>
          <template #header>QQ Plot</template>
          <div ref="qqRef" style="width: 100%; height: 420px" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>
