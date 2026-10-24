<template>
  <section class="specialist-records" aria-label="子 Agent 执行明细">
    <div class="records-heading">
      <div><strong>专项协作记录</strong><span>{{ items.length }} 次委派 · 输入、工具与结果均可回看</span></div>
      <el-button v-if="items.length" text @click="expanded = expanded.length ? [] : items.map(item => item.id)">
        {{ expanded.length ? '折叠全部子 Agent' : '展开全部子 Agent' }}
      </el-button>
    </div>
    <p v-if="!items.length" class="empty-records">这一轮尚无子 Agent 委派。规划与任务跟进会按阶段留下实际记录。</p>
    <el-collapse v-model="expanded">
      <el-collapse-item v-for="item in items" :key="item.id" :name="item.id">
        <template #title>
          <span class="record-role">{{ roleNames[item.role] || item.role }}</span>
          <span class="record-id">#{{ item.id }}</span>
          <el-tag size="small" :type="item.status === 'failed' ? 'danger' : item.status === 'running' ? 'warning' : 'info'">{{ statusNames[item.status] || item.status }}</el-tag>
          <span class="record-id">{{ item.result?.rounds_used || 0 }} 轮 · {{ item.result?.tokens_used ?? '—' }} token</span>
        </template>
        <MarkdownMessage v-if="item.result?.summary" :content="item.result.summary" />
        <el-timeline>
          <el-timeline-item v-for="(event, index) in item.evidence || []" :key="event.seq || index" :timestamp="event.at || ''" placement="top"
            :type="String(event.type).includes('failed') ? 'danger' : 'primary'">
            <div class="record-event">{{ eventNames[event.type] || event.type || event.kind || '证据' }}<span v-if="event.round"> · 模型第 {{ event.round }} 轮</span></div>
            <MarkdownMessage v-if="event.content" :content="event.content" />
            <p v-if="event.name">工具：{{ event.name }}</p>
            <p v-if="event.error" class="record-error">{{ event.error }}</p>
            <el-collapse class="record-payload"><el-collapse-item title="查看输入、参数与完整结果" :name="index">
              <pre>{{ JSON.stringify(event, null, 2) }}</pre>
            </el-collapse-item></el-collapse>
          </el-timeline-item>
        </el-timeline>
        <p v-if="item.error_code" class="record-error">{{ item.error_code }}</p>
      </el-collapse-item>
    </el-collapse>
  </section>
</template>

<script setup>
import { ref } from 'vue'
import MarkdownMessage from './MarkdownMessage.vue'
defineProps({ items: { type: Array, default: () => [] }, roleNames: { type: Object, default: () => ({}) } })
const expanded = ref([])
const statusNames = { running: '执行中', success: '已完成', failed: '失败', skipped: '未执行', escalated: '需人工处理' }
const eventNames = { started: '接收专项任务', 'model.request': '模型输入与工具范围', 'model.response': '模型响应', 'tool.started': '调用工具', 'tool.completed': '工具返回', 'tool.failed': '工具错误反馈', completed: '专项结果', failed: '执行失败' }
</script>

<style scoped>
.specialist-records { margin: 18px 0; border-top: 1px solid var(--el-border-color-lighter); padding-top: 16px; }
.records-heading { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.records-heading strong { display: block; color: var(--el-text-color-primary); }
.records-heading span, .record-id, .empty-records { font-size: 12px; color: var(--el-text-color-secondary); }
.record-role { font-weight: 600; margin-right: 10px; }
.record-id { margin: 0 10px; }
.record-summary { white-space: pre-wrap; line-height: 1.7; overflow-wrap: anywhere; }
.record-event { font-weight: 500; }
.record-payload pre { max-height: 420px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; font-size: 12px; padding: 12px; background: var(--el-fill-color-lighter); }
.record-error { color: var(--el-color-danger); }
@media(max-width: 700px) { .records-heading { align-items: flex-start; } .record-id { margin: 0 4px; } }
</style>
