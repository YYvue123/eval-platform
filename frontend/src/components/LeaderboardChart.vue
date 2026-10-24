<template><div ref="host" class="leaderboard-chart" :style="{ height }" role="img" :aria-label="label" /></template>
<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
const props = defineProps({ option: Object, height: { type: String, default: '360px' }, label: String })
const host = ref(null)
let chart, observer
function render() { if (chart && props.option) chart.setOption(props.option, true) }
function saveImage() {
  if (!chart) return
  const link=document.createElement('a'); link.href=chart.getDataURL({type:'png',pixelRatio:3,backgroundColor:'#fff'}); link.download=`${props.label || '模型榜单'}.png`; link.click()
}
defineExpose({ saveImage, resize: () => chart?.resize() })
onMounted(() => { chart = echarts.init(host.value); observer = new ResizeObserver(() => chart?.resize()); observer.observe(host.value); render() })
watch(() => props.option, async () => { await nextTick(); render() }, { deep: true })
onBeforeUnmount(() => { observer?.disconnect(); chart?.dispose() })
</script>
<style scoped>.leaderboard-chart { width: 100%; min-width: 0; }</style>
