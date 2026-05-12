<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { marketApi } from '@/api'

interface Stock {
  ts_code: string
  symbol: string
  name: string
  area: string
  industry: string
  market: string
  exchange: string
  list_status: string
  list_date: string
  is_hs: string
}

const router = useRouter()
const stocks = ref<Stock[]>([])
const loading = ref(false)
const searchText = ref('')
const statusFilter = ref('L')
const currentPage = ref(1)
const pageSize = ref(20)

const statusOptions = [
  { label: '全部', value: '' },
  { label: '上市', value: 'L' },
  { label: '退市', value: 'D' },
  { label: '暂停', value: 'P' },
]

const filteredStocks = computed(() => {
  let result = stocks.value
  if (statusFilter.value) {
    result = result.filter((s) => s.list_status === statusFilter.value)
  }
  if (searchText.value) {
    const kw = searchText.value.toLowerCase()
    result = result.filter(
      (s) =>
        s.ts_code.toLowerCase().includes(kw) ||
        s.name.toLowerCase().includes(kw) ||
        s.symbol.includes(kw) ||
        s.industry?.toLowerCase().includes(kw) ||
        s.area?.toLowerCase().includes(kw),
    )
  }
  return result
})

const pagedStocks = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredStocks.value.slice(start, start + pageSize.value)
})

const statusTagType = (status: string) => {
  switch (status) {
    case 'L': return 'success'
    case 'D': return 'danger'
    case 'P': return 'warning'
    default: return 'info'
  }
}

const statusLabel = (status: string) => {
  switch (status) {
    case 'L': return '上市'
    case 'D': return '退市'
    case 'P': return '暂停'
    default: return status
  }
}

onMounted(async () => {
  loading.value = true
  try {
    const res = (await marketApi.getStocks()) as any
    stocks.value = res.stocks ?? []
  } finally {
    loading.value = false
  }
})

function onSearchChange() {
  currentPage.value = 1
}

function onStatusFilterChange() {
  currentPage.value = 1
}

function onRowDblClick(row: Stock) {
  router.push({ path: '/analysis', query: { stock: row.ts_code } })
}
</script>

<template>
  <div>
    <h2 style="margin-bottom: 20px">股票列表</h2>

    <el-card style="margin-bottom: 20px">
      <el-form :inline="true">
        <el-form-item label="状态">
          <el-select
            v-model="statusFilter"
            style="width: 100px"
            @change="onStatusFilterChange"
          >
            <el-option
              v-for="opt in statusOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="搜索">
          <el-input
            v-model="searchText"
            placeholder="代码 / 名称 / 行业 / 地区"
            style="width: 280px"
            clearable
            @input="onSearchChange"
          />
        </el-form-item>
        <el-form-item>
          <span style="color: #909399; font-size: 13px">
            共 {{ filteredStocks.length }} 只股票，双击行进入量化分析
          </span>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card>
      <el-table
        :data="pagedStocks"
        v-loading="loading"
        stripe
        highlight-current-row
        style="width: 100%"
        @row-dblclick="onRowDblClick"
      >
        <el-table-column prop="ts_code" label="代码" width="120" sortable />
        <el-table-column prop="name" label="名称" width="100" sortable />
        <el-table-column prop="area" label="地区" width="100" sortable />
        <el-table-column prop="industry" label="行业" min-width="140" sortable />
        <el-table-column prop="market" label="市场" width="100" sortable />
        <el-table-column prop="exchange" label="交易所" width="80" sortable />
        <el-table-column prop="list_date" label="上市日期" width="110" sortable />
        <el-table-column prop="list_status" label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.list_status)" size="small">
              {{ statusLabel(row.list_status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="is_hs" label="沪深港通" width="90" />
      </el-table>

      <div style="margin-top: 16px; display: flex; justify-content: center">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="filteredStocks.length"
          layout="total, sizes, prev, pager, next, jumper"
        />
      </div>
    </el-card>
  </div>
</template>
