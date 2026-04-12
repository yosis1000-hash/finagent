/* FinAgent Main App */

// ─── State ────────────────────────────────────────
let currentUser = null;
let allItems = [];
let allUsers = [];
let currentItemId = null;
let currentView = 'list';

// ─── Org Config (loaded from server, with defaults) ───
let appConfig = {
  org_name: 'אגף',
  role_labels: {
    division_head: 'ראש אגף',
    department_head: 'ראש מחלקה',
    section_head: 'ראש תחום',
    office_manager: 'מנהלת משרד',
    economist: 'כלכלן',
    student: 'סטודנט',
    advisor: 'יועץ',
    team_lead: 'ראש צוות',
    external: 'חיצוני',
  }
};

function getRoleLabel(role) {
  return appConfig.role_labels[role] || role;
}

async function loadOrgConfig() {
  try {
    appConfig = await API.orgConfig();
  } catch { /* use defaults */ }
}

// Legacy alias used in several places
const ROLE_LABELS = new Proxy({}, { get: (_, key) => getRoleLabel(key) });

const TYPE_LABELS = {
  project: 'פרויקט',
  task: 'משימה',
  subtask: 'תת-משימה',
  followup: 'מעקב',
  reminder: 'תזכורת',
};

const STATUS_LABELS = {
  planning: 'תכנון', active: 'פעיל', on_hold: 'מושהה',
  open: 'פתוח', in_progress: 'בטיפול', pending_review: 'ממתין לסקירה',
  waiting: 'ממתין', responded: 'נענה', overdue: 'באיחור',
  completed: 'הושלם', cancelled: 'בוטל', archived: 'ארכיב', closed: 'סגור',
};

const PRIORITY_LABELS = {
  critical: 'קריטי', high: 'גבוה', medium: 'בינוני', low: 'נמוך',
};

const STATUS_OPTIONS_BY_TYPE = {
  project: ['planning', 'active', 'on_hold', 'completed', 'archived'],
  task: ['open', 'in_progress', 'pending_review', 'completed', 'cancelled'],
  subtask: ['open', 'in_progress', 'completed', 'cancelled'],
  followup: ['waiting', 'responded', 'overdue', 'closed'],
  reminder: ['open', 'completed'],
};

const MANAGEMENT_ROLES = ['division_head', 'section_head', 'office_manager'];

// ─── Init ─────────────────────────────────────────
window.addEventListener('load', async () => {
  const token = API.getToken();
  if (token) {
    try {
      const user = await API.me();
      initApp(user);
    } catch {
      showLogin();
    }
  } else {
    showLogin();
  }
});

function showLogin() {
  document.getElementById('app').classList.add('hidden');
  document.getElementById('login-screen').classList.remove('hidden');
}

async function initApp(user) {
  currentUser = user;
  localStorage.setItem('fa_user', JSON.stringify(user));
  document.getElementById('login-screen').classList.add('hidden');
  document.getElementById('app').classList.remove('hidden');

  document.getElementById('sidebar-name').textContent = user.name;
  document.getElementById('sidebar-role').textContent = ROLE_LABELS[user.role_type] || user.role_type;
  document.getElementById('sidebar-avatar').textContent = user.name[0];

  // Show admin nav only for allowed roles
  const adminNav = document.querySelectorAll('.admin-only');
  adminNav.forEach(el => {
    if (['division_head', 'office_manager'].includes(user.role_type)) {
      el.classList.remove('hidden');
    }
  });

  await loadOrgConfig();
  await loadUsers();
  showPanel('tasks');
}

// ─── Login ────────────────────────────────────────
document.getElementById('login-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const email = document.getElementById('login-email').value;
  const password = document.getElementById('login-password').value;
  const btn = document.getElementById('login-btn');
  const errEl = document.getElementById('login-error');

  btn.disabled = true;
  document.getElementById('login-btn-text').textContent = 'מתחבר...';
  errEl.classList.add('hidden');

  try {
    const data = await API.login(email, password);
    API.setToken(data.access_token);
    const user = await API.me();
    initApp(user);
  } catch (err) {
    errEl.textContent = 'אימייל או סיסמה שגויים';
    errEl.classList.remove('hidden');
    btn.disabled = false;
    document.getElementById('login-btn-text').textContent = 'כניסה למערכת';
  }
});

function logout() {
  API.clearToken();
  currentUser = null;
  allItems = [];
  showLogin();
}

// ─── Users ────────────────────────────────────────
async function loadUsers() {
  try {
    allUsers = await API.users();
  } catch {
    allUsers = [];
  }
}

