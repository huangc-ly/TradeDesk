<script setup lang="ts">
import { ref, onMounted, computed, watch, nextTick } from 'vue'
import * as echarts from 'echarts'
import { factorsApi } from '@/api'

interface FactorMeta {
  id: string
  name: string
  category: string
  type: string
  description: string
  lookback_days: number
  expression: string
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
  top_10: { ts_code: string; name: string; value: number }[]
  bottom_10: { ts_code: string; name: string; value: number }[]
  all_values: { ts_code: string; value: number }[]
}

const CATEGORY_LABELS: Record<string, string> = {
  value: '价值', size: '规模', momentum: '动量', volatility: '波动', liquidity: '流动性',
}

const TYPE_LABELS: Record<string, string> = {
  raw: '原始字段', window: '窗口计算', callback: 'Python 回调',
}

const factors = ref<FactorMeta[]>([])
const activeFactorId = ref('')
const activeFactor = computed(() =>
  factors.value.find((f) => f.id === activeFactorId.value) ?? null,
)
const computeDate = ref('')
const latestDate = ref('')
const result = ref<FactorResult | null>(null)
const loading = ref(false)
const error = ref('')
const activeTab = ref('概览')

const histogramRef = ref<HTMLDivElement>()
let histogramChart: echarts.ECharts | null = null

// ── Tree data: grouped by category ──
const treeData = computed(() => {
  const groups: Record<string, FactorMeta[]> = {}
  for (const f of factors.value) {
    if (!groups[f.category]) groups[f.category] = []
    groups[f.category].push(f)
  }
  return Object.entries(groups).map(([cat, catFactors]) => ({
    id: `cat_${cat}`,
    label: `${CATEGORY_LABELS[cat] || cat}  (${catFactors.length})`,
    children: catFactors.map((f) => ({
      id: f.id,
      label: f.name,
      isLeaf: true,
    })),
  }))
})

// ── Lifecycle ──
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

watch(computeDate, (d) => {
  if (d && activeFactor.value) doCompute()
})

// ── Actions ──
function onNodeClick(data: { id: string; isLeaf?: boolean }) {
  if (!data.isLeaf) return
  activeFactorId.value = data.id
  activeTab.value = '概览'
  error.value = ''
  if (computeDate.value) doCompute()
}

