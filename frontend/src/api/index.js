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
