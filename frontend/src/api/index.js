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
  getUnreadCount: () => request.get('/notifications/mine/unread-count', { skipErrorToast: true }),
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
  preview: (id, formData) => request.post(`/datasets/${id}/preview`, formData, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120000 }),
  importFile: (id, formData) => request.post(`/datasets/${id}/import`, formData, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120000 }),
  items: (id, params) => request.get(`/datasets/${id}/items`, { params }),
  patchItem: (id, itemId, data) => request.patch(`/datasets/${id}/items/${itemId}`, data),
  exportFile: (id, params) => request.get(`/datasets/${id}/export`, { params, responseType: 'blob' }),
  submit: (id) => request.post(`/datasets/${id}/submit`),
  audit: (id, data) => request.post(`/datasets/${id}/audit`, data),
  publish: (id) => request.post(`/datasets/${id}/publish`),
  rollback: (id, versionId) => request.post(`/datasets/${id}/versions/${versionId}/rollback`),
  tags: () => request.get('/datasets/tags'),
  createTag: (data) => request.post('/datasets/tags', data),
  updateTag: (id, data) => request.put(`/datasets/tags/${id}`, data),
  deleteTag: (id) => request.delete(`/datasets/tags/${id}`)
}

export const modelsApi = {
  list: (params) => request.get('/models', { params }),
  get: (id) => request.get(`/models/${id}`),
  create: (data) => request.post('/models', data),
  update: (id, data) => request.put(`/models/${id}`, data),
  delete: (id) => request.delete(`/models/${id}`),
  health: (id) => request.post(`/models/${id}/health`),
  invoke: (id, data) => request.post(`/models/${id}/invoke`, data),
  createVersion: (id, data) => request.post(`/models/${id}/versions`, data),
  activateVersion: (id, vid) => request.post(`/models/${id}/versions/${vid}/activate`),
  addAcl: (id, data) => request.post(`/models/${id}/acl`, data),
  deleteAcl: (id, aclId) => request.delete(`/models/${id}/acl/${aclId}`)
}

export const promptsApi = {
  list: (params) => request.get('/prompts', { params }),
  get: (id) => request.get(`/prompts/${id}`),
  create: (data) => request.post('/prompts', data),
  update: (id, data) => request.put(`/prompts/${id}`, data),
  delete: (id) => request.delete(`/prompts/${id}`),
  publish: (id) => request.post(`/prompts/${id}/publish`),
  submit: (id) => request.post(`/prompts/${id}/submit`),
  audit: (id, data) => request.post(`/prompts/${id}/audit`, data),
  preview: (id, data) => request.post(`/prompts/${id}/preview`, data),
  generate: (data) => request.post('/prompts/generate', data),
  optimize: (id) => request.post(`/prompts/${id}/optimize`),
  copy: (id) => request.post(`/prompts/${id}/copy`),
  restore: (id, vid) => request.post(`/prompts/${id}/versions/${vid}/restore`),
  compare: (id, params) => request.get(`/prompts/${id}/compare`, { params }),
  runTest: (id, data) => request.post(`/prompts/${id}/tests`, data),
  tests: (id) => request.get(`/prompts/${id}/tests`),
  stats: (id) => request.get(`/prompts/${id}/stats`),
  logs: (id) => request.get(`/prompts/${id}/logs`),
  createExperiment: (id, data) => request.post(`/prompts/${id}/experiments`, data),
  experiments: (id) => request.get(`/prompts/${id}/experiments`),
  publishExperiment: (id, eid, data) => request.post(`/prompts/${id}/experiments/${eid}/publish`, data || {}),
}

export const resourcesApi = {
  list: (params) => request.get('/resources', { params }),
  get: (id) => request.get(`/resources/${encodeURIComponent(id)}`),
  register: (manifest) => request.post('/resources/register', { manifest }),
  invoke: (data) => request.post('/resources/invoke', data),
  mcpProbe: (data) => request.post('/resources/mcp/probe', data),
  stdioAliases: () => request.get('/resources/mcp/stdio-aliases'),
  offline: (id) => request.post(`/resources/${encodeURIComponent(id)}/offline`),
  match: (data) => request.post('/resources/match', data),
  events: (params) => request.get('/resources/events', { params }),
  health: (id) => request.post(`/resources/${encodeURIComponent(id)}/health`),
  registry: () => request.get('/resources/registry'),
  judges: () => request.get('/resources/judges'),
  heartbeat: (id) => request.post(`/resources/${encodeURIComponent(id)}/heartbeat`),
  calls: (id, params) =>
    request.get(`/resources/calls/${encodeURIComponent(id)}`, { params }),
}