// ─── Panel Navigation ─────────────────────────────
function showPanel(name) {
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

  const panel = document.getElementById(`panel-${name}`);
  panel.classList.remove('hidden');
  panel.classList.add('active');
  document.querySelector(`[data-panel="${name}"]`)?.classList.add('active');

  if (name === 'tasks') loadItems();
  if (name === 'dashboard') loadDashboard();
  if (name === 'reports') loadReports();
  if (name === 'admin') loadAdmin();
}

// ─── Tasks Panel ──────────────────────────────────
async function loadItems() {
  try {
    const params = {};
    if (document.getElementById('filter-my-work')?.checked) params.my_work = true;
    allItems = await API.items(params);
    renderItems();
  } catch (err) {
    showToast('שגיאה בטעינת פריטים', 'error');
  }
}

function filterItems() {
  renderItems();
}

function getFilteredItems() {
  const search = document.getElementById('search-input').value.toLowerCase();
  const type = document.getElementById('filter-type').value;
  const status = document.getElementById('filter-status').value;
  const priority = document.getElementById('filter-priority').value;
  const myWork = document.getElementById('filter-my-work').checked;

  return allItems.filter(item => {
    if (search && !item.title.toLowerCase().includes(search)) return false;
    if (type && item.type !== type) return false;
    if (status && item.status !== status) return false;
    if (priority && item.priority !== priority) return false;
    if (myWork && item.assignee_user_id !== currentUser?.id) return false;
    return true;
  });
}

function renderItems() {
  const items = getFilteredItems();
  if (currentView === 'list') renderListView(items);
  else renderBoardView(items);
}

