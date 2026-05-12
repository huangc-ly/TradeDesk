<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { marketApi } from '@/api'
import KLineChart from '@/components/KLineChart.vue'

interface StockBasic {
  ts_code: string
  symbol: string
  name: string
  area: string
  industry: string
}

interface TreeNode {
  id: string
  label: string
  isLeaf?: boolean
  children?: TreeNode[]
}

const stocks = ref<StockBasic[]>([])
const selectedCode = ref('')
const selectedName = ref('')
const filterText = ref('')
const treeRef = ref()

const treeData = computed(() => {
  const groups: Record<string, StockBasic[]> = {}
  for (const s of stocks.value) {
    const key = s.industry || '未分类'
    if (!groups[key]) groups[key] = []
    groups[key].push(s)
  }

  const sortedGroups = Object.entries(groups).sort((a, b) =>
    a[0].localeCompare(b[0], 'zh'),
  )

  return sortedGroups.map(([industry, groupStocks]) => ({
    id: `ind_${industry}`,
    label: `${industry}  (${groupStocks.length})`,
    children: groupStocks
      .sort((a, b) => a.ts_code.localeCompare(b.ts_code))
      .map((s) => ({
        id: s.ts_code,
        label: `${s.name}  ${s.ts_code}`,
        isLeaf: true,
      })),
  }))
})

function filterNode(value: string, data: TreeNode) {
  if (!value) return true
  return data.label.toLowerCase().includes(value.toLowerCase())
}

function onNodeClick(data: TreeNode) {
  if (data.isLeaf) {
    selectedCode.value = data.id
    selectedName.value = data.label
  }
}

watch(filterText, (val) => {
  treeRef.value?.filter(val)
})

onMounted(async () => {
  try {
    const res = await marketApi.getStocks()
    stocks.value = (res as any).stocks ?? []
  } catch (e) {
    console.error('Failed to load stocks:', e)
  }
})
</script>

<template>
  <div>
    <h2 style="margin-bottom: 20px">行情</h2>

    <div class="market-layout">
      <!-- Left: stock tree -->
      <div class="tree-panel">
        <el-input
          v-model="filterText"
          placeholder="搜索股票名称或代码"
          clearable
          style="margin-bottom: 12px"
        />
        <el-tree
          ref="treeRef"
          :data="treeData"
          :filter-node-method="filterNode"
          node-key="id"
          default-expand-all
          highlight-current
          @node-click="onNodeClick"
        >
          <template #default="{ data }">
            <span class="tree-node" :class="{ leaf: data.isLeaf }">
              {{ data.label }}
            </span>
          </template>
        </el-tree>
      </div>

      <!-- Right: chart -->
      <div class="chart-panel">
        <el-card v-if="selectedCode">
          <template #header>
            <span style="font-weight: 600">{{ selectedName }}</span>
          </template>
          <KLineChart :key="selectedCode" :code="selectedCode" />
        </el-card>
        <el-empty v-else description="点击左侧股票查看行情" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.market-layout {
  display: flex;
  gap: 16px;
  height: calc(100vh - 160px);
}

.tree-panel {
  width: 300px;
  min-width: 300px;
  overflow-y: auto;
  background: #fff;
  border-radius: 4px;
  padding: 12px;
  border: 1px solid #ebeef5;
}

.chart-panel {
  flex: 1;
  overflow-y: auto;
}

.tree-node {
  font-size: 13px;
}

.tree-node.leaf {
  font-size: 13px;
  cursor: pointer;
}
</style>
