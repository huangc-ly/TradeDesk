<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { marketApi } from '@/api'

const stockCount = ref(0)
const indexCount = ref(0)

onMounted(async () => {
  try {
    const [stocksRes, indexesRes] = await Promise.all([
      marketApi.getStocks(),
      marketApi.getIndexes(),
    ])
    stockCount.value = (stocksRes as any).count ?? 0
    indexCount.value = (indexesRes as any).count ?? 0
  } catch (e) {
    console.error('Failed to load dashboard data:', e)
  }
})
</script>

<template>
  <div>
    <h2 style="margin-bottom: 20px">仪表盘</h2>

    <el-row :gutter="20">
      <el-col :span="8">
        <el-card shadow="hover">
          <template #header>股票数量</template>
          <div style="font-size: 32px; font-weight: bold; color: #409eff">
            {{ stockCount }}
          </div>
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card shadow="hover">
          <template #header>指数数量</template>
          <div style="font-size: 32px; font-weight: bold; color: #67c23a">
            {{ indexCount }}
          </div>
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card shadow="hover">
          <template #header>策略数量</template>
          <div style="font-size: 32px; font-weight: bold; color: #e6a23c">
            0
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>
