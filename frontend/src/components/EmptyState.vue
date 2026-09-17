<template>
  <div class="empty-state">
    <div class="empty-illustration" v-html="illustrationSvg" />
    <p class="empty-title">{{ title }}</p>
    <p class="empty-desc">{{ description }}</p>
    <slot name="action">
      <el-button v-if="actionText && showAction" type="primary" @click="$emit('action')">
        {{ actionText }}
      </el-button>
    </slot>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  type: {
    type: String,
    default: 'default'
  },
  title: { type: String, default: '' },
  description: { type: String, default: '' },
  actionText: { type: String, default: '' },
  showAction: { type: Boolean, default: true }
})

const presets = {
  dataset: {
    title: '暂无数据集',
    desc: '上传 JSONL、JSON、CSV、Excel 或 TXT，开始评测',
    action: '新增数据集'
  },
  base_model: {
    title: '暂无基础模型',
    desc: '添加基础模型后即可创建微调任务',
    action: '添加基础模型'
  },
  task: {
    title: '暂无任务',
    desc: '选择被测模型和数据集，创建你的第一个评测任务',
    action: '创建任务'
  },
  model: {
    title: '暂无被测模型',
    desc: '注册在线接口或远程加密访问通道后即可评测',
    action: '注册模型'
  },
  user: {
    title: '暂无用户',
    desc: '新增用户，邀请团队成员使用平台',
    action: '新增用户'
  },
  notification: {
    title: '暂无通知',
    desc: '发送的通知将显示在这里',
    action: '发送通知'
  },
  role: {
    title: '请选择角色',
    desc: '在左侧选择要配置的角色',
    action: ''
  },
  default: {
    title: '暂无数据',
    desc: '当前还没有相关内容',
    action: ''
  }
}

const preset = computed(() => presets[props.type] || presets.default)
const title = computed(() => props.title || preset.value.title)
const description = computed(() => props.description || preset.value.desc)
const actionText = computed(() => props.actionText || preset.value.action)

const illustrations = {
  dataset: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 80" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><rect x="10" y="10" width="100" height="60" rx="6" fill="var(--bg-card)" stroke="var(--border-color)"/><path d="M20 25h80M20 35h60M20 45h70M20 55h50"/></svg>',
  base_model: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 80" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="60" cy="35" r="18" fill="var(--bg-card)" stroke="var(--color-primary)" opacity="0.3"/><path d="M45 50c0-8 7-15 15-15s15 7 15 15M60 20v10M60 60v10M30 35h10M80 35h10"/></svg>',
  task: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 80" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="25" y="15" width="70" height="50" rx="6" fill="var(--bg-card)" stroke="var(--border-color)"/><circle cx="40" cy="40" r="8" stroke="var(--color-primary)"/><path d="M55 38l12 8 18-18" stroke="var(--color-success)" stroke-width="2"/></svg>',
  model: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 80" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M30 55 L60 25 L90 55 Z" fill="var(--bg-card)" stroke="var(--color-primary)" opacity="0.3"/><circle cx="60" cy="40" r="12" fill="var(--bg-card)" stroke="var(--color-primary)"/></svg>',
  user: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 80" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="60" cy="28" r="14" fill="var(--bg-card)" stroke="var(--border-color)"/><path d="M35 65c0-14 11-25 25-25s25 11 25 25" fill="var(--bg-card)" stroke="var(--border-color)"/></svg>',
  notification: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 80" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M60 15l-35 20v15c0 10 8 18 35 25 27-7 35-15 35-25V35z" fill="var(--bg-card)" stroke="var(--color-warning)" opacity="0.3"/><circle cx="75" cy="28" r="6" fill="var(--color-danger)"/></svg>',
  role: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 80" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="20" y="20" width="35" height="40" rx="4" fill="var(--bg-card)" stroke="var(--border-color)"/><rect x="65" y="20" width="35" height="40" rx="4" fill="var(--bg-card)" stroke="var(--border-color)"/><circle cx="37" cy="35" r="6" stroke="var(--color-primary)"/><path d="M75 35h10M75 42h10"/></svg>',
  default: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 80" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="25" y="20" width="70" height="40" rx="6" fill="var(--bg-card)" stroke="var(--border-color)"/><path d="M45 45h30M45 52h20" stroke="var(--text-placeholder)" stroke-width="1"/></svg>'
}

const illustrationSvg = computed(() => illustrations[props.type] || illustrations.default)
</script>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
  text-align: center;
}

.empty-illustration {
  width: 120px;
  height: 80px;
  margin-bottom: 20px;
  color: var(--text-secondary);
  opacity: 0.85;
}

.empty-illustration :deep(svg) {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.empty-title {
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.empty-desc {
  margin: 0 0 20px;
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.5;
  max-width: 280px;
}
</style>