export const batchApi = {
  run: (data) => request.post('/batch/run', data),
  status: (id) => request.get(`/batch/status/${id}`),
  cancel: (id) => request.delete(`/batch/${id}`),
  shard: (id, shardId, params) => request.get(`/batch/${id}/shards/${shardId}`, { params }),
  putResults: (id, shardId, data) => request.put(`/batch/${id}/shards/${shardId}/results`, data),
  results: (id, params) => request.get(`/batch/${id}/results`, { params, responseType: 'blob' })
}

export const qualityApi = {
  list: (params) => request.get('/quality', { params }),
  run: (params) => request.post('/quality/run', null, { params }),
  rules: () => request.get('/quality/rules'),
  updateRule: (id, data) => request.put(`/quality/rules/${id}`, data),
  issues: (params) => request.get('/quality/issues', { params }),
  handleIssue: (id, data) => request.post(`/quality/issues/${id}/handle`, data),
  download: (id) => request.get(`/quality/${id}/download`, { responseType: 'blob' })
}

export const tasksApi = {
  list: (params) => request.get('/tasks', { params }),
  get: (id) => request.get(`/tasks/${id}`),
  create: (data) => request.post('/tasks', data),
  results: (id, params) => request.get(`/tasks/${id}/results`, { params }),
  run: (id) => request.post(`/tasks/${id}/run`),
  cancel: (id) => request.post(`/tasks/${id}/cancel`),
  retry: (id) => request.post(`/tasks/${id}/retry`),
  catalog: () => request.get('/tasks/catalog'),
  templates: (params) => request.get('/tasks/templates', { params }),
  createTemplate: (data) => request.post('/tasks/templates', data),
  updateTemplate: (code, data) => request.put(`/tasks/templates/${encodeURIComponent(code)}`, data),
  submit: (id) => request.post(`/tasks/${id}/submit`),
  audit: (id, data) => request.post(`/tasks/${id}/audit`, data),
  events: (id) => request.get(`/tasks/${id}/events`),
  subtasks: (id) => request.get(`/tasks/${id}/subtasks`),
  report: (id, params) => request.get(`/tasks/${id}/report`, { params, responseType: 'blob' }),
  reportStatus: (id) => request.get(`/tasks/${id}/report-status`),
  renderReport: (id) => request.post(`/tasks/${id}/report/render`),
  lineage: (id) => request.get(`/tasks/${id}/lineage`),
  alerts: () => request.get('/tasks/alerts'),
  patchAlert: (id, data) => request.put(`/tasks/alerts/${id}`, data)
}

export const leaderboardApi = {
  list: (params) => request.get('/leaderboard', { params }),
  refresh: (params) => request.post('/leaderboard/refresh', null, { params }),
  export: (params) => request.get('/leaderboard/export', { params, responseType: 'blob' }),
  weights: () => request.get('/leaderboard/weights'),
  putWeights: (data) => request.put('/leaderboard/weights', data),
  costs: () => request.get('/leaderboard/costs'),
  putCost: (id, data) => request.put(`/leaderboard/costs/${id}`, data),
  radar: (params) => request.get('/leaderboard/radar', { params }),
  trend: (params) => request.get('/leaderboard/trend', { params }),
  currentRelease: (params) => request.get('/leaderboard/releases/current', { params }),
  publish: (params, data) => request.post('/leaderboard/releases/publish', data || {}, { params }),
  rollback: (params) => request.post('/leaderboard/releases/rollback', null, { params }),
}

export const servicesApi = {
  list: (params) => request.get('/services', { params }),
  create: (data) => request.post('/services', data),
  updateStatus: (id, params) => request.post(`/services/${id}/status`, null, { params }),
  quote: (id, data) => request.post(`/services/${id}/quote`, data),
  confirm: (id) => request.post(`/services/${id}/confirm`),
  report: (id, params) => request.get(`/services/${id}/report`, { params, responseType: 'blob' }),
  shadow: (id, data) => request.post(`/services/${id}/shadow`, data),
  promote: (id) => request.post(`/services/${id}/promote`),
  rollback: (id) => request.post(`/services/${id}/rollback`),
  workspaces: () => request.get('/services/workspaces'),
  createWorkspace: (data) => request.post('/services/workspaces', data),
  kanban: () => request.get('/services/kanban')
}