function renderListView(items) {
  const tbody = document.getElementById('items-tbody');
  const empty = document.getElementById('items-empty');
  tbody.innerHTML = '';

  if (items.length === 0) {
    empty.classList.remove('hidden');
    return;
  }
  empty.classList.add('hidden');

  items.forEach(item => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>
        <a href="#" class="item-link" onclick="openItemModal(${item.id}); return false;">
          ${escHtml(item.title)}
        </a>
      </td>
      <td><span class="type-badge ${item.type}">${TYPE_LABELS[item.type] || item.type}</span></td>
      <td><span class="status-badge ${item.status}">${STATUS_LABELS[item.status] || item.status}</span></td>
      <td>${item.priority ? `<span class="priority-badge ${item.priority}">${PRIORITY_LABELS[item.priority]}</span>` : '-'}</td>
      <td>${item.assignee ? escHtml(item.assignee.name) : '-'}</td>
      <td>${item.deadline ? formatDate(item.deadline) : '-'}</td>
      <td>
        <button class="btn-ghost btn-sm" onclick="openItemModal(${item.id})">פתח</button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function renderBoardView(items) {
  const board = document.getElementById('kanban-board');
  const cols = ['open', 'in_progress', 'pending_review', 'completed', 'planning', 'active'];
  board.innerHTML = '';

  cols.forEach(status => {
    const colItems = items.filter(i => i.status === status);
    if (status === 'planning' && !items.some(i => i.type === 'project')) return;

    const col = document.createElement('div');
    col.className = 'kanban-col';
    col.innerHTML = `
      <div class="kanban-col-header">
        <span>${STATUS_LABELS[status]}</span>
        <span class="kanban-count">${colItems.length}</span>
      </div>
    `;
    colItems.forEach(item => {
      const card = document.createElement('div');
      card.className = 'kanban-card';
      card.onclick = () => openItemModal(item.id);
      card.innerHTML = `
        <div class="kanban-card-title">${escHtml(item.title)}</div>
        <div class="kanban-card-meta">
          <span class="type-badge ${item.type}">${TYPE_LABELS[item.type]}</span>
          ${item.deadline ? `<span>⏰ ${formatDate(item.deadline)}</span>` : ''}
          ${item.assignee ? `<span>👤 ${escHtml(item.assignee.name)}</span>` : ''}
        </div>
      `;
      col.appendChild(card);
    });
    board.appendChild(col);
  });
}

function setView(view) {
  currentView = view;
  document.getElementById('view-list').classList.toggle('active', view === 'list');
  document.getElementById('view-board').classList.toggle('active', view === 'board');
  document.getElementById('items-list-view').classList.toggle('hidden', view !== 'list');
  document.getElementById('items-board-view').classList.toggle('hidden', view !== 'board');
  renderItems();
}

// ─── Item Modal ───────────────────────────────────
async function openItemModal(itemId) {
  currentItemId = itemId;
  const modal = document.getElementById('item-modal');
  modal.classList.remove('hidden');

  try {
    const item = await API.item(itemId);
    const activity = await API.itemActivity(itemId);
    populateItemModal(item, activity);
  } catch (err) {
    showToast('שגיאה בטעינת פריט', 'error');
    closeItemModal();
  }
}

function populateItemModal(item, activity) {
  document.getElementById('modal-title').textContent = item.title;
  document.getElementById('modal-type-badge').textContent = TYPE_LABELS[item.type] || item.type;
  document.getElementById('modal-type-badge').className = `type-badge ${item.type}`;
  document.getElementById('modal-description').value = item.description || '';
  document.getElementById('modal-deadline').value = item.deadline || '';
  document.getElementById('modal-created').textContent = formatDate(item.created_at);
  document.getElementById('modal-updated').textContent = formatDate(item.updated_at);

  // AI Summary
  if (item.ai_summary) {
    document.getElementById('modal-ai-summary').classList.remove('hidden');
    document.getElementById('modal-ai-summary-text').textContent = item.ai_summary;
  } else {
    document.getElementById('modal-ai-summary').classList.add('hidden');
  }

  // Status options
  const statusSel = document.getElementById('modal-status');
  const statuses = STATUS_OPTIONS_BY_TYPE[item.type] || ['open', 'in_progress', 'completed'];
  statusSel.innerHTML = statuses.map(s =>
    `<option value="${s}" ${item.status === s ? 'selected' : ''}>${STATUS_LABELS[s]}</option>`
  ).join('');

  // Priority
  document.getElementById('modal-priority').value = item.priority || '';

  // Assignee
  const assigneeSel = document.getElementById('modal-assignee');
  assigneeSel.innerHTML = '<option value="">-</option>' +
    allUsers.map(u => `<option value="${u.id}" ${item.assignee_user_id === u.id ? 'selected' : ''}>${escHtml(u.name)}</option>`).join('');

  // Activity
  const actEl = document.getElementById('modal-activity');
  if (activity.length === 0) {
    actEl.innerHTML = '<p style="color:var(--gray-400);font-size:12px">אין פעילות עדיין</p>';
  } else {
    actEl.innerHTML = activity.map(a => `
      <div class="activity-item">
        <span class="act-actor">${escHtml(a.actor)}</span>
        <span>${escHtml(a.action)}</span>
        ${a.details ? `<span class="deferred">${escHtml(a.details)}</span>` : ''}
        <span class="act-time">${formatDate(a.created_at)}</span>
      </div>
    `).join('');
  }
}

function closeItemModal() {
  document.getElementById('item-modal').classList.add('hidden');
  currentItemId = null;
}

async function saveItemField(field, value) {
  if (!currentItemId) return;
  try {
    await API.updateItem(currentItemId, { [field]: value || null });
    const idx = allItems.findIndex(i => i.id === currentItemId);
    if (idx >= 0) allItems[idx][field] = value;
    showToast('נשמר');
  } catch (err) {
    showToast('שגיאה בשמירה: ' + err.message, 'error');
  }
}

async function saveItemDescription() {
  if (!currentItemId) return;
  const desc = document.getElementById('modal-description').value;
  await saveItemField('description', desc);
}

async function archiveCurrentItem() {
  if (!currentItemId) return;
  try {
    await API.deleteItem(currentItemId);
    allItems = allItems.filter(i => i.id !== currentItemId);
    closeItemModal();
    renderItems();
    showToast('הפריט הועבר לארכיב');
  } catch (err) {
    showToast('שגיאה: ' + err.message, 'error');
  }
}

// ─── Create Item Modal ────────────────────────────
function openCreateModal() {
  document.getElementById('create-modal').classList.remove('hidden');

  // Populate assignee list
  const sel = document.getElementById('create-assignee');
  sel.innerHTML = '<option value="">- בחר -</option>' +
    allUsers.map(u => `<option value="${u.id}">${escHtml(u.name)}</option>`).join('');

  const awaited = document.getElementById('create-awaited-from');
  awaited.innerHTML = '<option value="">- בחר -</option>' +
    allUsers.map(u => `<option value="${u.id}">${escHtml(u.name)}</option>`).join('');

  updateCreateFormFields();
}

function closeCreateModal() {
  document.getElementById('create-modal').classList.add('hidden');
  document.getElementById('create-form').reset();
}

function updateCreateFormFields() {
  const type = document.getElementById('create-type').value;
  const followupFields = document.getElementById('create-followup-fields');
  followupFields.style.display = type === 'followup' ? 'block' : 'none';
}

async function submitCreateForm(e) {
  e.preventDefault();
  const type = document.getElementById('create-type').value;
  const title = document.getElementById('create-title').value;
  const description = document.getElementById('create-description').value;
  const assigneeId = document.getElementById('create-assignee').value;
  const priority = document.getElementById('create-priority').value;
  const deadline = document.getElementById('create-deadline').value;
  const awaitedFrom = document.getElementById('create-awaited-from').value;
  const expectedBy = document.getElementById('create-expected-by').value;

  const payload = {
    type, title,
    description: description || null,
    assignee_user_id: assigneeId ? parseInt(assigneeId) : null,
    priority,
    deadline: deadline || null,
    awaited_from_user_id: awaitedFrom ? parseInt(awaitedFrom) : null,
    expected_by: expectedBy || null,
  };

  try {
    const item = await API.createItem(payload);
    allItems.unshift(item);
    renderItems();
    closeCreateModal();
    showToast('פריט נוצר בהצלחה', 'success');
  } catch (err) {
    showToast('שגיאה ביצירת פריט: ' + err.message, 'error');
  }
}

// ─── Dashboard ────────────────────────────────────
async function loadDashboard() {
  try {
    const stats = await API.dashStats();
    document.getElementById('stat-open').textContent = stats.total_open;
    document.getElementById('stat-due-week').textContent = stats.due_this_week;
    document.getElementById('stat-overdue').textContent = stats.overdue;
    document.getElementById('stat-completed').textContent = stats.completed_this_month;

    if (MANAGEMENT_ROLES.includes(currentUser?.role_type)) {
      document.querySelectorAll('.management-only').forEach(el => el.classList.remove('hidden'));
      loadActivityTable();
      loadFollowupsSection();
    }
  } catch (err) {
    showToast('שגיאה בטעינת דשבורד', 'error');
  }
}

async function loadActivityTable() {
  try {
    const activity = await API.dashActivity();
    const tbody = document.getElementById('activity-tbody');
    tbody.innerHTML = activity.map(a => `
      <tr>
        <td>${escHtml(a.name)}</td>
        <td>${ROLE_LABELS[a.role_type] || a.role_type}</td>
        <td>${a.open_tasks}</td>
        <td>${a.last_activity ? formatDate(a.last_activity) : 'אין'}</td>
      </tr>
    `).join('');
  } catch {}
}

async function loadFollowupsSection() {
  try {
    const followups = await API.dashFollowups();
    const list = document.getElementById('followups-list');
    if (followups.length === 0) {
      list.innerHTML = '<p style="color:var(--gray-400)">אין מעקבים פתוחים</p>';
      return;
    }
    list.innerHTML = followups.map(f => `
      <div class="report-card">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <strong>${escHtml(f.title)}</strong>
          ${f.is_overdue ? '<span class="status-badge overdue">באיחור</span>' : '<span class="status-badge waiting">ממתין</span>'}
        </div>
        <div style="font-size:12px;color:var(--gray-600);margin-top:4px">
          ימים מהיצירה: ${f.days_since_created}
          ${f.expected_by ? ` | תאריך צפוי: ${formatDate(f.expected_by)}` : ''}
        </div>
      </div>
    `).join('');
  } catch {}
}

// ─── Reports ──────────────────────────────────────
async function loadReports() {
  try {
    // Load open tasks for context
    const myItems = await API.items({ my_work: true });
    const openTasks = myItems.filter(i => !['completed','cancelled','archived'].includes(i.status));
    const tasksList = document.getElementById('open-tasks-for-report');
    if (openTasks.length > 0) {
      tasksList.innerHTML = `
        <div class="open-tasks-list">
          <p>משימות פתוחות שלך:</p>
          <ul>${openTasks.map(t => `<li>${escHtml(t.title)}</li>`).join('')}</ul>
        </div>`;
    }

    // My reports
    const myReports = await API.myReports();
    renderReportHistory(myReports);

    // Management: all reports
    if (MANAGEMENT_ROLES.includes(currentUser?.role_type)) {
      document.getElementById('all-reports-section').classList.remove('hidden');
      const allReports = await API.allReports();
      renderAllReports(allReports);
    }
  } catch (err) {
    showToast('שגיאה בטעינת דיווחים', 'error');
  }
}

function renderReportHistory(reports) {
  const el = document.getElementById('report-history');
  if (reports.length === 0) {
    el.innerHTML = '<p style="color:var(--gray-400);font-size:13px">אין דיווחים עדיין</p>';
    return;
  }
  el.innerHTML = reports.map(r => reportCard(r)).join('');
}

function renderAllReports(reports) {
  const el = document.getElementById('all-reports-list');
  el.innerHTML = reports.map(r => `
    <div class="report-card">
      <div style="display:flex;gap:10px;align-items:center;margin-bottom:6px">
        <strong>${r.user_name || 'משתמש'}</strong>
        <span style="color:var(--gray-400);font-size:12px">${formatDate(r.submitted_at)}</span>
        ${r.ai_score ? `<span class="score-badge score-${r.ai_score}">${r.ai_score}</span>` : ''}
      </div>
      ${r.ai_score_reasoning ? `<p style="font-size:12px;color:var(--gray-600)">${escHtml(r.ai_score_reasoning)}</p>` : ''}
    </div>
  `).join('');
}

function reportCard(r) {
  return `
    <div class="report-card">
      <div style="display:flex;gap:10px;align-items:center;margin-bottom:6px">
        <span style="color:var(--gray-600);font-size:12px">${formatDate(r.submitted_at)}</span>
        ${r.ai_score ? `<span class="score-badge score-${r.ai_score}">${r.ai_score}/5</span>` : ''}
      </div>
      ${r.report_text ? `<p style="font-size:13px">${escHtml(r.report_text.substring(0, 120))}${r.report_text.length > 120 ? '...' : ''}</p>` : ''}
      ${r.ai_score_reasoning ? `<p style="font-size:12px;color:var(--gray-600);margin-top:4px">🤖 ${escHtml(r.ai_score_reasoning)}</p>` : ''}
    </div>
  `;
}

async function submitReport(e) {
  e.preventDefault();
  const text = document.getElementById('report-text').value;
  const periodStart = document.getElementById('report-period-start').value;
  const periodEnd = document.getElementById('report-period-end').value;
  const resultEl = document.getElementById('report-result');

  try {
    const result = await API.submitReport({
      report_text: text,
      period_start: periodStart || null,
      period_end: periodEnd || null,
    });
    resultEl.classList.remove('hidden');
    resultEl.innerHTML = `
      <div style="background:#f0fff4;border:1px solid #9ae6b4;border-radius:8px;padding:14px;margin-top:12px">
        <div style="font-weight:600;margin-bottom:6px">
          הדיווח התקבל! ציון AI:
          <span class="score-badge score-${result.ai_score}">${result.ai_score}/5</span>
        </div>
        ${result.ai_score_reasoning ? `<p style="font-size:13px;color:#276749">${escHtml(result.ai_score_reasoning)}</p>` : ''}
      </div>`;
    document.getElementById('report-text').value = '';
    showToast('הדיווח הוגש בהצלחה', 'success');
  } catch (err) {
    showToast('שגיאה בהגשת הדיווח: ' + err.message, 'error');
  }
}

// ─── Admin Panel ──────────────────────────────────
async function loadAdmin() {
  await loadUsersTable();
  await loadTeamsList();
}

function showAdminTab(tab) {
  document.querySelectorAll('.admin-tab-content').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById(`admin-tab-${tab}`).classList.add('active');
  event.target.classList.add('active');

  if (tab === 'org') loadOrgTree();
  if (tab === 'audit') loadAuditLog();
  if (tab === 'settings') populateSettingsForm();
}

async function loadUsersTable() {
  try {
    const users = await API.users();
    allUsers = users;
    const tbody = document.getElementById('users-tbody');
    tbody.innerHTML = users.map(u => `
      <tr>
        <td>${escHtml(u.name)}</td>
        <td dir="ltr">${escHtml(u.email)}</td>
        <td>${ROLE_LABELS[u.role_type] || u.role_type}</td>
        <td>${u.parent_id ? (users.find(p => p.id === u.parent_id)?.name || u.parent_id) : '-'}</td>
        <td>${u.report_frequency === 'daily' ? 'יומי' : u.report_frequency === 'weekly' ? 'שבועי' : 'ללא'}</td>
        <td><span class="status-badge ${u.is_active ? 'active' : 'archived'}">${u.is_active ? 'פעיל' : 'לא פעיל'}</span></td>
        <td style="display:flex;gap:6px">
          <button class="btn-ghost btn-sm" onclick="openEditUserModal(${u.id})">ערוך</button>
          ${currentUser?.role_type === 'division_head' ? `
            <button class="btn-ghost btn-sm" onclick="deactivateUser(${u.id}, '${escHtml(u.name)}')">
              ${u.is_active ? 'השבת' : 'השבתה'}
            </button>
          ` : ''}
        </td>
      </tr>
    `).join('');
  } catch {}
}

async function loadTeamsList() {
  const list = document.getElementById('teams-list');
  try {
    const teams = await API.teams();
    if (teams.length === 0) {
      list.innerHTML = '<p style="color:var(--gray-400);margin-bottom:16px">אין צוותים עדיין — לחץ "+ צוות חדש" ליצירה</p>';
      return;
    }
    list.innerHTML = '';
    for (const t of teams) {
      let detail = { members: [] };
      try { detail = await API.teamDetail(t.id); } catch {}
      const leadName = allUsers.find(u => u.id === t.lead_user_id)?.name;
      const card = document.createElement('div');
      card.className = 'team-card';
      card.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center">
          <div>
            <h4 style="margin:0">${escHtml(t.name)}</h4>
            ${t.focus ? `<p style="color:var(--gray-600);font-size:13px;margin:4px 0 0">${escHtml(t.focus)}</p>` : ''}
            ${leadName ? `<p style="font-size:12px;margin:4px 0 0;color:var(--gray-500)">ראש צוות: ${escHtml(leadName)}</p>` : ''}
          </div>
          <button class="btn-ghost btn-sm" onclick="openAddMemberModal(${t.id}, '${escHtml(t.name)}')">+ הוסף חבר</button>
        </div>
        <div class="team-members-list" style="margin-top:12px;display:flex;flex-wrap:wrap;gap:8px">
          ${detail.members.map(m => `
            <div class="team-member-chip">
              <span>${escHtml(m.name)}</span>
              <span style="color:var(--gray-400);font-size:11px">${getRoleLabel(m.role_type)}</span>
              <button class="btn-remove-member" onclick="removeMember(${t.id}, ${m.id})" title="הסר">✕</button>
            </div>
          `).join('')}
          ${detail.members.length === 0 ? '<span style="color:var(--gray-400);font-size:12px">אין חברים עדיין</span>' : ''}
        </div>
      `;
      list.appendChild(card);
    }
  } catch {
    list.innerHTML = '<p style="color:var(--gray-400)">שגיאה בטעינת צוותים</p>';
  }
}

async function removeMember(teamId, userId) {
  try {
    await API.removeTeamMember(teamId, userId);
    await loadTeamsList();
    showToast('החבר הוסר');
  } catch (err) {
    showToast('שגיאה: ' + err.message, 'error');
  }
}

let _addMemberTeamId = null;
function openAddMemberModal(teamId, teamName) {
  _addMemberTeamId = teamId;
  document.getElementById('add-member-title').textContent = `הוסף חבר לצוות "${teamName}"`;
  const sel = document.getElementById('add-member-user-select');
  sel.innerHTML = allUsers.map(u =>
    `<option value="${u.id}">${escHtml(u.name)} — ${getRoleLabel(u.role_type)}</option>`
  ).join('');
  document.getElementById('add-member-modal').classList.remove('hidden');
}

function closeAddMemberModal() {
  document.getElementById('add-member-modal').classList.add('hidden');
  _addMemberTeamId = null;
}

async function submitAddMember() {
  if (!_addMemberTeamId) return;
  const userId = parseInt(document.getElementById('add-member-user-select').value);
  try {
    await API.addTeamMember(_addMemberTeamId, userId);
    closeAddMemberModal();
    await loadTeamsList();
    showToast('החבר נוסף', 'success');
  } catch (err) {
    showToast('שגיאה: ' + err.message, 'error');
  }
}

async function loadOrgTree() {
  const el = document.getElementById('org-tree');
  el.innerHTML = '<p style="color:var(--gray-400)">טוען...</p>';
  try {
    const [tree, teams] = await Promise.all([API.orgTree(), API.teams()]);
    el.innerHTML = '';

    // ── Formal hierarchy ──
    const formalSection = document.createElement('div');
    formalSection.className = 'org-section';
    formalSection.innerHTML = '<h4 class="org-section-title">מבנה היררכי רשמי</h4>';
    const treeWrap = document.createElement('div');
    treeWrap.className = 'org-tree-wrap';
    treeWrap.dir = 'ltr';
    tree.forEach(root => treeWrap.appendChild(buildOrgNode(root)));
    formalSection.appendChild(treeWrap);
    el.appendChild(formalSection);

    // ── Teams / informal ──
    if (teams.length > 0) {
      const teamsSection = document.createElement('div');
      teamsSection.className = 'org-section';
      teamsSection.innerHTML = '<h4 class="org-section-title">צוותים אד-הוק ופרויקטים</h4>';
      const teamsGrid = document.createElement('div');
      teamsGrid.className = 'org-teams-grid';

      for (const team of teams) {
        try {
          const detail = await API.teamDetail(team.id);
          const card = document.createElement('div');
          card.className = 'org-team-card';
          card.innerHTML = `
            <div class="org-team-name">${escHtml(team.name)}</div>
            ${team.focus ? `<div class="org-team-focus">${escHtml(team.focus)}</div>` : ''}
            <div class="org-team-members">
              ${detail.members.map(m => `
                <div class="org-team-member">
                  <span class="member-avatar">${m.name[0]}</span>
                  <span>${escHtml(m.name)}</span>
                  <span class="org-member-role">${getRoleLabel(m.role_type)}</span>
                </div>
              `).join('') || '<span style="color:var(--gray-400);font-size:12px">אין חברים</span>'}
            </div>
          `;
          teamsGrid.appendChild(card);
        } catch {}
      }
      teamsSection.appendChild(teamsGrid);
      el.appendChild(teamsSection);
    }
  } catch (err) {
    document.getElementById('org-tree').innerHTML = '<p style="color:var(--gray-400)">שגיאה בטעינת עץ ארגוני</p>';
  }
}

function buildOrgNode(node) {
  const wrap = document.createElement('li');
  wrap.className = 'org-li';

  const box = document.createElement('div');
  box.className = 'org-node-box';
  const openBadge = node.open_tasks > 0
    ? `<span class="org-tasks-open">${node.open_tasks} פתוחות</span>` : '';
  const doneBadge = node.done_tasks > 0
    ? `<span class="org-tasks-done">${node.done_tasks} הושלמו</span>` : '';
  const teamBadges = (node.teams || []).map(t =>
    `<span class="org-team-badge">${escHtml(t)}</span>`
  ).join('');

  box.innerHTML = `
    <div class="org-node-role">${getRoleLabel(node.role_type)}</div>
    <div class="org-node-name">${escHtml(node.name)}</div>
    <div class="org-node-meta">
      ${openBadge}${doneBadge}
      ${teamBadges}
    </div>
  `;
  wrap.appendChild(box);

  if (node.children?.length) {
    const ul = document.createElement('ul');
    ul.className = 'org-ul';
    node.children.forEach(c => ul.appendChild(buildOrgNode(c)));
    wrap.appendChild(ul);
  }
  return wrap;
}

async function loadAuditLog() {
  const el = document.getElementById('audit-log-list');
  el.innerHTML = '<p style="color:var(--gray-400)">טוען...</p>';
  try {
    const logs = await API.auditLogs();
    if (logs.length === 0) {
      el.innerHTML = '<p style="color:var(--gray-400)">אין רשומות ביקורת</p>';
      return;
    }
    const ACTION_LABELS = {
      create: 'יצר', update: 'עדכן', deactivate: 'השבית',
      submit_report: 'הגיש דיווח', archive: 'העביר לארכיב',
    };
    const ENTITY_LABELS = { user: 'משתמש', work_item: 'פריט', team: 'צוות', report: 'דיווח' };
    el.innerHTML = logs.map(l => `
      <div class="report-card" style="display:flex;justify-content:space-between;align-items:center;padding:10px 14px">
        <div>
          <strong>${escHtml(l.actor_name)}</strong>
          <span style="color:var(--gray-600);margin:0 6px">${ACTION_LABELS[l.action] || l.action}</span>
          <span>${ENTITY_LABELS[l.entity_type] || l.entity_type}${l.entity_id ? ` #${l.entity_id}` : ''}</span>
          ${l.details ? `<div style="font-size:12px;color:var(--gray-500);margin-top:2px">${escHtml(l.details)}</div>` : ''}
        </div>
        <span style="font-size:12px;color:var(--gray-400);white-space:nowrap">${formatDate(l.created_at)}</span>
      </div>
    `).join('');
  } catch {
    el.innerHTML = '<p style="color:var(--gray-400)">שגיאה בטעינת יומן</p>';
  }
}

// ─── Org Settings ─────────────────────────────────
function populateSettingsForm() {
  document.getElementById('cfg-org-name').value = appConfig.org_name || '';
  const roles = appConfig.role_labels || {};
  Object.keys(roles).forEach(key => {
    const el = document.getElementById(`cfg-role-${key}`);
    if (el) el.value = roles[key] || '';
  });
}

async function saveOrgSettings() {
  const roleKeys = ['division_head', 'section_head', 'office_manager', 'economist', 'student', 'advisor', 'team_lead', 'external'];
  const role_labels = {};
  roleKeys.forEach(key => {
    const el = document.getElementById(`cfg-role-${key}`);
    if (el && el.value.trim()) role_labels[key] = el.value.trim();
  });
  const payload = {
    org_name: document.getElementById('cfg-org-name').value.trim() || 'אגף',
    role_labels,
  };
  try {
    appConfig = await API.saveOrgConfig(payload);
    showToast('ההגדרות נשמרו', 'success');
  } catch (err) {
    showToast('שגיאה בשמירה: ' + err.message, 'error');
  }
}

// Create User
function openCreateUserModal() {
  const sel = document.getElementById('cu-parent');
  sel.innerHTML = '<option value="">- ללא -</option>' +
    allUsers.map(u => `<option value="${u.id}">${escHtml(u.name)}</option>`).join('');
  document.getElementById('create-user-modal').classList.remove('hidden');
}

function closeCreateUserModal() {
  document.getElementById('create-user-modal').classList.add('hidden');
  document.getElementById('create-user-form').reset();
}

async function submitCreateUser(e) {
  e.preventDefault();
  const payload = {
    name: document.getElementById('cu-name').value,
    email: document.getElementById('cu-email').value,
    password: document.getElementById('cu-password').value,
    role_type: document.getElementById('cu-role').value,
    parent_id: document.getElementById('cu-parent').value ? parseInt(document.getElementById('cu-parent').value) : null,
    report_frequency: document.getElementById('cu-report-freq').value,
  };
  try {
    await API.createUser(payload);
    await loadUsersTable();
    closeCreateUserModal();
    showToast('משתמש נוצר בהצלחה', 'success');
  } catch (err) {
    showToast('שגיאה: ' + err.message, 'error');
  }
}

async function deactivateUser(id, name) {
  if (!confirm(`האם להשבית את ${name}?`)) return;
  try {
    await API.deactivateUser(id);
    await loadUsersTable();
    showToast(`${name} הושבת`);
  } catch (err) {
    showToast('שגיאה: ' + err.message, 'error');
  }
}

// Edit User
function openEditUserModal(userId) {
  const user = allUsers.find(u => u.id === userId);
  if (!user) return;

  document.getElementById('eu-id').value = user.id;
  document.getElementById('eu-name').value = user.name;
  document.getElementById('eu-email').value = user.email;
  document.getElementById('eu-role').value = user.role_type;
  document.getElementById('eu-report-freq').value = user.report_frequency;

  const sel = document.getElementById('eu-parent');
  sel.innerHTML = '<option value="">- ללא -</option>' +
    allUsers.filter(u => u.id !== userId).map(u =>
      `<option value="${u.id}" ${u.id === user.parent_id ? 'selected' : ''}>${escHtml(u.name)}</option>`
    ).join('');

  document.getElementById('edit-user-modal').classList.remove('hidden');
}

function closeEditUserModal() {
  document.getElementById('edit-user-modal').classList.add('hidden');
  document.getElementById('edit-user-form').reset();
}

async function submitEditUser(e) {
  e.preventDefault();
  const id = parseInt(document.getElementById('eu-id').value);
  const payload = {
    name: document.getElementById('eu-name').value,
    email: document.getElementById('eu-email').value,
    role_type: document.getElementById('eu-role').value,
    parent_id: document.getElementById('eu-parent').value ? parseInt(document.getElementById('eu-parent').value) : null,
    report_frequency: document.getElementById('eu-report-freq').value,
  };
  try {
    await API.updateUser(id, payload);
    await loadUsersTable();
    closeEditUserModal();
    showToast('המשתמש עודכן בהצלחה', 'success');
  } catch (err) {
    showToast('שגיאה: ' + err.message, 'error');
  }
}

// Create Team
function openCreateTeamModal() {
  const sel = document.getElementById('ct-lead');
  const sectionHeads = allUsers.filter(u => ['section_head', 'division_head'].includes(u.role_type));
  sel.innerHTML = '<option value="">- ללא -</option>' +
    sectionHeads.map(u => `<option value="${u.id}">${escHtml(u.name)}</option>`).join('');
  document.getElementById('create-team-modal').classList.remove('hidden');
}

function closeCreateTeamModal() {
  document.getElementById('create-team-modal').classList.add('hidden');
  document.getElementById('create-team-form').reset();
}

async function submitCreateTeam(e) {
  e.preventDefault();
  const payload = {
    name: document.getElementById('ct-name').value,
    focus: document.getElementById('ct-focus').value || null,
    lead_user_id: document.getElementById('ct-lead').value ? parseInt(document.getElementById('ct-lead').value) : null,
  };
  try {
    await API.createTeam(payload);
    await loadTeamsList();
    closeCreateTeamModal();
    showToast('צוות נוצר בהצלחה', 'success');
  } catch (err) {
    showToast('שגיאה: ' + err.message, 'error');
  }
}

// ─── Toast ────────────────────────────────────────
let toastTimer = null;
function showToast(msg, type = '') {
  const toast = document.getElementById('toast');
  toast.textContent = msg;
  toast.className = 'toast' + (type ? ` ${type}` : '');
  toast.classList.remove('hidden');
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.add('hidden'), 3000);
}

// ─── Utils ────────────────────────────────────────
function escHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatDate(dateStr) {
  if (!dateStr) return '-';
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return dateStr;
  return d.toLocaleDateString('he-IL', { day: '2-digit', month: '2-digit', year: 'numeric' });
}
