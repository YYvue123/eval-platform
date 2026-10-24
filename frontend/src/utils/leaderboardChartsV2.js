import { csvCell, number } from './leaderboardCharts.js'
export { csvCell, number }
export const colors = ['#2563eb', '#14a89c', '#ed9a32', '#9069d8', '#dc678e']
const short = name => name.replace('[演示配置] ', '')
const tooltip = { renderMode: 'richText', confine: true, backgroundColor: '#fff', borderColor: '#dce5f1', textStyle: { color: '#334155', fontSize: 12 }, padding: [12, 16], extraCssText: 'box-shadow:0 6px 28px #23395d18;border-radius:10px' }
const base = { color: colors, animationDuration: 350, textStyle: { fontFamily: 'inherit', color: '#7a8aa4', fontSize: 12 } }
const splitLine = { lineStyle: { color: '#edf1f7', type: 'dashed' } }
const scoreText = (v, scale) => v == null ? '未测' : `${number(scale ? v * 100 : v, 1)}${scale ? ' 分' : ''}`
export function radarOption(rows, dimensions, scale) {
  const dims = dimensions.filter(d => rows.every(r => r.dimensions[d]?.score != null))
  if (!scale || !rows.length || dims.length < 3) return null
  return { ...base, tooltip: { ...tooltip, trigger: 'item', formatter: p => [p.name, ...dims.map((d,i) => `${d}    ${scoreText(p.value[i], scale)}`)].join('\n') },
    radar: { shape: 'circle', startAngle: 90, radius: '67%', center: ['50%', '49%'], splitNumber: 5,
      indicator: dims.map(d => ({ name: d, min: scale.min, max: scale.max })), axisName: { color: '#40506a', fontSize: 13, fontWeight: 500 }, axisNameGap: 20,
      splitArea: { show: true, areaStyle: { color: ['#fff', '#fafcff'] } }, splitLine: { lineStyle: { color: '#dfe8f5', width: 1 } }, axisLine: { lineStyle: { color: '#e5ecf7' } } },
    series: rows.map((r,i) => ({ type: 'radar', name: r.model_name, symbol: 'circle', symbolSize: 6,
      lineStyle: { width: 2.5, color: r.chart_color || colors[i] }, itemStyle: { color: r.chart_color || colors[i], borderWidth: 2, borderColor: '#fff' },
      areaStyle: { color: r.chart_color || colors[i], opacity: .035 }, emphasis: { lineStyle: { width: 4 }, areaStyle: { opacity: .12 } },
      data: [{ name: r.model_name, value: dims.map(d=>r.dimensions[d].score) }] })) }
}
export function barOption(rows, key='ranking_score', label='综合得分', scale=null) {
  const multiplier = scale && !['latency_ms','cost','value_score'].includes(key) ? 100 : 1
  const items = rows.filter(r=>r[key]!=null).slice(0,15).slice().reverse()
  return { ...base, tooltip: { ...tooltip, trigger:'axis', axisPointer:{type:'shadow'}, formatter:p=>`${p[0].name}\n${label}    ${number(p[0].value,2)}` }, grid:{left:15,right:62,top:28,bottom:22,containLabel:true},
    xAxis:{type:'value',max:multiplier===100 ? 100 : undefined,splitLine,axisLabel:{color:'#8a98ad'},axisLine:{show:false}},
    yAxis:{type:'category',data:items.map(r=>short(r.model_name)),axisLine:{show:false},axisTick:{show:false},axisLabel:{color:'#526179',width:170,overflow:'truncate',margin:18}},
    series:[{type:'bar',name:label,barMaxWidth:18,showBackground:true,backgroundStyle:{color:'#f3f6fb',borderRadius:5},itemStyle:{borderRadius:5},
      label:{show:true,position:'right',color:'#344765',fontWeight:600,formatter:p=>number(p.value,1)},
      data:items.map((r,i)=>({value:r[key]*multiplier,itemStyle:{color:r.chart_color || (i===items.length-1?'#2563eb':'#9bbcf7')}}))}] }
}
export function heatOption(rows, dimensions, scale) {
  if(!scale) return null
  const data=[]
  rows.forEach((r,y)=>dimensions.forEach((d,x)=>{if(r.dimensions[d]?.score!=null)data.push([x,y,r.dimensions[d].score])}))
  return {...base,tooltip:{...tooltip,position:'top',formatter:p=>`${rows[p.value[1]].model_name}\n${dimensions[p.value[0]]}    ${scoreText(p.value[2],scale)}`},
    grid:{left:20,right:25,top:48,bottom:70,containLabel:true},
    xAxis:{type:'category',position:'top',data:dimensions,axisLine:{show:false},axisTick:{show:false},axisLabel:{interval:0,color:'#526179',margin:14,rotate:dimensions.length>6?20:0}},
    yAxis:{type:'category',data:rows.map(r=>short(r.model_name)),inverse:true,axisLine:{show:false},axisTick:{show:false},axisLabel:{width:160,overflow:'truncate',color:'#526179',margin:16}},
    visualMap:{min:scale.min,max:scale.max,orient:'horizontal',left:'center',bottom:4,itemWidth:13,itemHeight:170,text:['高','低'],calculable:true,inRange:{color:['#f0f6ff','#c3def6','#68b7db','#2773cc','#1745a1']}},
    series:[{type:'heatmap',data,label:{show:true,color:'#163d6d',fontWeight:600,formatter:p=>number(p.value[2]*100,1)},itemStyle:{borderColor:'#fff',borderWidth:6,borderRadius:7},emphasis:{itemStyle:{shadowBlur:12,shadowColor:'#2a5aab25'}}}]}
}
export function trendOption(rows,history,scale) {
  return {...base,tooltip:{...tooltip,trigger:'axis',valueFormatter:v=>number(v,2)},grid:{left:48,right:24,top:28,bottom:68},
    xAxis:{type:'time',axisLine:{lineStyle:{color:'#e2e9f2'}},axisTick:{show:false},axisLabel:{hideOverlap:true}},
    yAxis:{type:'value',name:scale?'得分 / 100':'原始分',min:scale?0:undefined,max:scale?100:undefined,splitLine},
    dataZoom:[{type:'inside'},{type:'slider',height:16,bottom:12,borderColor:'transparent',backgroundColor:'#f3f6fb',fillerColor:'#2563eb18',handleStyle:{color:'#2563eb'}}],
    series:rows.map(r=>({name:r.model_name,type:'line',smooth:.15,symbol:'circle',symbolSize:7,connectNulls:false,lineStyle:{width:2.5,color:r.chart_color},itemStyle:{color:r.chart_color},
      data:history.filter(p=>p.key===r.key).map(p=>[p.at?.endsWith('Z')?p.at:`${p.at}Z`,p.score==null?null:p.score*(scale?100:1)])}))}
}
export function scatterOption(rows,scale) {
  return {...base,tooltip:{...tooltip,trigger:'item',formatter:p=>`${p.seriesName}\n实测均延    ${number(p.value[0],0)} ms\n得分    ${number(p.value[1],1)}`},
    grid:{left:55,right:55,top:30,bottom:45},xAxis:{type:'value',name:'时延 / ms',nameLocation:'middle',nameGap:28,splitLine},
    yAxis:{type:'value',name:scale?'得分 / 100':'原始分',min:scale?0:undefined,max:scale?100:undefined,splitLine},
    series:rows.filter(r=>r.latency_ms!=null).map(r=>({name:r.model_name,type:'scatter',symbolSize:20,itemStyle:{color:r.chart_color,opacity:.85,borderWidth:3,borderColor:'#fff'},label:{show:true,formatter:short(r.model_name),position:'top',color:'#526179',fontSize:12},labelLayout:{hideOverlap:true},data:[[r.latency_ms,r.score*(scale?100:1)]]}))}
}
