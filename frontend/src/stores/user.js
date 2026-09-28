import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { usersApi } from '@/api'

const TOKEN_KEY = 'eval_token'
const USERNAME_KEY = 'eval_username'
const ROLE_KEY = 'eval_role'
const REMEMBER_ME_KEY = 'eval_remember_me'

function getStorage() {
  return localStorage.getItem(REMEMBER_ME_KEY) === '1' ? localStorage : sessionStorage
}

export const useUserStore = defineStore('user', () => {
  const storage = getStorage()
  const token = ref(storage.getItem(TOKEN_KEY) || '')
  const username = ref(storage.getItem(USERNAME_KEY) || '')
  const role = ref(storage.getItem(ROLE_KEY) || 'viewer')
  const permissions = ref([])
  const dataScope = ref('all')
  const roleCode = ref(role.value)
  const avatar = ref('')
  const nickname = ref('')
  const phone = ref('')
  const email = ref('')
  const createdAt = ref('')
  const userId = ref(null)
  /** 头像展示 URL（blob 或空，用于 header/个人中心） */
  const avatarDisplayUrl = ref('')

  function setAuth(accessToken, name, userRole = 'viewer', rememberMe = true) {
    token.value = accessToken
    username.value = name
    role.value = userRole
    roleCode.value = userRole
    const store = rememberMe ? localStorage : sessionStorage
    store.setItem(TOKEN_KEY, accessToken)
    store.setItem(USERNAME_KEY, name)
    store.setItem(ROLE_KEY, userRole)
    if (rememberMe) {
      localStorage.setItem(REMEMBER_ME_KEY, '1')
    } else {
      localStorage.removeItem(REMEMBER_ME_KEY)
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(USERNAME_KEY)
      localStorage.removeItem(ROLE_KEY)
    }
  }

  function setUserInfo(info) {
    if (info.id !== undefined) userId.value = info.id
    if (info.permissions) permissions.value = info.permissions
    if (info.data_scope) dataScope.value = info.data_scope
    if (info.role_code) {
      roleCode.value = info.role_code
      role.value = info.role_code
    }
    if (info.avatar !== undefined) avatar.value = info.avatar || ''
    if (info.nickname !== undefined) nickname.value = info.nickname || ''
    if (info.phone !== undefined) phone.value = info.phone || ''
    if (info.email !== undefined) email.value = info.email || ''
    if (info.created_at !== undefined) createdAt.value = info.created_at || ''
  }

  function setAvatarDisplayUrl(url) {
    if (avatarDisplayUrl.value && avatarDisplayUrl.value.startsWith('blob:')) {
      try { URL.revokeObjectURL(avatarDisplayUrl.value) } catch (_) {}
    }
    avatarDisplayUrl.value = url || ''
  }

  function logout() {
    setAvatarDisplayUrl('')
    token.value = ''
    username.value = ''
    role.value = 'viewer'
    roleCode.value = 'viewer'
    permissions.value = []
    dataScope.value = 'all'
    avatar.value = ''
    nickname.value = ''
    phone.value = ''
    email.value = ''
    createdAt.value = ''
    userId.value = null
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USERNAME_KEY)
    localStorage.removeItem(ROLE_KEY)
    localStorage.removeItem(REMEMBER_ME_KEY)
    sessionStorage.removeItem(TOKEN_KEY)
    sessionStorage.removeItem(USERNAME_KEY)
    sessionStorage.removeItem(ROLE_KEY)
  }

  async function fetchUserInfo() {
    if (!token.value) return
    try {
      const info = await usersApi.getMe()
      setUserInfo(info)
      if (info.avatar) {
        try {
          const blob = await usersApi.getMeAvatar()
          const url = URL.createObjectURL(blob)
          setAvatarDisplayUrl(url)
        } catch (_) {
          setAvatarDisplayUrl('')
        }
      } else {
        setAvatarDisplayUrl('')
      }
    } catch (_) {
      permissions.value = []
      dataScope.value = 'all'
      setAvatarDisplayUrl('')
    }
  }

  const isLoggedIn = () => !!token.value
  const isAdmin = () => roleCode.value === 'admin' || role.value === 'admin'

  /** 检查是否拥有指定权限 */
  function hasPermission(perm) {
    if (isAdmin()) return true
    return Array.isArray(permissions.value) && permissions.value.includes(perm)
  }

  /** 检查是否有任一权限 */
  function hasAnyPermission(...perms) {
    if (isAdmin()) return true
    return perms.some((p) => hasPermission(p))
  }

  /** 是否仅能看到自己的数据 */
  const isDataScopeOwn = computed(() => dataScope.value === 'own')

  /** 显示名称：昵称优先，否则用户名 */
  const displayName = computed(() => (nickname.value && nickname.value.trim()) || username.value)

  return {
    token,
    username,
    role,
    roleCode,
    permissions,
    dataScope,
    avatar,
    nickname,
    phone,
    email,
    createdAt,
    userId,
    avatarDisplayUrl,
    displayName,
    setAuth,
    setUserInfo,
    setAvatarDisplayUrl,
    logout,
    fetchUserInfo,
    isLoggedIn,
    isAdmin,
    hasPermission,
    hasAnyPermission,
    isDataScopeOwn
  }
})