async function doCompute() {
  if (!activeFactor.value || !computeDate.value) return
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

// ── Histogram ──
function renderHistogram() {
  if (!histogramRef.value || !result.value) return
  if (histogramChart) histogramChart.dispose()

  const values = result.value.all_values.map((v) => v.value)
  histogramChart = echarts.init(histogramRef.value)

  const { mean, std } = result.value.stats
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

  const normalData = xData.map((x) => {
    const d = (1 / (std * Math.sqrt(2 * Math.PI))) * Math.exp(-0.5 * ((x - mean) / std) ** 2)
    return +(d * values.length * binW).toFixed(4)
  })

  histogramChart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 50, right: 20, top: 10, bottom: 30 },
    xAxis: { type: 'category', data: xData, axisLabel: { show: false } },
    yAxis: { type: 'value' },
    series: [
      {
        type: 'bar', data: bins, name: '频数',
        itemStyle: {
          color: (p: any) => +xData[p.dataIndex] >= 0 ? '#67c23a' : '#f56c6c',
          opacity: 0.7,
        },
      },
      {
        type: 'line', data: normalData, smooth: true, name: '正态拟合',
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

    <div class="factor-layout">
      <!-- ═══ Left: factor tree ═══ -->
      <div class="factor-tree">
        <div class="tree-header">因子目录</div>
        <el-tree
          :data="treeData"
          node-key="id"
          default-expand-all
          highlight-current
          :current-node-key="activeFactorId"
          @node-click="onNodeClick"
        >
          <template #default="{ data }">
            <span :class="['tree-node', { leaf: data.isLeaf }]">
              {{ data.label }}
            </span>
          </template>
        </el-tree>
      </div>

      <!-- ═══ Right: detail panel ═══ -->
      <div class="factor-detail">
        <!-- Toolbar -->
        <div class="detail-toolbar">
          <div class="toolbar-left">
            <span v-if="activeFactor" class="factor-title">{{ activeFactor.name }}</span>
            <span v-else class="factor-placeholder">请从左侧选择因子</span>
          </div>
          <div class="toolbar-right">
            <el-date-picker
              v-model="computeDate"
              type="date"
              value-format="YYYY-MM-DD"
              :disabled-date="(d: Date) => d.getTime() > Date.now()"
              style="width: 180px"
            />
            <span style="font-size: 12px; color: #909399; margin-left: 8px">
              最新 {{ latestDate }}
            </span>
          </div>
        </div>

        <!-- Error -->
        <el-alert
          v-if="error"
          :title="error"
          type="error"
          show-icon
          closable
          style="margin-bottom: 16px"
          @close="error = ''"
        />

        <!-- Content -->
        <div v-if="!activeFactor" class="empty-state">
          <el-empty description="选择因子并指定日期，查看截面分布" />
        </div>

        <div v-else v-loading="loading" class="detail-content">
          <!-- Tabs: 概览 / 排名 / 详情 -->
          <el-tabs v-model="activeTab">
            <!-- ── 概览 ── -->
            <el-tab-pane name="概览" label="概览">
              <div v-if="result">
                <!-- Stats cards -->
                <el-row :gutter="12" style="margin-bottom: 16px">
                  <el-col :span="4">
                    <el-card shadow="hover" class="stat-card">
                      <div class="stat-label">有效样本</div>
                      <div class="stat-value primary">{{ result.stats.count_valid.toLocaleString() }}</div>
                    </el-card>
                  </el-col>
                  <el-col :span="4">
                    <el-card shadow="hover" class="stat-card">
                      <div class="stat-label">均值</div>
                      <div class="stat-value primary">{{ result.stats.mean.toFixed(4) }}</div>
                    </el-card>
                  </el-col>
                  <el-col :span="4">
                    <el-card shadow="hover" class="stat-card">
                      <div class="stat-label">标准差</div>
                      <div class="stat-value primary">{{ result.stats.std.toFixed(4) }}</div>
                    </el-card>
                  </el-col>
                  <el-col :span="4">
                    <el-card shadow="hover" class="stat-card">
                      <div class="stat-label">中位数</div>
                      <div class="stat-value primary">{{ result.stats.median.toFixed(4) }}</div>
                    </el-card>
                  </el-col>
                  <el-col :span="4">
                    <el-card shadow="hover" class="stat-card">
                      <div class="stat-label">Q25 / Q75</div>
                      <div class="stat-value small">{{ result.stats.q25.toFixed(4) }} / {{ result.stats.q75.toFixed(4) }}</div>
                    </el-card>
                  </el-col>
                  <el-col :span="4">
                    <el-card shadow="hover" class="stat-card">
                      <div class="stat-label">范围</div>
                      <div class="stat-value small">[{{ result.stats.min.toFixed(4) }}, {{ result.stats.max.toFixed(4) }}]</div>
                    </el-card>
                  </el-col>
                </el-row>

                <!-- Histogram -->
                <el-card>
                  <template #header>因子分布直方图</template>
                  <div ref="histogramRef" style="width: 100%; height: 360px" />
                </el-card>
              </div>
              <el-empty v-else description="点击左侧因子或修改日期开始计算" />
            </el-tab-pane>

            <!-- ── 排名 ── -->
            <el-tab-pane name="排名" label="排名">
              <div v-if="result">
                <el-row :gutter="16">
                  <el-col :span="12">
                    <el-card>
                      <template #header>
                        <span style="font-weight: 600; color: #f56c6c">Top 20</span>
                      </template>
                      <el-table :data="result.top_10" size="small" max-height="500" stripe>
                        <el-table-column type="index" label="#" width="50" />
                        <el-table-column prop="ts_code" label="代码" width="110" />
                        <el-table-column prop="name" label="名称" min-width="100" show-overflow-tooltip />
                        <el-table-column prop="value" label="因子值" sortable>
                          <template #default="{ row }">
                            <span style="font-weight: 600">{{ row.value.toFixed(4) }}</span>
                          </template>
                        </el-table-column>
                      </el-table>
                    </el-card>
                  </el-col>
                  <el-col :span="12">
                    <el-card>
                      <template #header>
                        <span style="font-weight: 600; color: #67c23a">Bottom 20</span>
                      </template>
                      <el-table :data="result.bottom_10" size="small" max-height="500" stripe>
                        <el-table-column type="index" label="#" width="50" />
                        <el-table-column prop="ts_code" label="代码" width="110" />
                        <el-table-column prop="name" label="名称" min-width="100" show-overflow-tooltip />
                        <el-table-column prop="value" label="因子值" sortable>
                          <template #default="{ row }">
                            <span style="font-weight: 600">{{ row.value.toFixed(4) }}</span>
                          </template>
                        </el-table-column>
                      </el-table>
                    </el-card>
                  </el-col>
                </el-row>
              </div>
              <el-empty v-else description="请先计算因子值" />
            </el-tab-pane>

            <!-- ── 详情 ── -->
            <el-tab-pane name="详情" label="详情">
              <el-card>
                <el-descriptions :column="2" border>
                  <el-descriptions-item label="因子名称" :span="2">
                    {{ activeFactor.name }}
                  </el-descriptions-item>
                  <el-descriptions-item label="因子 ID">{{ activeFactor.id }}</el-descriptions-item>
                  <el-descriptions-item label="分类">
                    <el-tag size="small">{{ CATEGORY_LABELS[activeFactor.category] || activeFactor.category }}</el-tag>
                  </el-descriptions-item>
                  <el-descriptions-item label="类型">
                    <el-tag size="small" :type="activeFactor.type === 'raw' ? 'success' : 'warning'">
                      {{ TYPE_LABELS[activeFactor.type] || activeFactor.type }}
                    </el-tag>
                  </el-descriptions-item>
                  <el-descriptions-item label="回溯天数">
                    {{ activeFactor.lookback_days > 0 ? activeFactor.lookback_days + ' 天' : '无需回溯' }}
                  </el-descriptions-item>
                  <el-descriptions-item label="描述" :span="2">
                    {{ activeFactor.description }}
                  </el-descriptions-item>
                  <el-descriptions-item label="计算表达式" :span="2">
                    <code style="background: #f5f7fa; padding: 4px 8px; border-radius: 4px; font-size: 12px; word-break: break-all">
                      {{ activeFactor.expression }}
                    </code>
                  </el-descriptions-item>
                </el-descriptions>
              </el-card>
            </el-tab-pane>
          </el-tabs>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.factor-layout {
  display: flex;
  gap: 16px;
  height: calc(100vh - 160px);
}

/* ── Left tree ── */
.factor-tree {
  width: 260px;
  min-width: 260px;
  background: #fff;
  border-radius: 4px;
  border: 1px solid #ebeef5;
  overflow-y: auto;
  padding: 0;
}

.tree-header {
  padding: 12px 16px;
  font-weight: 600;
  font-size: 14px;
  color: #303133;
  border-bottom: 1px solid #ebeef5;
  position: sticky;
  top: 0;
  background: #fff;
  z-index: 1;
}

.tree-node {
  font-size: 13px;
  color: #606266;
}

.tree-node.leaf {
  cursor: pointer;
}

.tree-node.leaf:hover {
  color: #409eff;
}

/* ── Right detail ── */
.factor-detail {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.detail-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: #fff;
  border-radius: 4px;
  border: 1px solid #ebeef5;
  margin-bottom: 16px;
  flex-shrink: 0;
}

.factor-title {
  font-weight: 600;
  font-size: 16px;
  color: #303133;
}

.factor-placeholder {
  font-size: 14px;
  color: #909399;
}

.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #fff;
  border-radius: 4px;
  border: 1px solid #ebeef5;
}

.detail-content {
  flex: 1;
}

/* ── Stat cards ── */
.stat-card {
  text-align: center;
}

.stat-card :deep(.el-card__body) {
  padding: 12px 8px;
}

.stat-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}

.stat-value {
  font-weight: 700;
  font-size: 18px;
}

.stat-value.primary {
  color: #409eff;
}

.stat-value.small {
  font-size: 14px;
}
</style>
