import test from 'node:test'
import assert from 'node:assert/strict'
import { radarOption,heatOption,trendOption,scatterOption } from '../../src/utils/leaderboardChartsV2.js'
const rows=[{key:'a',model_name:'A',score:.4,latency_ms:120,chart_color:'#14a89c',dimensions:{a:{score:0},b:{score:1},c:{score:.5},d:{score:null}}},{key:'b',model_name:'B',score:.8,latency_ms:150,dimensions:{a:{score:.2},b:{score:.7},c:{score:.4},d:{score:.2}}}]
const scale={min:0,max:1}
test('circular radar keeps measured zero, removes missing axes and preserves model color',()=>{
  const option=radarOption(rows,['a','b','c','d'],scale)
  assert.equal(option.radar.shape,'circle')
  assert.equal(option.radar.indicator.length,3)
  assert.deepEqual(option.series[0].data[0].value,[0,1,.5])
  assert.equal(option.series[0].lineStyle.color,'#14a89c')
  assert.match(option.tooltip.formatter({name:'A',value:[0,1,.5]}),/100.0 分/)
  assert.equal(radarOption(rows,['a','b'],scale),null)
  assert.equal(radarOption(rows,['a','b','c'],null),null)
})
test('heatmap tooltip names model, dimension, and score; no fabricated missing zero',()=>{
  const option=heatOption(rows,['a','b','c','d'],scale)
  assert.equal(option.series[0].data.length,7)
  assert.equal(option.tooltip.formatter({value:[0,0,0]}),'A\na    0.0 分')
})
test('history and efficiency use percentage display while raw data remains unchanged',()=>{
  const option=trendOption(rows,[{key:'a',at:'2026-10-24T00:00:00',score:.4}],scale)
  assert.equal(option.series[0].data[0][1],40)
  assert.equal(scatterOption(rows,scale).series[0].data[0][1],40)
  assert.equal(rows[0].score,.4)
})
