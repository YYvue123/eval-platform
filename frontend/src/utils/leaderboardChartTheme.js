// Preserve callbacks and data while replacing the chart's light-only paint values.
const darkPaint = {
  '#fff': '#1e293b', '#fafcff': '#243349', '#f3f6fb': '#273a50',
  '#dce5f1': '#4a607a', '#edf1f7': '#3b4e67', '#dfe8f5': '#405670',
  '#e5ecf7': '#3b4e67', '#e2e9f2': '#405670', '#334155': '#dce8f4',
  '#7a8aa4': '#a8bdd5', '#40506a': '#d3e1f1', '#8a98ad': '#a8bdd5',
  '#526179': '#c5d7ea', '#344765': '#e2ecf7',
  '#163d6d': '#e2edf8', '#f0f6ff': '#273b52', '#c3def6': '#284763',
  '#68b7db': '#2e6088', '#2773cc': '#397cba', '#1745a1': '#4b8fea',
}
export function leaderboardChartTheme(option, dark) {
  if (!dark || !option) return option
  function paint(value) {
    if (typeof value === 'string') return darkPaint[value] || value
    if (typeof value === 'function') return value
    if (Array.isArray(value)) return value.map(paint)
    if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([key, child]) => [key, paint(child)]))
    return value
  }
  return paint(option)
}