export const agentsApi = {
  profile: () => request.get('/agents/profile'),
  saveProfile: (data) => request.put('/agents/profile', data),
  catalog: () => request.get('/agents/catalog'),
  createDefinition: (data) => request.post('/agents/definitions', data),
  updateDefinition: (role, data) => request.put(`/agents/definitions/${role}`, data),
  deleteDefinition: (role) => request.delete(`/agents/definitions/${role}`),
  createSkill: (data) => request.post('/agents/skills', data),
  updateSkill: (code, data) => request.put(`/agents/skills/${code}`, data),
  deleteSkill: (code) => request.delete(`/agents/skills/${code}`),
  recipes: () => request.get('/agents/recipes'),
  saveRecipe: (id) => request.post(`/agents/sessions/${id}/recipe`),
  updateCapabilities: (id, data) => request.put(`/agents/sessions/${id}/capabilities`, data),
  delegate: (id, data) => request.post(`/agents/sessions/${id}/delegate`, data),
  knowledge: (params) => request.get('/agents/knowledge', { params }),
  addKnowledge: (data) => request.post('/agents/knowledge', data),
  sessions: () => request.get('/agents/sessions'),
  createSession: (data) => request.post('/agents/sessions', data),
  getSession: (id) => request.get(`/agents/sessions/${id}`),
  clarify: (id, data) => request.post(`/agents/sessions/${id}/clarify`, data),
  approve: (id, data) => request.post(`/agents/sessions/${id}/approve`, data || {}),
  confirm: (id, data) => request.post(`/agents/sessions/${id}/confirm`, data),
  monitor: (id) => request.get(`/agents/sessions/${id}/monitor`),
  diagnose: (id) => request.post(`/agents/sessions/${id}/diagnose`),
  collaborate: (id, data) => request.post(`/agents/sessions/${id}/collaborate`, data || {}),
  delegations: (id) => request.get(`/agents/sessions/${id}/delegations`),
  knowledgeCandidates: (params) => request.get('/agents/knowledge/candidates', { params }),
  reviewKnowledge: (id, data) => request.post(`/agents/knowledge/candidates/${id}/review`, data),
  deleteKnowledge: (id) => request.delete(`/agents/knowledge/candidates/${id}`),
  actSuggestion: (id, data) => request.post(`/agents/suggestions/${id}/act`, data),
  startRun: (sid, data) => request.post(`/agents/sessions/${sid}/runs`, data),
  getRun: (rid) => request.get(`/agents/runs/${rid}`),
  runEvents: (rid, params) => request.get(`/agents/runs/${rid}/events`, { params }),
  cancelRun: (rid) => request.post(`/agents/runs/${rid}/cancel`),
  resumeRun: (rid) => request.post(`/agents/runs/${rid}/resume`),
}

export const opsApi = {
  health: () => request.get('/health'),
  live: () => request.get('/live'),
  ready: () => request.get('/ready'),
  metrics: () => request.get('/metrics', { responseType: 'text' }),
  status: () => request.get('/ops/status'),
  backup: () => request.post('/ops/backup'),
  restoreDrill: (backupPath) =>
    request.post('/ops/restore-drill', null, { params: backupPath ? { backup_path: backupPath } : {} }),
  acceptance: () => request.get('/ops/acceptance'),
  admissionRun: (level = 'basic') => request.post('/ops/admission/run', { level }),
  admissionLatest: () => request.get('/ops/admission/latest'),
  fault: (body) => request.post('/ops/fault', body),
  gcSnapshots: () => request.post('/ops/gc-snapshots'),
  tickets: (params) => request.get('/ops/tickets', { params }),
  createTicket: (data) => request.post('/ops/tickets', data),
  patchTicket: (id, data) => request.patch(`/ops/tickets/${id}`, data),
  drills: () => request.get('/ops/drills'),
  createDrill: (data) => request.post('/ops/drills', data),
  authorizations: (params) => request.get('/ops/authorizations', { params }),
  createAuthorization: (data) => request.post('/ops/authorizations', data),
  disableAuthorization: (id) => request.post(`/ops/authorizations/${id}/disable`),
  report: () => request.get('/ops/report'),
  policy: () => request.get('/ops/policy')
}
