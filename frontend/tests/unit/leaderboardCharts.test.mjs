import test from 'node:test'
import assert from 'node:assert/strict'
import { csvCell, heatOption, radarOption } from '../../src/utils/leaderboardCharts.js'
test('missing dimensions never become zero in radar or heatmap', () => {
  const rows=[{model_name:'A',dimensions:{a:{score:0},b:{score:1},c:{score:.5},d:{score:null}}},{model_name:'B',dimensions:{a:{score:1},b:{score:1},c:{score:.4},d:{score:.2}}}]
  const scale={min:0,max:1}
  const radar=radarOption(rows,['a','b','c','d'],scale)
  assert.equal(radar.radar.indicator.length,3)
  assert.deepEqual(radar.series[0].data[0].value,[0,1,.5])
  assert.equal(heatOption(rows,['a','b','c','d'],scale).series[0].data.length,7)
  assert.equal(radarOption(rows,['a','b','c'],null),null)
})
test('CSV quotes fields and neutralizes spreadsheet formulas', () => {
  assert.equal(csvCell('a,"b"'), '"a,""b"""')
  assert.equal(csvCell('=1+1'), '"\'=1+1"')
  assert.equal(csvCell(null),'""')
})
