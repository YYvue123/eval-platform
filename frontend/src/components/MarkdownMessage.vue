<template><div class="markdown-content" v-html="renderMarkdown(content)"></div></template>
<script setup>
import { renderMarkdown } from '@/utils/markdown'
defineProps({ content: { type: String, default: '' } })
</script>
<style scoped>
.markdown-content { line-height: 1.8; overflow-wrap: anywhere; min-width: 0; }
.markdown-content :deep(p) { margin: 0 0 12px; }
.markdown-content :deep(p:last-child) { margin-bottom: 0; }
.markdown-content :deep(h1), .markdown-content :deep(h2), .markdown-content :deep(h3), .markdown-content :deep(h4) { line-height: 1.5; margin: 22px 0 10px; font-weight: 650; color: var(--el-text-color-primary); }
.markdown-content :deep(h1) { font-size: 22px; }
.markdown-content :deep(h2) { font-size: 19px; }
.markdown-content :deep(h3), .markdown-content :deep(h4) { font-size: 16px; }
.markdown-content :deep(ul), .markdown-content :deep(ol) { padding-left: 24px; margin: 8px 0 14px; }
.markdown-content :deep(li) { margin: 4px 0; }
.markdown-content :deep(li > p) { margin-bottom: 4px; }
.markdown-content :deep(blockquote) { margin: 12px 0; padding: 4px 16px; border-left: 3px solid #9caeb6; color: var(--el-text-color-secondary); }
.markdown-content :deep(code) { font-family: Consolas, monospace; font-size: .9em; padding: 2px 5px; border-radius: 4px; background: #edf1f3; }
.markdown-content :deep(pre) { margin: 14px 0; padding: 16px; background: #172731; color: #e4edf0; border-radius: 8px; overflow-x: auto; line-height: 1.65; }
.markdown-content :deep(pre code) { padding: 0; color: inherit; background: transparent; white-space: pre; }
.markdown-content :deep(.markdown-table) { max-width: 100%; overflow-x: auto; margin: 14px 0; }
.markdown-content :deep(table) { width: 100%; border-collapse: collapse; font-size: 13px; }
.markdown-content :deep(th), .markdown-content :deep(td) { border: 1px solid #dce4e7; padding: 9px 12px; text-align: left; vertical-align: top; min-width: 90px; }
.markdown-content :deep(th) { background: #f0f5f5; font-weight: 600; }
.markdown-content :deep(tr:nth-child(even) td) { background: #f9fbfb; }
.markdown-content :deep(a) { color: #087f85; text-decoration: underline; text-underline-offset: 3px; }
.markdown-content :deep(hr) { border: 0; border-top: 1px solid #dce4e7; margin: 20px 0; }
.dark .markdown-content :deep(code) { background: #314358; color: #e0eaf4; }
.dark .markdown-content :deep(pre) { background: #101b2b; color: #dfebf4; }
.dark .markdown-content :deep(pre code) { background: transparent; color: inherit; }
.dark .markdown-content :deep(th), .dark .markdown-content :deep(td) { border-color: #42566a; }
.dark .markdown-content :deep(th) { background: #263b4e; }
.dark .markdown-content :deep(tr:nth-child(even) td) { background: #203245; }
.dark .markdown-content :deep(a) { color: #83d8cd; }
</style>
