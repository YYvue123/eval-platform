<template>
  <div class="profile-page">
    <div class="page-header">
      <p class="page-desc">管理头像、昵称、联系方式与密码</p>
    </div>
    <el-row :gutter="24">
      <el-col :span="24" :md="14">
        <el-card class="card">
          <template #header><span>基本信息</span></template>
          <el-form ref="formRef" :model="form" label-width="90px" label-position="left">
            <el-form-item label="头像">
              <div class="avatar-upload">
                <el-avatar :size="80" :src="userStore.avatarDisplayUrl" class="avatar-preview">
                  {{ (userStore.displayName || 'U').charAt(0).toUpperCase() }}
                </el-avatar>
                <el-upload
                  class="avatar-uploader"
                  :show-file-list="false"
                  :http-request="handleAvatarUpload"
                  accept=".jpg,.jpeg,.png,.gif,.webp"
                >
                  <el-button type="primary" size="small">更换头像</el-button>
                </el-upload>
                <p class="avatar-tip">支持 jpg/png/gif/webp，不超过 5MB</p>
              </div>
            </el-form-item>
            <el-form-item label="用户名">
              <el-input v-model="userStore.username" disabled />
            </el-form-item>
            <el-form-item label="昵称">
              <el-input v-model="form.nickname" placeholder="选填，用于展示" maxlength="50" show-word-limit />
            </el-form-item>
            <el-form-item label="手机号">
              <el-input v-model="form.phone" placeholder="选填" maxlength="20" />
            </el-form-item>
            <el-form-item label="邮箱">
              <el-input v-model="form.email" placeholder="选填" maxlength="255" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="saving" @click="saveProfile">保存资料</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
      <el-col :span="24" :md="10">
        <el-card class="card">
          <template #header><span>修改密码</span></template>
          <el-form ref="pwdRef" :model="pwdForm" :rules="pwdRules" label-width="90px" label-position="left">
            <el-form-item label="原密码" prop="old_password">
              <el-input v-model="pwdForm.old_password" type="password" placeholder="请输入当前密码" show-password autocomplete="off" />
            </el-form-item>
            <el-form-item label="新密码" prop="new_password">
              <el-input v-model="pwdForm.new_password" type="password" placeholder="字母与数字组合，大于6位" show-password autocomplete="off" />
              <div v-if="pwdForm.new_password" class="password-strength">
                <span class="strength-label">强度：</span>
                <el-progress
                  :percentage="passwordStrength.level * 25"
                  :stroke-width="6"
                  :color="strengthColor"
                  :show-text="false"
                />
                <span :class="['strength-text', 'strength-' + passwordStrength.type]">{{ passwordStrength.label }}</span>
              </div>
            </el-form-item>
            <el-form-item label="确认密码" prop="confirm_password">
              <el-input v-model="pwdForm.confirm_password" type="password" placeholder="再次输入新密码" show-password autocomplete="off" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="changingPwd" @click="changePassword">修改密码</el-button>
            </el-form-item>
          </el-form>
        </el-card>
        <el-card class="card info-card">
          <template #header><span>账号信息</span></template>
          <dl class="info-list">
            <dt>角色</dt>
            <dd>{{ roleLabel }}</dd>
            <dt>注册时间</dt>
            <dd>{{ createdAt }}</dd>
          </dl>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { usersApi } from '@/api'
import { getPasswordStrength, validatePassword } from '@/utils/password'

const userStore = useUserStore()
const formRef = ref(null)
const pwdRef = ref(null)
const saving = ref(false)
const changingPwd = ref(false)

const form = reactive({
  nickname: '',
  phone: '',
  email: ''
})

const pwdForm = reactive({
  old_password: '',
  new_password: '',
  confirm_password: ''
})

const passwordStrength = computed(() => getPasswordStrength(pwdForm.new_password))
const strengthColor = computed(() => {
  const t = passwordStrength.value.type
  return t === 'danger' ? '#f56c6c' : t === 'warning' ? '#e6a23c' : '#67c23a'
})

const pwdRules = {
  old_password: [{ required: true, message: '请输入原密码', trigger: 'blur' }],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    {
      validator: (rule, value, cb) => {
        const r = validatePassword(value)
        if (!r.valid) cb(new Error(r.message))
        else cb()
      },
      trigger: 'blur'
    }
  ],
  confirm_password: [
    { required: true, message: '请再次输入新密码', trigger: 'blur' },
    {
      validator: (rule, value, cb) => {
        if (value !== pwdForm.new_password) cb(new Error('两次输入的密码不一致'))
        else cb()
      },
      trigger: 'blur'
    }
  ]
}

