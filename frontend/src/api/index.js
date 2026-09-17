/**
 * API 统一封装
 */
import request from '@/utils/request'

export const authApi = {
  login: (data) => request.post('/auth/login', data),
  register: (data) => request.post('/auth/register', data)
}

export const dashboardApi = {
  getStats: () => request.get('/dashboard/stats'),
  getWorkbench: () => request.get('/dashboard/workbench')
}

export const usersApi = {
  list: (params) => request.get('/users', { params }),
  listOptions: () => request.get('/users/options'),
  getMe: () => request.get('/users/me'),
  getMeAvatar: () => request.get('/users/me/avatar', { responseType: 'blob' }),
  get: (id) => request.get(`/users/${id}`),
  create: (data) => request.post('/users', data),
  update: (id, data) => request.put(`/users/${id}`, data),
  updateMe: (formData) => request.put('/users/me', formData, { headers: { 'Content-Type': 'multipart/form-data' } }),
  delete: (id) => request.delete(`/users/${id}`)
}

export const rolesApi = {
  list: () => request.get('/roles'),
  listPermissions: () => request.get('/roles/permissions'),
  get: (id) => request.get(`/roles/${id}`),
  update: (id, data) => request.put(`/roles/${id}`, data)
}

export const auditApi = {
  list: (params) => request.get('/audit', { params })
}

export const notificationsApi = {
  listMine: (params) => request.get('/notifications/mine', { params }),
  getUnreadCount: () => request.get('/notifications/mine/unread-count'),
  markRead: (id) => request.post(`/notifications/mine/${id}/read`),
  markAllRead: () => request.post('/notifications/mine/read-all'),
  list: (params) => request.get('/notifications', { params }),
  create: (data) => request.post('/notifications', data),
  delete: (id) => request.delete(`/notifications/${id}`)
}

export const datasetsApi = {
  list: (params) => request.get('/datasets', { params }),
  get: (id) => request.get(`/datasets/${id}`),
  create: (data) => request.post('/datasets', data),
  update: (id, data) => request.put(`/datasets/${id}`, data),
  delete: (id) => request.delete(`/datasets/${id}`),
  importFile: (id, formData) => request.post(`/datasets/${id}/import`, formData, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120000 }),
  items: (id, params) => request.get(`/datasets/${id}/items`, { params }),
  exportFile: (id, params) => request.get(`/datasets/${id}/export`, { params, responseType: 'blob' }),
  publish: (id) => request.post(`/datasets/${id}/publish`),
  tags: () => request.get('/datasets/tags'),
  createTag: (data) => request.post('/datasets/tags', data)
}

export const modelsApi = {
  list: (params) => request.get('/models', { params }),
  get: (id) => request.get(`/models/${id}`),
  create: (data) => request.post('/models', data),
  update: (id, data) => request.put(`/models/${id}`, data),
  delete: (id) => request.delete(`/models/${id}`),
  health: (id) => request.post(`/models/${id}/health`),
  invoke: (id, data) => request.post(`/models/${id}/invoke`, data)
}

export const promptsApi = {
  list: (params) => request.get('/prompts', { params }),
  get: (id) => request.get(`/prompts/${id}`),
  create: (data) => request.post('/prompts', data),
  update: (id, data) => request.put(`/prompts/${id}`, data),
  delete: (id) => request.delete(`/prompts/${id}`),
  publish: (id) => request.post(`/prompts/${id}/publish`),
  preview: (id, data) => request.post(`/prompts/${id}/preview`, data)
}

export const resourcesApi = {
  list: (params) => request.get('/resources', { params }),
  get: (id) => request.get(`/resources/${encodeURIComponent(id)}`),
  register: (manifest) => request.post('/resources/register', { manifest }),
  invoke: (data) => request.post('/resources/invoke', data),
  offline: (id) => request.post(`/resources/${encodeURIComponent(id)}/offline`)
}

export const qualityApi = {
  list: (params) => request.get('/quality', { params }),
  run: (params) => request.post('/quality/run', null, { params })
}

export const tasksApi = {
  list: (params) => request.get('/tasks', { params }),
  get: (id) => request.get(`/tasks/${id}`),
  create: (data) => request.post('/tasks', data),
  results: (id, params) => request.get(`/tasks/${id}/results`, { params }),
  run: (id) => request.post(`/tasks/${id}/run`),
  cancel: (id) => request.post(`/tasks/${id}/cancel`)
}

export const leaderboardApi = {
  list: (params) => request.get('/leaderboard', { params })
}

export const servicesApi = {
  list: (params) => request.get('/services', { params }),
  create: (data) => request.post('/services', data),
  updateStatus: (id, params) => request.post(`/services/${id}/status`, null, { params })
}
