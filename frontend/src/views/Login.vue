<template>
  <div class="login-page">
    <div class="login-box">
      <div class="login-header">
        <el-icon :size="48" color="#6366f1"><Cpu /></el-icon>
        <h1>大模型智能评测平台</h1>
        <p>评测数据、被测模型与工具底座的一体化管理</p>
      </div>
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        class="login-form"
        @submit.prevent="handleSubmit"
      >
        <el-form-item prop="username">
          <el-input
            ref="usernameInputRef"
            v-model="form.username"
            placeholder="用户名"
            size="large"
            :prefix-icon="User"
            autocomplete="username"
            @keyup.enter="handleSubmit"
          />
        </el-form-item>
        <el-form-item prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="密码"
            size="large"
            show-password
            :prefix-icon="Lock"
            autocomplete="current-password"
            @keyup.enter="handleSubmit"
          />
        </el-form-item>
        <el-form-item>
          <el-checkbox v-model="form.rememberMe">记住我</el-checkbox>
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            size="large"
            :loading="loading"
            class="login-btn"
            @click="handleSubmit"
          >
            登 录
          </el-button>
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { User, Lock } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { authApi } from '@/api'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const REMEMBER_ME_KEY = 'eval_remember_me'
const USERNAME_KEY = 'eval_username'

const formRef = ref()
const usernameInputRef = ref()
const loading = ref(false)

const form = reactive({
  username: '',
  password: '',
  rememberMe: true
})

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
}

onMounted(() => {
  if (localStorage.getItem(REMEMBER_ME_KEY) === '1') {
    form.username = localStorage.getItem(USERNAME_KEY) || ''
  }
  usernameInputRef.value?.focus()
})

async function handleSubmit() {
  try {
    await formRef.value?.validate()
    loading.value = true
    const res = await authApi.login(form)
    userStore.setAuth(res.access_token, res.username, res.role || 'viewer', form.rememberMe)
    ElMessage.success('登录成功')
    const redirect = route.query.redirect
    router.push(typeof redirect === 'string' && redirect.startsWith('/') ? redirect : '/dashboard')
  } catch (e) {
    if (e?.errors) return
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
  padding: 16px;
}
.login-box {
  width: 100%;
  max-width: 400px;
  padding: 48px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
  animation: login-box-in 0.35s ease-out;
}
@keyframes login-box-in {
  from {
    opacity: 0;
    transform: translateY(-12px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
.login-header {
  text-align: center;
  margin-bottom: 32px;
}
.login-header h1 {
  margin: 16px 0 8px;
  font-size: 24px;
  color: #303133;
}
.login-header p {
  color: #909399;
  font-size: 14px;
}
.login-btn {
  width: 100%;
}
@media (max-width: 480px) {
  .login-box {
    padding: 32px 24px;
  }
}
</style>
