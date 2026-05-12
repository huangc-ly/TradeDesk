<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { Monitor, TrendCharts, Setting, Wallet, DataAnalysis, Histogram, List, Notebook } from '@element-plus/icons-vue'

const router = useRouter()
const appStore = useAppStore()

const menuItems = [
  { path: '/dashboard', title: '仪表盘', icon: Monitor },
  { path: '/market', title: '行情', icon: TrendCharts },
  { path: '/strategy', title: '策略', icon: Setting },
  { path: '/portfolio', title: '组合', icon: Wallet },
  { path: '/stocks', title: '股票列表', icon: List },
  { path: '/finance', title: '财报', icon: Notebook },
  { path: '/analysis', title: '分析', icon: DataAnalysis },
  { path: '/factors', title: '因子库', icon: Histogram },
]
</script>

<template>
  <el-container>
    <el-aside :width="appStore.collapsed ? '64px' : '220px'">
      <div class="logo">
        <span v-show="!appStore.collapsed">TradeDesk</span>
        <span v-show="appStore.collapsed">TD</span>
      </div>
      <el-menu
        :default-active="router.currentRoute.value.path"
        background-color="#1d1e2c"
        text-color="#bfcbd9"
        active-text-color="#409eff"
        :collapse="appStore.collapsed"
        router
      >
        <el-menu-item v-for="item in menuItems" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.title }}</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header>
        <el-button text @click="appStore.toggleCollapse">
          <el-icon :size="20">
            <component :is="appStore.collapsed ? 'Expand' : 'Fold'" />
          </el-icon>
        </el-button>
        <span>个人量化系统</span>
      </el-header>

      <el-main>
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.el-menu {
  border-right: none;
}
</style>
