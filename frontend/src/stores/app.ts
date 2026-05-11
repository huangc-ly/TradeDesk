import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAppStore = defineStore('app', () => {
  const collapsed = ref(false)

  function toggleCollapse() {
    collapsed.value = !collapsed.value
  }

  return { collapsed, toggleCollapse }
})
