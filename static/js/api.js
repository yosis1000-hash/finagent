/* FinAgent API client */

const API = {
  baseUrl: '',
  token: null,

  setToken(token) {
    this.token = token;
    localStorage.setItem('fa_token', token);
  },

  getToken() {
    if (!this.token) this.token = localStorage.getItem('fa_token');
    return this.token;
  },

  clearToken() {
    this.token = null;
    localStorage.removeItem('fa_token');
    localStorage.removeItem('fa_user');
  },

  async request(method, path, body = null) {
    const headers = { 'Content-Type': 'application/json' };
    const token = this.getToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const opts = { method, headers };
    if (body) opts.body = JSON.stringify(body);

    const res = await fetch(this.baseUrl + path, opts);
    if (res.status === 401) {
      this.clearToken();
      showLogin();
      throw new Error('Unauthorized');
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    if (res.status === 204) return null;
    return res.json();
  },

  get: (path) => API.request('GET', path),
  post: (path, body) => API.request('POST', path, body),
  put: (path, body) => API.request('PUT', path, body),
  delete: (path) => API.request('DELETE', path),

  // Auth
  login: (email, password) => API.post('/api/auth/login', { email, password }),

  // Users
  me: () => API.get('/api/users/me'),
  users: () => API.get('/api/users/'),
  orgTree: () => API.get('/api/users/org-tree'),
  createUser: (data) => API.post('/api/users/', data),
  updateUser: (id, data) => API.put(`/api/users/${id}`, data),
  deactivateUser: (id) => API.delete(`/api/users/${id}`),

  // Teams
  teams: () => API.get('/api/teams/'),
  team: (id) => API.get(`/api/teams/${id}`),
  createTeam: (data) => API.post('/api/teams/', data),
  updateTeam: (id, data) => API.put(`/api/teams/${id}`, data),
  addTeamMember: (teamId, userId) => API.post(`/api/teams/${teamId}/members`, { user_id: userId }),
  removeTeamMember: (teamId, userId) => API.delete(`/api/teams/${teamId}/members/${userId}`),

  // Work Items
  items: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return API.get('/api/items/' + (qs ? '?' + qs : ''));
  },
  item: (id) => API.get(`/api/items/${id}`),
  createItem: (data) => API.post('/api/items/', data),
  updateItem: (id, data) => API.put(`/api/items/${id}`, data),
  deleteItem: (id) => API.delete(`/api/items/${id}`),
  itemActivity: (id) => API.get(`/api/items/${id}/activity`),

  // Dashboard
  dashStats: () => API.get('/api/dashboard/stats'),
  dashActivity: () => API.get('/api/dashboard/activity'),
  dashFollowups: () => API.get('/api/dashboard/followups'),
  dashReportScores: () => API.get('/api/dashboard/reports'),

  // Reports
  submitReport: (data) => API.post('/api/reports/submit', data),
  myReports: () => API.get('/api/reports/my'),
  allReports: () => API.get('/api/reports/'),

  // Audit
  auditLogs: () => API.get('/api/users/audit-logs'),
};
