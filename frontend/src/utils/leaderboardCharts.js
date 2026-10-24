export const palette = ['#2762ed', '#17a9aa', '#f0a03a', '#8a70d6', '#dc718f']
export const number = (v, digits = 2) => v == null || !Number.isFinite(Number(v)) ? '—' : Number(v).toFixed(digits)
export function csvCell(value) { return `"${String(value ?? '').replace(/^[=+@\-\t\r]/, "'$&").replaceAll('"', '""')}"` }
const base = { color: palette, animationDuration: 450, textStyle: { fontFamily: 'inherit', color: '#71809a' }, tooltip: { trigger: 'axis', renderMode: 'richText', confine: true }, toolbox: { right: 0, feature: { saveAsImage: { title: '保存图片', pixelRatio: 2 } } } }
export function barOption(rows, metric, label) {
  const data = rows.filter(r => r[metric] != null).slice(0, 30).reverse()
  return { ...base, grid: { left: 18, right: 64, top: 28, bottom: 18, containLabel: true }, xAxis: { type: 'value', name: label, splitLine: { lineStyle: { color: '#edf1f8' } } },
    yAxis: { type: 'category', data: data.map(r => r.model_name), axisLabel: { width: 170, overflow: 'truncate' }, axisLine: { show: false }, axisTick: { show: false } },
    series: [{ type: 'bar', name: label, barMaxWidth: 24, label: { show: true, position: 'right', formatter: p => number(p.value) }, itemStyle: { borderRadius: [0, 5, 5, 0] }, data: data.map((r, i) => ({ value: r[metric], itemStyle: { color: i === data.length - 1 ? palette[0] : '#a5bff8' } })) }] }
}
export function radarOption(rows, dimensions, scale) {
  const complete = dimensions.filter(d => rows.every(r => r.dimensions[d]?.score != null))
  if (!scale || rows.length < 2 || complete.length < 3) return null
  return { ...base, tooltip: { trigger: 'item', renderMode: 'richText' }, legend: { bottom: 0, type: 'scroll' }, radar: { radius: '62%', center: ['50%', '44%'], indicator: complete.map(d => ({ name: d, min: scale.min, max: scale.max })), axisName: { color: '#536481' }, splitNumber: 4, splitArea: { areaStyle: { color: ['#fbfcff', '#f0f5ff'] } }, splitLine: { lineStyle: { color: '#dfe8fa' } } }, series: [{ type: 'radar', symbolSize: 5, lineStyle: { width: 2 }, areaStyle: { opacity: .07 }, data: rows.map(r => ({ name: r.model_name, value: complete.map(d => r.dimensions[d].score) })) }] }
}
export function heatOption(rows, dimensions, scale) {
  if (!scale) return null
  const data = []
  rows.forEach((r, y) => dimensions.forEach((d, x) => { const v = r.dimensions[d]?.score; if (v != null) data.push([x, y, v]) }))
  return { ...base, tooltip: { position: 'top', renderMode: 'richText' }, grid: { left: 20, right: 70, top: 36, bottom: 65, containLabel: true }, xAxis: { type: 'category', data: dimensions, position: 'top', splitArea: { show: true }, axisLabel: { interval: 0, rotate: dimensions.length > 6 ? 25 : 0 } }, yAxis: { type: 'category', data: rows.map(r => r.model_name), inverse: true, axisLabel: { width: 180, overflow: 'truncate' }, splitArea: { show: true } }, visualMap: { min: scale.min, max: scale.max, calculable: true, orient: 'horizontal', left: 'center', bottom: 0, inRange: { color: ['#eef4ff', '#a8dfe6', '#47b7c8', '#2762ed'] } }, series: [{ type: 'heatmap', data, label: { show: true, formatter: p => number(p.value[2]) }, itemStyle: { borderColor: '#fff', borderWidth: 4, borderRadius: 5 }, emphasis: { itemStyle: { borderColor: '#83a9ff', borderWidth: 2 } } }] }
}
export function trendOption(rows, history) {
  return { ...base, legend: { bottom: 0, type: 'scroll' }, grid: { left: 55, right: 30, top: 25, bottom: 90 }, xAxis: { type: 'time', axisLabel: { hideOverlap: true } }, yAxis: { type: 'value', name: '原始分', splitLine: { lineStyle: { color: '#edf1f8' } } }, dataZoom: [{ type: 'inside' }, { type: 'slider', bottom: 35, height: 16 }], series: rows.map(r => ({ name: r.model_name, type: 'line', symbolSize: 8, connectNulls: false, data: history.filter(p => p.key === r.key).map(p => [p.at?.endsWith('Z') ? p.at : `${p.at}Z`, p.score]) })) }
}
export function scatterOption(rows) {
  return { ...base, tooltip: { trigger: 'item', renderMode: 'richText' }, grid: { left: 60, right: 40, top: 25, bottom: 45 }, xAxis: { name: '平均时延 / ms', type: 'value', splitLine: { lineStyle: { color: '#edf1f8' } } }, yAxis: { name: '原始分', type: 'value', splitLine: { lineStyle: { color: '#edf1f8' } } }, series: rows.filter(r => r.latency_ms != null && r.score != null).map((r, i) => ({ name: r.model_name, type: 'scatter', symbolSize: 18, itemStyle: { color: palette[i % palette.length], opacity: .85 }, data: [[r.latency_ms, r.score]], label: { show: true, formatter: r.model_name, position: 'top', color: '#536481' } })) }
}
