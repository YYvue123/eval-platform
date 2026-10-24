<template><div ref="host" class="leaderboard-chart" :style="{ height }" role="img" :aria-label="label" /></template>
<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { useThemeStore } from '@/stores/theme'
import { leaderboardChartTheme } from '@/utils/leaderboardChartTheme'
const theme = useThemeStore()
const props = defineProps({ option: Object, height: { type: String, default: '360px' }, label: String })
const host = ref(null)
let chart, observer, chartTheme
function render() {
  if (!host.value) return
  const currentTheme = theme.isDark ? 'dark' : null
  if (!chart || chartTheme !== currentTheme) {
    chart?.dispose()
    chart = echarts.init(host.value, currentTheme)
    chartTheme = currentTheme
  }
  if (props.option) chart.setOption({ ...leaderboardChartTheme(props.option, theme.isDark), backgroundColor: 'transparent' }, true)
}
function saveImage() {
  if (!chart) return
  const link=document.createElement('a'); link.href=chart.getDataURL({type:'png',pixelRatio:3,backgroundColor:theme.isDark?'#1e293b':'#fff'}); link.download=`${props.label || '模型榜单'}.png`; link.click()
}
defineExpose({ saveImage, resize: () => chart?.resize() })
onMounted(() => { observer = new ResizeObserver(() => chart?.resize()); observer.observe(host.value); render() })
watch(() => props.option, async () => { await nextTick(); render() }, { deep: true })
watch(() => theme.isDark, render)
onBeforeUnmount(() => { observer?.disconnect(); chart?.dispose() })
</script>
<style scoped>.leaderboard-chart { width: 100%; min-width: 0; }</style>