const roleLabel = computed(() => {
  const r = userStore.roleCode || userStore.role
  return r === 'admin' ? '管理员' : r === 'researcher' ? '评测人员' : '访客'
})

const createdAt = computed(() => {
  const raw = userStore.createdAt
  if (!raw) return '-'
  try {
    return new Date(raw).toLocaleString('zh-CN')
  } catch (_) {
    return '-'
  }
})

function loadForm() {
  form.nickname = userStore.nickname || ''
  form.phone = userStore.phone || ''
  form.email = userStore.email || ''
}

async function saveProfile() {
  saving.value = true
  try {
    const fd = new FormData()
    fd.append('phone', form.phone)
    fd.append('email', form.email)
    fd.append('nickname', form.nickname)
    const data = await usersApi.updateMe(fd)
    userStore.setUserInfo(data)
    ElMessage.success('资料已保存')
  } catch (_) {
    // 错误已在 request 拦截器提示
  } finally {
    saving.value = false
  }
}

function handleAvatarUpload({ file }) {
  const fd = new FormData()
  fd.append('avatar', file)
  fd.append('phone', form.phone)
  fd.append('email', form.email)
  fd.append('nickname', form.nickname)
  saving.value = true
  usersApi
    .updateMe(fd)
    .then((data) => {
      userStore.setUserInfo(data)
      return userStore.avatar ? usersApi.getMeAvatar() : Promise.reject()
    })
    .then((blob) => {
      const url = URL.createObjectURL(blob)
      userStore.setAvatarDisplayUrl(url)
      ElMessage.success('头像已更新')
    })
    .catch((e) => {
      if (e?.response?.status !== 400 && e?.message) ElMessage.error(e.message)
    })
    .finally(() => {
      saving.value = false
    })
}

function changePassword() {
  pwdRef.value?.validate(async (valid) => {
    if (!valid) return
    changingPwd.value = true
    try {
      const fd = new FormData()
      fd.append('old_password', pwdForm.old_password)
      fd.append('new_password', pwdForm.new_password)
      fd.append('phone', userStore.phone || '')
      fd.append('email', userStore.email || '')
      fd.append('nickname', userStore.nickname || '')
      await usersApi.updateMe(fd)
      pwdForm.old_password = ''
      pwdForm.new_password = ''
      pwdForm.confirm_password = ''
      pwdRef.value?.resetFields()
      ElMessage.success('密码已修改')
    } catch (_) {}
    finally {
      changingPwd.value = false
    }
  })
}

onMounted(() => {
  loadForm()
})
</script>

<style scoped>
.profile-page .page-header { margin-bottom: 16px; }
.profile-page .page-desc { margin: 4px 0 0; font-size: 13px; color: var(--text-secondary); }
.profile-page .card { margin-bottom: 20px; }
.profile-page .avatar-upload { display: flex; flex-wrap: wrap; align-items: center; gap: 16px; }
.profile-page .avatar-preview { flex-shrink: 0; background: var(--el-color-primary); }
.profile-page .avatar-tip { margin: 8px 0 0; font-size: 12px; color: var(--text-secondary); }
.profile-page .info-list { margin: 0; }
.profile-page .info-list dt { font-size: 12px; color: var(--text-secondary); margin-top: 12px; }
.profile-page .info-list dt:first-child { margin-top: 0; }
.profile-page .info-list dd { margin: 4px 0 0; font-size: 14px; }
.profile-page .password-strength { display: flex; align-items: center; gap: 8px; margin-top: 6px; font-size: 12px; }
.profile-page .password-strength .strength-label { color: var(--text-secondary); }
.profile-page .password-strength .el-progress { flex: 1; max-width: 120px; }
.profile-page .password-strength .strength-text { min-width: 28px; }
.profile-page .password-strength .strength-danger { color: var(--el-color-danger); }
.profile-page .password-strength .strength-warning { color: var(--el-color-warning); }
.profile-page .card-head-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.profile-page .key-hint { margin: 0 0 12px; font-size: 12px; color: var(--text-secondary); }
.profile-page .revealed-key { margin-top: 12px; }
</style>
