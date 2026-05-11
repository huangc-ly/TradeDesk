<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { marketApi } from '@/api'
import KLineChart from '@/components/KLineChart.vue'

interface StockBasic {
  ts_code: string
  symbol: string
  name: string
  area: string
  industry: string
  market: string
}

const stocks = ref<StockBasic[]>([])
const selectedCode = ref('')
const searchText = ref('')

// Only render options matching search (empty = show nothing)
const filteredStocks = computed(() => {
  if (!searchText.value) return []
  const kw = searchText.value.toLowerCase()
  return stocks.value
    .filter(
      (s) =>
        s.ts_code.toLowerCase().includes(kw) ||
        s.name.toLowerCase().includes(kw) ||
        s.symbol.includes(kw)
    )
    .slice(0, 50) // limit visible options to 50
})

onMounted(async () => {
  try {
    const res = await marketApi.getStocks()
    stocks.value = (res as any).stocks ?? []
  } catch (e) {
    console.error('Failed to load stocks:', e)
  }
})

function onSelect(code: string) {
  selectedCode.value = code
}
</script>

<template>
  <div>
    <h2 style="margin-bottom: 20px">行情</h2>

    <el-card>
      <el-select
        v-model="selectedCode"
        filterable
        remote
        :remote-method="(q: string) => (searchText = q)"
        placeholder="输入代码或名称搜索（如 000001 或 平安）"
        style="width: 400px; margin-bottom: 20px"
        clearable
        @change="onSelect"
      >
        <el-option
          v-for="s in filteredStocks"
          :key="s.ts_code"
          :label="`${s.ts_code}  ${s.name}`"
          :value="s.ts_code"
        >
          <span style="float: left; font-weight: 500">{{ s.ts_code }}</span>
          <span style="float: right; color: #8492a6; font-size: 13px">{{ s.name }}</span>
        </el-option>
      </el-select>

      <KLineChart
        v-if="selectedCode"
        :key="selectedCode"
        :code="selectedCode"
      />
      <el-empty v-else description="请搜索并选择股票查看行情" />
    </el-card>
  </div>
</template>
