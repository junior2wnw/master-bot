/* ═══════════════════════════════════════════════════════════
   МастерБот Mini App — Core Application
   Telegram Web App SDK + Vanilla JS SPA
   ═══════════════════════════════════════════════════════════ */

const API = '/api/v1';
const tg = window.Telegram?.WebApp;

// ─── State ──────────────────────────────────────────────────
const state = {
  user: null,
  screen: 'dashboard',
  history: [],
  activeEstimateId: null,
  cartItems: 0,
  searchDebounce: null,
  catalogPath: [], // breadcrumb: [{type, id, name}]
  notifications: {
    page: 1,
    pageSize: 8,
    hasMore: false,
    selectedId: null,
    items: [],
    unreadCount: 0,
  },
};

const ROLE_INHERITANCE = {
  product_owner: ['admin'],
  admin: ['senior_master'],
  senior_master: ['master'],
  master: [],
  client: [],
};

const ROLE_ORDER = ['client', 'master', 'senior_master', 'admin', 'product_owner'];

function effectiveRoles(roles = []) {
  const resolved = new Set();
  const stack = [...roles];

  while (stack.length > 0) {
    const role = stack.pop();
    if (!role || resolved.has(role)) continue;
    resolved.add(role);
    (ROLE_INHERITANCE[role] || []).forEach(parent => stack.push(parent));
  }

  return resolved;
}

function hasRole(roles = [], role) {
  return effectiveRoles(roles).has(role);
}

function highestRole(roles = []) {
  const resolved = effectiveRoles(roles);
  for (let i = ROLE_ORDER.length - 1; i >= 0; i -= 1) {
    if (resolved.has(ROLE_ORDER[i])) return ROLE_ORDER[i];
  }
  return null;
}

// ─── Init ───────────────────────────────────────────────────
async function init() {
  if (tg) {
    tg.ready();
    tg.expand();
    tg.enableClosingConfirmation();
  }

  try {
    const initData = tg?.initData || JSON.stringify({id: 1, first_name: 'Dev', username: 'dev'});
    const res = await api('POST', '/auth', {init_data: initData});
    state.user = res;
    applyRoleContext(res);
    setupUI();
    await loadDashboard();
  } catch (e) {
    console.error('Auth failed:', e);
    document.getElementById('loader').innerHTML = '<p style="color:var(--destructive);padding:20px">Ошибка авторизации</p>';
    return;
  }

  hideLoader();
  setupSearch();
}

function hideLoader() {
  document.getElementById('loader').classList.add('hidden');
}

// ─── API ────────────────────────────────────────────────────
async function api(method, path, body) {
  const url = new URL(API + path, window.location.origin);
  if (state.user && method === 'GET') {
    url.searchParams.set('tg_id', state.user.telegram_id);
  }

  const opts = {method, headers: {}};
  if (body) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
    if (state.user) {
      url.searchParams.set('tg_id', state.user.telegram_id);
    }
  }

  const res = await fetch(url, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({detail: 'Error'}));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

function applyRoleContext(context = {}) {
  if (!state.user) return;
  state.user = {
    ...state.user,
    roles: context.roles || state.user.roles || [],
    direct_roles: context.direct_roles || state.user.direct_roles || [],
    active_role: context.active_role ?? state.user.active_role ?? null,
    active_role_label: context.active_role_label || state.user.active_role_label || '',
    max_role: context.max_role ?? state.user.max_role ?? null,
    max_role_label: context.max_role_label || state.user.max_role_label || '',
    role_override: context.role_override ?? state.user.role_override ?? null,
    can_switch_role: context.can_switch_role ?? state.user.can_switch_role ?? false,
    available_roles: context.available_roles || state.user.available_roles || [],
    is_role_switched: context.is_role_switched ?? state.user.is_role_switched ?? false,
  };
}

// ─── Navigation ─────────────────────────────────────────────
function navigate(screen, params = {}) {
  if (state.screen !== screen) {
    state.history.push({screen: state.screen, params: {}});
  }
  state.screen = screen;

  // Hide all screens, show target
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  const el = document.getElementById('screen-' + screen);
  if (el) el.classList.add('active');

  // Update tabs
  document.querySelectorAll('.tab').forEach(t => {
    t.classList.toggle('active', t.dataset.tab === screen);
  });

  // Back button
  document.getElementById('btn-back').classList.toggle('hidden', state.history.length === 0);

  // Header title
  const titles = {
    dashboard: 'МастерБот', search: 'Поиск', catalog: 'Каталог',
    estimates: 'Сметы', estimate: 'Смета', orders: 'Заказы',
    order: 'Заказ', earnings: 'Доходы', approvals: 'Согласования',
    analytics: 'Аналитика', profile: 'Профиль', item: 'Работа',
    notifications: 'Уведомления',
    suggestions: 'Предложения',
    'profile-edit': 'Личные данные',
    qr: 'Оплата',
  };
  document.getElementById('header-title').textContent = params.title || titles[screen] || '';

  // Load screen data
  loadScreen(screen, params);
}

function goBack() {
  if (state.history.length > 0) {
    const prev = state.history.pop();
    state.screen = prev.screen;
    document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
    const el = document.getElementById('screen-' + prev.screen);
    if (el) el.classList.add('active');
    document.querySelectorAll('.tab').forEach(t => {
      t.classList.toggle('active', t.dataset.tab === prev.screen);
    });
    document.getElementById('btn-back').classList.toggle('hidden', state.history.length === 0);
    const titles = {dashboard:'МастерБот',search:'Поиск',catalog:'Каталог',estimates:'Сметы',profile:'Профиль'};
    document.getElementById('header-title').textContent = titles[prev.screen] || '';
  }
}

async function loadScreen(screen, params) {
  switch (screen) {
    case 'dashboard': await loadDashboard(); break;
    case 'catalog': await loadCatalog(params); break;
    case 'search': document.getElementById('search-input').focus(); break;
    case 'estimates': await loadEstimates(); break;
    case 'estimate': await loadEstimate(params.id); break;
    case 'orders': await loadOrders(); break;
    case 'order': await loadOrder(params.id); break;
    case 'earnings': await loadEarnings(); break;
    case 'approvals': await loadApprovals(); break;
    case 'analytics': await loadAnalytics(); break;
    case 'profile': loadProfile(); break;
    case 'item': await loadItem(params.id); break;
    case 'notifications': await loadNotifications(); break;
    case 'suggestions': await loadSuggestionsComposer(); break;
    case 'profile-edit': await loadProfileEdit(); break;
    case 'qr': await loadQR(params.estimateId, params.profile); break;
  }
}

// ─── Setup UI ───────────────────────────────────────────────
function setupUI() {
  const roles = state.user.roles;
  const isMaster = hasRole(roles, 'master');

  // Show/hide tabs based on role
  if (isMaster) {
    document.getElementById('tab-estimates').classList.remove('hidden');
  }
}

// ─── Dashboard ──────────────────────────────────────────────
async function loadDashboard() {
  const data = await api('GET', '/dashboard');
  applyRoleContext(data);
  const roles = state.user.roles;
  const primaryRole = highestRole(roles);
  const isMaster = hasRole(roles, 'master');
  const isAdmin = hasRole(roles, 'admin');
  const isSenior = hasRole(roles, 'senior_master');

  document.getElementById('dash-name').textContent = `Привет, ${state.user.name}!`;

  const roleLabels = {
    product_owner: 'Product Owner', admin: 'Администратор',
    senior_master: 'Старший мастер', master: 'Мастер', client: 'Клиент',
  };
  document.getElementById('dash-subtitle').textContent =
    data.active_role_label || state.user.active_role_label || roleLabels[primaryRole] || primaryRole || '';

  // Stats
  const stats = [];
  if (isMaster) {
    stats.push({value: data.active_estimates || 0, label: 'Активных смет'});
    stats.push({value: money(data.total_earned || 0), label: 'Заработано'});
  }
  stats.push({value: data.active_orders || 0, label: 'Активных заказов'});
  if (data.pending_approvals) {
    stats.push({value: data.pending_approvals, label: 'Ожидают действия'});
  }
  if (data.unread_notifications) {
    stats.push({value: data.unread_notifications, label: 'Уведомлений'});
  }
  state.notifications.unreadCount = Number(data.unread_notifications || 0);
  setNotificationBadge(state.notifications.unreadCount);

  document.getElementById('dash-stats').innerHTML = stats.map(s => `
    <div class="stat-card">
      <div class="stat-value">${s.value}</div>
      <div class="stat-label">${s.label}</div>
    </div>
  `).join('');

  // Actions
  const actions = [];
  actions.push({
    icon: '🔍', color: 'blue', title: 'Быстрый поиск',
    desc: 'Найти работу за секунды', action: "navigate('search')",
  });
  actions.push({
    icon: '📋', color: 'green', title: 'Каталог работ',
    desc: 'Все услуги по категориям', action: "navigate('catalog')",
  });

  if (isMaster) {
    actions.push({
      icon: '📊', color: 'orange', title: 'Мои сметы',
      desc: 'Создать или просмотреть', action: "navigate('estimates')",
      badge: data.active_estimates || null,
    });
    actions.push({
      icon: '💰', color: 'purple', title: 'Доходы',
      desc: 'Статистика и выплаты', action: "navigate('earnings')",
    });
  }

  if (isSenior || isAdmin) {
    actions.push({
      icon: '✅', color: 'green', title: 'Согласования',
      desc: 'Скидки и запросы', action: "navigate('approvals')",
      badge: data.pending_approvals || null,
    });
  }

  if (isAdmin) {
    actions.push({
      icon: '📈', color: 'red', title: 'Аналитика',
      desc: 'Мониторинг платформы', action: "navigate('analytics')",
    });
  }

  actions.push({
    icon: '📝', color: 'blue', title: 'Заказы',
    desc: 'Отслеживание и история', action: "navigate('orders')",
    badge: data.active_orders || null,
  });
  actions.push({
    icon: '💡', color: 'orange', title: 'Предложения',
    desc: 'Идеи, боли и улучшения для разработчиков', action: "navigate('suggestions')",
  });

  document.getElementById('dash-actions').innerHTML = actions.map(a => `
    <div class="action-card" onclick="${a.action}">
      <div class="action-icon ${a.color}">${a.icon}</div>
      <div class="action-text">
        <div class="action-title">${a.title}</div>
        <div class="action-desc">${a.desc}</div>
      </div>
      ${a.badge ? `<div class="action-badge">${a.badge}</div>` : ''}
    </div>
  `).join('');
}

// ─── Search ─────────────────────────────────────────────────
function setupSearch() {
  const input = document.getElementById('search-input');
  input.addEventListener('input', () => {
    clearTimeout(state.searchDebounce);
    const q = input.value.trim();

    document.getElementById('search-clear').classList.toggle('hidden', q.length === 0);

    if (q.length < 2) {
      document.getElementById('search-results').innerHTML = '';
      document.getElementById('search-empty').classList.add('hidden');
      document.getElementById('search-hint').classList.toggle('hidden', q.length > 0);
      return;
    }

    document.getElementById('search-hint').classList.add('hidden');
    state.searchDebounce = setTimeout(() => doSearch(q), 200);
  });

  // Load popular tags
  loadPopularTags();
}

async function loadPopularTags() {
  try {
    const items = await api('GET', '/catalog/items?popular=true&limit=10');
    const tags = items.map(it => it.name.split(/\s+/).slice(0, 2).join(' '));
    const unique = [...new Set(tags)].slice(0, 8);
    document.getElementById('popular-tags').innerHTML = unique.map(t =>
      `<span class="tag" onclick="searchTag('${t}')">${t}</span>`
    ).join('');
  } catch (e) { /* ignore */ }
}

function searchTag(text) {
  document.getElementById('search-input').value = text;
  document.getElementById('search-input').dispatchEvent(new Event('input'));
}

async function doSearch(query) {
  try {
    const items = await api('GET', `/catalog/search?q=${encodeURIComponent(query)}`);
    const container = document.getElementById('search-results');
    const empty = document.getElementById('search-empty');

    if (items.length === 0) {
      container.innerHTML = '';
      empty.classList.remove('hidden');
      return;
    }
    empty.classList.add('hidden');
    container.innerHTML = items.map(it => itemRow(it)).join('');
  } catch (e) {
    console.error('Search error:', e);
  }
}

function clearSearch() {
  document.getElementById('search-input').value = '';
  document.getElementById('search-results').innerHTML = '';
  document.getElementById('search-empty').classList.add('hidden');
  document.getElementById('search-hint').classList.remove('hidden');
  document.getElementById('search-clear').classList.add('hidden');
}

// ─── Catalog ────────────────────────────────────────────────
async function loadCatalog(params = {}) {
  const container = document.getElementById('catalog-content');

  if (params.subgroupId) {
    // Show items in subgroup
    const items = await api('GET', `/catalog/items?subgroup_id=${params.subgroupId}`);
    container.innerHTML = `
      <p class="section-title">${params.title || 'Работы'}</p>
      <div class="item-list">${items.map(it => itemRow(it)).join('')}</div>
    `;
  } else if (params.groupId) {
    // Show subgroups or items
    const subs = await api('GET', `/catalog/subgroups/${params.groupId}`);
    if (subs.length > 0) {
      container.innerHTML = `
        <p class="section-title">${params.title || 'Подкатегории'}</p>
        <div class="catalog-grid">
          ${subs.map(s => `
            <div class="catalog-card" onclick="navigate('catalog', {groupId: ${params.groupId}, subgroupId: ${s.id}, title: '${esc(s.name)}'})">
              <div class="label">${s.name}</div>
              <div class="count">${s.count} работ</div>
            </div>
          `).join('')}
        </div>
        <p class="section-title mt-12">Все работы</p>
        <div class="item-list" id="group-items-${params.groupId}"></div>
      `;
      // Also load items
      const items = await api('GET', `/catalog/items?group_id=${params.groupId}`);
      document.getElementById(`group-items-${params.groupId}`).innerHTML = items.map(it => itemRow(it)).join('');
    } else {
      const items = await api('GET', `/catalog/items?group_id=${params.groupId}`);
      container.innerHTML = `
        <p class="section-title">${params.title || 'Работы'}</p>
        <div class="item-list">${items.map(it => itemRow(it)).join('')}</div>
      `;
    }
  } else if (params.professionId) {
    // Show groups
    const groups = await api('GET', `/catalog/groups/${params.professionId}`);
    container.innerHTML = `
      <p class="section-title">${params.title || 'Категории'}</p>
      <div class="catalog-grid">
        ${groups.map(g => `
          <div class="catalog-card" onclick="navigate('catalog', {professionId: ${params.professionId}, groupId: ${g.id}, title: '${esc(g.name)}'})">
            <div class="label">${g.name}</div>
            <div class="count">${g.count} работ</div>
          </div>
        `).join('')}
      </div>
    `;
  } else {
    // Show professions
    const profs = await api('GET', '/catalog/professions');
    container.innerHTML = `
      <div class="catalog-grid">
        ${profs.map(p => `
          <div class="catalog-card" onclick="navigate('catalog', {professionId: ${p.id}, title: '${esc(p.name)}'})">
            <div class="icon">${p.icon}</div>
            <div class="label">${p.name}</div>
            <div class="count">${p.count} работ</div>
          </div>
        `).join('')}
      </div>
      <div class="mt-12">
        <p class="section-title">Популярные работы</p>
        <div class="item-list" id="popular-items"></div>
      </div>
    `;
    // Load popular items
    const popular = await api('GET', '/catalog/items?popular=true&limit=10');
    document.getElementById('popular-items').innerHTML = popular.map(it => itemRow(it)).join('');
  }
}

// ─── Item Detail ────────────────────────────────────────────
async function loadItem(itemId) {
  const item = await api('GET', `/catalog/items/${itemId}`);
  const container = document.getElementById('item-detail');

  container.innerHTML = `
    <div class="card">
      <h3 style="font-size:17px;font-weight:700;margin-bottom:8px">${item.name}</h3>
      <div style="font-size:13px;color:var(--text-muted);margin-bottom:12px">
        <code>${item.code}</code> · ${item.unit}
        ${item.complexity ? ` · ${complexityLabel(item.complexity)}` : ''}
      </div>

      <div class="stat-grid" style="grid-template-columns:repeat(3,1fr);margin-bottom:12px">
        <div class="stat-card">
          <div class="stat-value" style="font-size:16px">${money(item.price_min)}</div>
          <div class="stat-label">Минимум</div>
        </div>
        <div class="stat-card">
          <div class="stat-value" style="font-size:16px">${money(item.price)}</div>
          <div class="stat-label">Рекоменд.</div>
        </div>
        <div class="stat-card">
          <div class="stat-value" style="font-size:16px">${money(item.price_max)}</div>
          <div class="stat-label">Максимум</div>
        </div>
      </div>

      ${item.description ? `<p style="font-size:14px;margin-bottom:8px">${item.description}</p>` : ''}
      ${item.note ? `<p style="font-size:13px;color:var(--text-muted)">📝 ${item.note}</p>` : ''}
      ${item.aliases ? `<p style="font-size:12px;color:var(--text-muted);margin-top:8px">🔍 ${item.aliases}</p>` : ''}
    </div>

    <button class="btn btn-primary btn-block" onclick="addToEstimate(${item.id}, '${esc(item.name)}')">
      ➕ Добавить в смету
    </button>
  `;
}

// ─── Estimates ──────────────────────────────────────────────
async function loadEstimates() {
  const estimates = await api('GET', '/estimates');
  const container = document.getElementById('estimates-list');

  if (estimates.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <p>У вас пока нет смет</p>
        <button class="btn btn-primary mt-12" onclick="createEstimate()">➕ Создать смету</button>
      </div>
    `;
    return;
  }

  const statusIcons = {draft:'📝', approved:'✅', client_review:'👁', paid:'💰', completed:'☑️', cancelled:'❌'};
  const statusLabels = {draft:'Черновик', approved:'Согласована', client_review:'На проверке', paid:'Оплачена', completed:'Завершена', cancelled:'Отменена', master_proposed:'Предложена', in_progress:'В работе'};

  container.innerHTML = `
    <button class="btn btn-primary btn-block mb-12" onclick="createEstimate()">➕ Новая смета</button>
    ${estimates.map(e => `
      <div class="estimate-row" onclick="navigate('estimate', {id: ${e.id}})">
        <div class="est-icon">${statusIcons[e.status] || '📋'}</div>
        <div class="est-info">
          <div class="est-title">Смета #${e.id} <span style="font-weight:400;color:var(--text-muted)">v${e.version}</span></div>
          <div class="est-meta">${statusLabels[e.status] || e.status}</div>
        </div>
        <div class="est-amount">${money(e.final)}</div>
      </div>
    `).join('')}
  `;
}

async function loadEstimate(estimateId) {
  if (!estimateId) return;
  state.activeEstimateId = estimateId;
  const est = await api('GET', `/estimates/${estimateId}`);
  renderEstimate(est);
}

function renderEstimate(est) {
  const container = document.getElementById('estimate-detail');
  const statusLabels = {draft:'Черновик', approved:'Согласована', client_review:'На проверке', paid:'Оплачена', completed:'Завершена', master_proposed:'Предложена', in_progress:'В работе'};
  const caps = est.capabilities || {};
  const isDraft = est.status === 'draft';
  const canEdit = Boolean(caps.can_edit);
  const canSendToClient = Boolean(caps.can_send_to_client);
  const canRequestDiscount = Boolean(caps.can_request_discount);
  const canClientRespond = Boolean(caps.can_client_respond);
  const canCreateOrder = Boolean(caps.can_create_order);
  const canExport = caps.can_export !== false;

  let itemsHtml = '';
  if (est.items.length === 0) {
    itemsHtml = `
      <div class="empty-state">
        <p>Смета пуста</p>
        <p class="text-muted">${canEdit ? 'Добавьте работы через поиск или каталог' : 'В смете пока нет позиций'}</p>
        ${canEdit ? `
        <div style="display:flex;gap:8px;justify-content:center;margin-top:12px">
          <button class="btn btn-primary btn-sm" onclick="navigate('search')">🔍 Поиск</button>
          <button class="btn btn-secondary btn-sm" onclick="navigate('catalog')">📋 Каталог</button>
        </div>
        ` : ''}
      </div>
    `;
  } else {
    itemsHtml = est.items.map((it, i) => `
      <div class="cart-item">
        <div class="cart-item-info">
          <div class="cart-item-name">${i+1}. ${it.name}</div>
          <div class="cart-item-meta">${it.unit} × ${money(it.unit_price)}${it.coefficients ? ' ' + Object.values(it.coefficients).map(v => '×'+v).join(' ') : ''}</div>
          <div class="cart-item-price">${money(it.subtotal)}</div>
        </div>
        ${isDraft && canEdit ? `
        <div class="cart-item-controls">
          <button class="qty-btn" onclick="changeQty(${est.id}, ${it.id}, ${it.quantity - 1})">−</button>
          <span class="qty-value">${it.quantity}</span>
          <button class="qty-btn" onclick="changeQty(${est.id}, ${it.id}, ${it.quantity + 1})">+</button>
          <button class="cart-item-delete" onclick="removeItem(${est.id}, ${it.id})">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>
          </button>
        </div>
        ` : `
        <div style="text-align:right">
          <div style="font-size:13px;color:var(--text-muted)">${it.quantity} ${it.unit}</div>
        </div>
        `}
      </div>
    `).join('');
  }

  let actionsHtml = '';
  if (isDraft && canEdit) {
    actionsHtml = `
      <div class="cart-actions">
        <button class="btn btn-primary" onclick="navigate('search')">➕ Добавить</button>
        ${canSendToClient ? `<button class="btn btn-secondary" onclick="sendToClient(${est.id})">📤 Клиенту</button>` : ''}
      </div>
      ${canRequestDiscount ? `
      <div class="cart-actions mt-8">
        <button class="btn btn-ghost btn-sm" onclick="requestDiscount(${est.id})">💸 Скидка</button>
      </div>
      ` : ''}
      <div class="cart-actions mt-8">
        <button class="btn btn-danger btn-block" onclick="deleteEstimate(${est.id}, ${est.items.length}, ${est.final})">
          ❌ Удалить смету
        </button>
      </div>
    `;
  } else if (est.status === 'client_review' && canClientRespond) {
    actionsHtml = `
      <div class="cart-actions">
        <button class="btn btn-primary" onclick="approveEstimate(${est.id})">✅ Согласовать</button>
        <button class="btn btn-danger" onclick="rejectEstimate(${est.id})">❌ Отклонить</button>
      </div>
    `;
  } else if (est.status === 'approved' && canCreateOrder) {
    actionsHtml = `
      <div class="cart-actions">
        <button class="btn btn-primary btn-block" onclick="createOrderFromEstimate(${est.id})">📝 Создать заказ</button>
      </div>
    `;
  }

  if (est.items.length > 0 && canExport) {
    actionsHtml += `
      <div class="export-bar mt-12">
        <div class="export-title">Выгрузить смету</div>
        <div class="export-buttons">
          <a class="btn btn-secondary btn-sm" href="${API}/estimates/${est.id}/export/pdf?tg_id=${state.user.telegram_id}" target="_blank">📄 PDF</a>
          <a class="btn btn-secondary btn-sm" href="${API}/estimates/${est.id}/export/xlsx?tg_id=${state.user.telegram_id}" target="_blank">📊 XLSX</a>
          <button class="btn btn-secondary btn-sm" onclick="navigate('qr', {estimateId: ${est.id}})">💳 QR оплата</button>
        </div>
      </div>
    `;
  }

  container.innerHTML = `
    <div class="cart-header">
      <h3>Смета #${est.id} <span style="font-weight:400;color:var(--text-muted)">v${est.version}</span></h3>
      <span class="cart-status ${est.status}">${statusLabels[est.status] || est.status}</span>
    </div>
    ${itemsHtml}
    <div class="cart-totals">
      <div class="cart-total-row">
        <span>Сумма</span>
        <span>${money(est.total)}</span>
      </div>
      ${est.discount > 0 ? `
      <div class="cart-total-row">
        <span>Скидка</span>
        <span class="discount">−${money(est.discount)}</span>
      </div>
      ` : ''}
      <div class="cart-total-row final">
        <span>Итого</span>
        <span class="text-accent">${money(est.final)}</span>
      </div>
    </div>
    ${actionsHtml}
  `;

  // Update FAB
  state.cartItems = est.items.length;
  updateFAB();
}

// ─── Estimate Actions ───────────────────────────────────────
async function createEstimate() {
  try {
    const est = await api('POST', '/estimates');
    state.activeEstimateId = est.id;
    toast('Смета создана');
    navigate('estimate', {id: est.id});
  } catch (e) { toast(e.message, true); }
}

async function addToEstimate(serviceItemId, itemName) {
  try {
    // Find or create draft estimate
    if (!state.activeEstimateId) {
      const est = await api('POST', '/estimates');
      state.activeEstimateId = est.id;
    }
    await api('POST', `/estimates/${state.activeEstimateId}/items`, {
      service_item_id: serviceItemId, quantity: 1,
    });
    toast(`✅ ${itemName} → смета`);

    // Update cart count
    const est = await api('GET', `/estimates/${state.activeEstimateId}`);
    state.cartItems = est.items.length;
    updateFAB();
  } catch (e) { toast(e.message, true); }
}

async function changeQty(estimateId, lineItemId, newQty) {
  if (newQty < 1) return removeItem(estimateId, lineItemId);
  try {
    await api('PATCH', `/estimates/${estimateId}/items/${lineItemId}`, {quantity: newQty});
    await loadEstimate(estimateId);
  } catch (e) { toast(e.message, true); }
}

async function removeItem(estimateId, lineItemId) {
  try {
    await api('DELETE', `/estimates/${estimateId}/items/${lineItemId}`);
    toast('Удалено');
    await loadEstimate(estimateId);
  } catch (e) { toast(e.message, true); }
}

async function deleteEstimate(estimateId, itemCount, finalAmount) {
  const confirmed = await confirmAction(
    `Удалить смету #${estimateId}?\nПозиций: ${itemCount}\nИтого: ${money(finalAmount)}\n\nДействие необратимо.`
  );
  if (!confirmed) return;

  try {
    await api('DELETE', `/estimates/${estimateId}`);
    if (state.activeEstimateId === estimateId) {
      state.activeEstimateId = null;
      state.cartItems = 0;
      updateFAB();
    }
    toast('Смета удалена');
    navigate('estimates');
  } catch (e) { toast(e.message, true); }
}

async function sendToClient(estimateId) {
  // For now, just change status to client_review
  try {
    await api('POST', `/estimates/${estimateId}/status`, {status: 'client_review'});
    toast('📤 Смета отправлена клиенту');
    await loadEstimate(estimateId);
  } catch (e) { toast(e.message, true); }
}

async function approveEstimate(estimateId) {
  try {
    await api('POST', `/estimates/${estimateId}/status`, {status: 'approved'});
    toast('✅ Смета согласована');
    await loadEstimate(estimateId);
  } catch (e) { toast(e.message, true); }
}

async function rejectEstimate(estimateId) {
  try {
    await api('POST', `/estimates/${estimateId}/status`, {status: 'draft'});
    toast('Смета отклонена');
    await loadEstimate(estimateId);
  } catch (e) { toast(e.message, true); }
}

function requestDiscount(estimateId) {
  const input = prompt('Процент скидки\nВведите только число, например: 10 или 12.5');
  if (!input) return;
  const value = parseFloat(input.trim().replace('%', '').replace(',', '.'));
  if (!Number.isFinite(value)) {
    toast('Укажите только процент скидки', true);
    return;
  }
  if (value <= 0 || value > 50) {
    toast('Скидка должна быть больше 0% и не превышать 50%', true);
    return;
  }

  api('POST', `/estimates/${estimateId}/discount`, {
    value,
  }).then(() => toast(`Скидка обновлена до ${formatPercent(value)}`))
    .catch(e => toast(e.message, true));
}

// ─── Orders ─────────────────────────────────────────────────
async function loadOrders() {
  const orders = await api('GET', '/orders');
  const container = document.getElementById('orders-list');

  if (orders.length === 0) {
    container.innerHTML = '<div class="empty-state"><p>Заказов пока нет</p></div>';
    return;
  }

  const statusIcons = {draft:'📝', submitted:'📤', assigned:'👷', in_progress:'🔨', completed:'✅', paid:'💰', cancelled:'❌'};
  const statusLabels = {draft:'Черновик', submitted:'Отправлен', assigned:'Назначен', in_progress:'В работе', completed:'Завершён', paid:'Оплачен', cancelled:'Отменён'};

  container.innerHTML = orders.map(o => `
    <div class="order-row" onclick="navigate('order', {id: ${o.id}})">
      <div style="font-size:24px">${statusIcons[o.status] || '📋'}</div>
      <div style="flex:1">
        <div style="font-weight:600">Заказ #${o.id}</div>
        <div style="font-size:12px;color:var(--text-muted)">${statusLabels[o.status] || o.status}${o.address ? ' · ' + o.address.substring(0,25) : ''}</div>
      </div>
    </div>
  `).join('');
}

async function loadOrder(orderId) {
  const order = await api('GET', `/orders/${orderId}`);
  const container = document.getElementById('order-detail');
  const caps = order.capabilities || {};

  const statusIcons = {draft:'📝', submitted:'📤', assigned:'👷', in_progress:'🔨', completed:'✅', paid:'💰', cancelled:'❌'};
  const statusLabels = {draft:'Черновик', submitted:'Отправлен', assigned:'Назначен', in_progress:'В работе', completed:'Завершён', paid:'Оплачен', cancelled:'Отменён'};
  const urgencyLabels = {normal:'Обычная', urgent:'Срочная', emergency:'Экстренная'};

  // Estimate items section
  let itemsHtml = '';
  if (order.estimate) {
    itemsHtml = `
      <div class="card mt-12">
        <div class="card-title">Состав работ (v${order.estimate.version})</div>
        ${order.estimate.items.map((it, i) => `
          <div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border);font-size:14px">
            <span>${i+1}. ${it.name} × ${it.quantity}</span>
            <span style="white-space:nowrap">${money(it.subtotal)}</span>
          </div>
        `).join('')}
        <div style="display:flex;justify-content:space-between;padding:8px 0;font-weight:700;font-size:15px">
          <span>Итого</span>
          <span class="text-accent">${money(order.estimate.final)}</span>
        </div>
      </div>
    `;
  }

  // Status history timeline
  let historyHtml = '';
  if (order.history && order.history.length > 0) {
    historyHtml = `
      <div class="card mt-12">
        <div class="card-title">История</div>
        <div class="timeline">
          ${order.history.map(h => `
            <div class="timeline-item">
              <div class="timeline-dot"></div>
              <div class="timeline-content">
                <span class="timeline-status">${statusLabels[h.to] || h.to}</span>
                <span class="timeline-time">${h.at ? new Date(h.at).toLocaleString('ru-RU', {day:'numeric', month:'short', hour:'2-digit', minute:'2-digit'}) : ''}</span>
              </div>
            </div>
          `).join('')}
        </div>
      </div>
    `;
  }

  // Actions based on status
  let actionsHtml = '';
  if (caps.can_submit) {
    actionsHtml = `<button class="btn btn-primary btn-block" onclick="updateOrderStatus(${order.id}, 'submitted')">📤 Отправить заказ</button>`;
  } else if (caps.can_assign) {
    actionsHtml = `<button class="btn btn-primary btn-block" onclick="assignOrder(${order.id})">✋ Взять заказ</button>`;
  } else if (caps.can_start) {
    actionsHtml = `<button class="btn btn-primary btn-block" onclick="updateOrderStatus(${order.id}, 'in_progress')">🔨 Начать работу</button>`;
  } else if (caps.can_complete) {
    actionsHtml = `<button class="btn btn-primary btn-block" onclick="updateOrderStatus(${order.id}, 'completed')">✅ Завершить</button>`;
  } else if (caps.can_pay) {
    actionsHtml = `<button class="btn btn-primary btn-block" onclick="showPayment(${order.id})">💳 Оплатить</button>`;
  }

  if (caps.can_cancel) {
    actionsHtml += `<button class="btn btn-ghost btn-block mt-8" onclick="updateOrderStatus(${order.id}, 'cancelled')">Отменить заказ</button>`;
  }

  container.innerHTML = `
    <div class="card">
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">
        <div style="font-size:32px">${statusIcons[order.status] || '📋'}</div>
        <div>
          <h3 style="font-size:17px;font-weight:700">Заказ #${order.id}</h3>
          <span class="cart-status ${order.status}">${statusLabels[order.status] || order.status}</span>
        </div>
      </div>
      <div class="order-meta">
        ${order.address ? `<div class="meta-row"><span class="meta-icon">📍</span> ${order.address}</div>` : ''}
        <div class="meta-row"><span class="meta-icon">⚡</span> ${urgencyLabels[order.urgency] || order.urgency}</div>
        ${order.client_name ? `<div class="meta-row"><span class="meta-icon">👤</span> Клиент: ${order.client_name}</div>` : ''}
        ${order.master_name ? `<div class="meta-row"><span class="meta-icon">🔧</span> Мастер: ${order.master_name}</div>` : ''}
        ${order.notes ? `<div class="meta-row"><span class="meta-icon">📝</span> ${order.notes}</div>` : ''}
        ${order.payment_status ? `<div class="meta-row"><span class="meta-icon">💳</span> Оплата: ${order.payment_status}</div>` : ''}
      </div>
    </div>
    ${itemsHtml}
    ${historyHtml}
    <div class="mt-12">${actionsHtml}</div>
  `;
}

async function updateOrderStatus(orderId, status) {
  try {
    await api('POST', `/orders/${orderId}/status`, {status});
    toast('Статус обновлён');
    await loadOrder(orderId);
  } catch (e) { toast(e.message, true); }
}

async function assignOrder(orderId) {
  try {
    await api('POST', `/orders/${orderId}/assign-self`);
    toast('Заказ назначен вам');
    await loadOrder(orderId);
  } catch (e) { toast(e.message, true); }
}

async function showPayment(orderId) {
  try {
    const info = await api('GET', `/orders/${orderId}/payment`);
    const container = document.getElementById('order-detail');
    container.innerHTML += `
      <div class="card mt-12 payment-card">
        <div class="card-title">💳 Оплата</div>
        <div class="payment-amount">${money(info.amount)}</div>
        ${info.recipient ? `<div class="meta-row">Получатель: ${info.recipient}</div>` : ''}
        ${info.bank_name ? `<div class="meta-row">Банк: ${info.bank_name}</div>` : ''}
        ${info.phone ? `<div class="meta-row">Телефон: ${info.phone}</div>` : ''}
        ${info.qr_data ? `<div class="meta-row" style="margin-top:8px;font-size:12px;color:var(--text-muted)">QR-данные: ${info.qr_data}</div>` : ''}
      </div>
    `;
  } catch (e) { toast(e.message, true); }
}

async function createOrderFromEstimate(estimateId) {
  const address = prompt('Адрес выполнения работ:');
  if (!address) return;
  try {
    const order = await api('POST', '/orders', {
      estimate_id: estimateId, address, urgency: 'normal',
    });
    toast(`Заказ #${order.id} создан`);
    navigate('orders');
  } catch (e) { toast(e.message, true); }
}

// ─── Earnings ───────────────────────────────────────────────
async function loadEarnings() {
  const data = await api('GET', '/earnings');
  document.getElementById('earnings-content').innerHTML = `
    <div class="earning-stat">
      <div class="earning-value">${money(data.total_earned)}</div>
      <div class="earning-label">Общий заработок</div>
    </div>
    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-value" style="font-size:18px">${data.completed}</div>
        <div class="stat-label">Выполнено заказов</div>
      </div>
      <div class="stat-card">
        <div class="stat-value" style="font-size:18px">${money(data.pending)}</div>
        <div class="stat-label">Ожидает оплаты</div>
      </div>
    </div>
    <div class="card mt-12">
      <div class="card-title">Комиссия платформы</div>
      <p style="font-size:14px;color:var(--text-muted);margin-top:4px">${money(data.commission_paid)}</p>
    </div>
  `;
}

// ─── Approvals ──────────────────────────────────────────────
async function loadApprovals() {
  const items = await api('GET', '/approvals');
  const container = document.getElementById('approvals-list');

  if (items.length === 0) {
    container.innerHTML = '<div class="empty-state"><p>Нет ожидающих согласований</p></div>';
    return;
  }

  container.innerHTML = items.map(dr => `
    <div class="card">
      <div class="card-header">
        <div>
          <div class="card-title">Смета #${dr.estimate_id}</div>
          <div class="card-subtitle">${dr.type === 'percent' ? dr.value + '%' : money(dr.value)}</div>
        </div>
      </div>
      <div style="display:flex;gap:8px">
        <button class="btn btn-primary btn-sm flex-1" onclick="processApproval(${dr.id}, 'approve')">✅ Одобрить</button>
        <button class="btn btn-danger btn-sm flex-1" onclick="processApproval(${dr.id}, 'reject')">❌ Отклонить</button>
      </div>
    </div>
  `).join('');
}

async function processApproval(requestId, action) {
  try {
    await api('POST', `/approvals/${requestId}`, {action});
    toast(action === 'approve' ? '✅ Одобрено' : '❌ Отклонено');
    await loadApprovals();
  } catch (e) { toast(e.message, true); }
}

// ─── Suggestions ────────────────────────────────────────────
async function loadSuggestionsComposer() {
  const container = document.getElementById('suggestions-content');
  container.innerHTML = `
    <div class="card suggestion-card">
      <div class="card-title">💡 Предложить улучшение</div>
      <div class="card-subtitle">
        Напишите одним сообщением идею, проблему или неудобство.
        Текст сохранится и уйдёт разработчикам во внутренние уведомления.
      </div>
      <div class="form-group mt-12">
        <label class="form-label" for="suggestion-message">Текст предложения</label>
        <textarea
          id="suggestion-message"
          class="form-input suggestion-textarea"
          placeholder="Например: в экране сметы не хватает быстрой кнопки дублирования, из-за этого мы теряем время на повторной сборке..."
          oninput="updateSuggestionCounter()"
        ></textarea>
        <div class="suggestion-meta">
          <span class="text-muted">Минимум 10 символов, можно писать в свободной форме.</span>
          <span id="suggestion-counter" class="suggestion-counter">0/1500</span>
        </div>
      </div>
      <div class="suggestion-hints">
        <div class="suggestion-hint"><strong>Что не так?</strong> Где и какой именно сценарий неудобен.</div>
        <div class="suggestion-hint"><strong>Что нужно?</strong> Какой результат был бы полезен.</div>
        <div class="suggestion-hint"><strong>Что сломано?</strong> Если это баг, коротко опишите шаги и эффект.</div>
      </div>
      <button id="suggestion-submit" class="btn btn-primary btn-block mt-12" onclick="submitSuggestion()">
        Отправить разработчикам
      </button>
    </div>
  `;
  updateSuggestionCounter();
}

function updateSuggestionCounter() {
  const input = document.getElementById('suggestion-message');
  const counter = document.getElementById('suggestion-counter');
  if (!input || !counter) return;

  const length = input.value.trim().length;
  counter.textContent = `${length}/1500`;
  counter.classList.toggle('text-accent', length >= 10 && length <= 1500);
}

async function submitSuggestion() {
  const input = document.getElementById('suggestion-message');
  const button = document.getElementById('suggestion-submit');
  if (!input || !button) return;

  const message = input.value.trim();
  if (message.length < 10) {
    toast('Опишите предложение чуть подробнее', true);
    return;
  }

  button.disabled = true;
  try {
    const payload = await api('POST', '/suggestions', {message});
    input.value = '';
    updateSuggestionCounter();
    const deliveredText = payload.recipient_count
      ? `Предложение #${payload.id} отправлено`
      : `Предложение #${payload.id} сохранено`;
    toast(deliveredText);
  } catch (e) {
    toast(e.message, true);
  } finally {
    button.disabled = false;
  }
}

// ─── Analytics ──────────────────────────────────────────────
async function loadAnalytics() {
  try {
    const data = await api('GET', '/analytics/overview');
    const container = document.getElementById('analytics-content');

    const funnel = data.funnel || {};
    const maxFunnel = Math.max(...Object.values(funnel), 1);

    container.innerHTML = `
      <div class="stat-grid">
        <div class="stat-card"><div class="stat-value">${data.users}</div><div class="stat-label">Пользователей</div></div>
        <div class="stat-card"><div class="stat-value">${data.masters}</div><div class="stat-label">Мастеров</div></div>
        <div class="stat-card"><div class="stat-value">${data.estimates}</div><div class="stat-label">Смет</div></div>
        <div class="stat-card"><div class="stat-value">${data.orders}</div><div class="stat-label">Заказов</div></div>
      </div>

      <div class="analytics-card">
        <h3 style="font-size:15px;font-weight:600;margin-bottom:12px">💰 Финансы</h3>
        <div class="cart-total-row"><span>Оборот</span><span class="font-bold">${money(data.gross)}</span></div>
        <div class="cart-total-row"><span>Комиссия</span><span class="font-bold">${money(data.platform_fee)}</span></div>
        <div class="cart-total-row"><span>  Ст. мастерам</span><span>${money(data.senior_share)}</span></div>
        <div class="cart-total-row"><span>  Админам</span><span>${money(data.admin_share)}</span></div>
        <div class="cart-total-row final"><span>Чистая прибыль</span><span class="text-accent">${money(data.platform_net)}</span></div>
      </div>

      <div class="analytics-card">
        <h3 style="font-size:15px;font-weight:600;margin-bottom:12px">📊 Воронка заказов</h3>
        ${['draft','submitted','assigned','in_progress','completed','paid','cancelled'].map(s => {
          const labels = {draft:'Черновики', submitted:'Отправлены', assigned:'Назначены', in_progress:'В работе', completed:'Завершены', paid:'Оплачены', cancelled:'Отменены'};
          const v = funnel[s] || 0;
          const pct = Math.round(v / maxFunnel * 100);
          return `
            <div class="funnel-row">
              <span class="funnel-label">${labels[s]}</span>
              <div style="flex:2;padding:0 8px"><div class="funnel-bar" style="width:${pct}%"></div></div>
              <span class="funnel-value">${v}</span>
            </div>
          `;
        }).join('')}
      </div>
    `;
  } catch (e) { toast(e.message, true); }
}

// ─── Profile ────────────────────────────────────────────────
function loadProfile() {
  const u = state.user;
  const primaryRole = highestRole(u.roles);
  const roleLabels = {
    product_owner: '🏢 Product Owner', admin: '⚙️ Администратор',
    senior_master: '👨‍🔧 Старший мастер', master: '🔧 Мастер', client: '👤 Клиент',
  };

  const isMaster = hasRole(u.roles, 'master');
  const isAdmin = hasRole(u.roles, 'admin');
  const activeRoleLabel = u.active_role_label || roleLabels[primaryRole] || primaryRole || '';
  const maxRoleLabel = u.max_role_label || activeRoleLabel;

  let menuItems = '';
  menuItems += profileItem('👤', 'Личные данные и реквизиты', "navigate('profile-edit')");
  if (isMaster) {
    menuItems += profileItem('🏦', 'Мои реквизиты и QR', "navigate('qr', {profile: 1})");
    menuItems += profileItem('💰', 'Доходы', "navigate('earnings')");
    menuItems += profileItem('📊', 'Мои сметы', "navigate('estimates')");
  }
  menuItems += profileItem('📝', 'Мои заказы', "navigate('orders')");
  menuItems += profileItem('💡', 'Предложения', "navigate('suggestions')");
  if (isAdmin) {
    menuItems += profileItem('📈', 'Аналитика', "navigate('analytics')");
    menuItems += profileItem('✅', 'Согласования', "navigate('approvals')");
  }

  const roleContext = u.can_switch_role ? `
    <div class="card profile-context">
      <div class="card-title">🎭 Режим роли</div>
      <div class="profile-meta"><span>Сейчас</span><strong>${activeRoleLabel}</strong></div>
      <div class="profile-meta"><span>Максимум</span><strong>${maxRoleLabel}</strong></div>
      ${u.is_role_switched ? '<div class="profile-note">Включен временный тестовый контур прав. Прямые роли в базе не меняются.</div>' : ''}
      <div class="role-switcher">
        <button class="role-chip ${!u.role_override ? 'active' : ''}" onclick="setRoleMode(null)">Авто</button>
        ${(u.available_roles || []).map(role => `
          <button
            class="role-chip ${u.active_role === role.code ? 'active' : ''}"
            onclick="setRoleMode('${role.code}')"
          >${role.label}</button>
        `).join('')}
      </div>
    </div>
  ` : '';

  document.getElementById('profile-content').innerHTML = `
    <div class="profile-header">
      <div class="profile-avatar">${u.name[0]}</div>
      <div class="profile-name">${u.name}</div>
      <div class="profile-roles">${activeRoleLabel}</div>
      ${u.is_role_switched ? `<div class="profile-roles">Максимальная роль: ${maxRoleLabel}</div>` : ''}
    </div>
    ${roleContext}
    <div class="profile-menu">
      ${menuItems}
    </div>
  `;
}

function profileItem(icon, label, action) {
  return `
    <div class="profile-item" onclick="${action}">
      <span class="icon">${icon}</span>
      <span class="label">${label}</span>
      <svg class="chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 18l6-6-6-6"/></svg>
    </div>
  `;
}

async function setRoleMode(roleCode) {
  try {
    const payload = await api('PUT', '/profile/role-mode', {role_code: roleCode});
    applyRoleContext(payload);
    setupUI();
    if (state.screen === 'dashboard') {
      await loadDashboard();
    } else {
      loadProfile();
    }
    toast(`Режим: ${payload.active_role_label}`);
  } catch (e) {
    toast(e.message, true);
  }
}

// ─── Profile Editor ─────────────────────────────────────────
async function loadProfileEdit() {
  let p;
  try {
    p = await api('GET', '/profile');
  } catch (e) {
    p = {full_name:'', phone:'', email:'', telegram_username:'', company_name:'', inn:'', address:'', specialization:'', bank_name:'', bik:'', correspondent_account:'', settlement_account:'', card_number:'', sbp_phone:'', payment_recipient:''};
  }

  const container = document.getElementById('profile-edit-content');
  container.innerHTML = `
    <div class="card">
      <div class="card-title">👤 Личные данные</div>
      <p style="font-size:12px;color:var(--text-muted);margin-bottom:12px">Эти данные используются в шапке смет (PDF/XLSX)</p>
      ${formField('pe-full_name', 'ФИО', p.full_name, 'Иванов Иван Иванович')}
      ${formField('pe-phone', 'Телефон', p.phone, '+7 999 123-45-67')}
      ${formField('pe-email', 'Email', p.email, 'master@mail.ru')}
      ${formField('pe-telegram_username', 'Telegram', p.telegram_username, '@username')}
      ${formField('pe-company_name', 'Компания / ИП', p.company_name, 'ИП Иванов И.И.')}
      ${formField('pe-inn', 'ИНН', p.inn, '123456789012')}
      ${formField('pe-address', 'Адрес', p.address, 'г. Стерлитамак, ул. ...')}
      ${formField('pe-specialization', 'Специализация', p.specialization, 'Электрик, Сантехник')}
    </div>

    <div class="card mt-12">
      <div class="card-title">🏦 Банковские реквизиты</div>
      <p style="font-size:12px;color:var(--text-muted);margin-bottom:12px">Для QR-кода оплаты и реквизитов в смете</p>
      ${formField('pe-payment_recipient', 'Получатель платежа', p.payment_recipient, 'ИП Иванов Иван Иванович')}
      ${formField('pe-bank_name', 'Банк', p.bank_name, 'Сбербанк')}
      ${formField('pe-settlement_account', 'Расчётный счёт', p.settlement_account, '40802810...')}
      ${formField('pe-correspondent_account', 'Корр. счёт', p.correspondent_account, '30101810...')}
      ${formField('pe-bik', 'БИК', p.bik, '042202603')}
      ${formField('pe-card_number', 'Номер карты', p.card_number, '2202 **** **** 1234')}
      ${formField('pe-sbp_phone', 'Телефон СБП', p.sbp_phone, '+7 999 123-45-67')}
    </div>

    <button class="btn btn-primary btn-block mt-12" onclick="saveProfile()">💾 Сохранить</button>
  `;
}

function formField(id, label, value, placeholder) {
  return `
    <div class="form-group">
      <label class="form-label" for="${id}">${label}</label>
      <input class="form-input" id="${id}" type="text" value="${esc(value || '')}" placeholder="${placeholder}">
    </div>
  `;
}

async function saveProfile() {
  const fields = ['full_name','phone','email','telegram_username','company_name','inn','address','specialization','payment_recipient','bank_name','settlement_account','correspondent_account','bik','card_number','sbp_phone'];
  const data = {};
  for (const f of fields) {
    data[f] = document.getElementById('pe-' + f).value.trim();
  }
  try {
    await api('PUT', '/profile', data);
    toast('Данные сохранены');
  } catch (e) { toast(e.message, true); }
}

// ─── QR Payment Viewer ─────────────────────────────────────
async function loadQR(estimateId, profileMode = false) {
  const container = document.getElementById('qr-content');

  try {
    const data = profileMode
      ? await api('GET', '/profile/payment-qr')
      : await api('GET', `/estimates/${estimateId}/qr`);

    const title = profileMode ? 'Мои реквизиты' : `Оплата по смете #${estimateId}`;
    const subtitle = profileMode
      ? 'QR без суммы: сумму можно ввести вручную в банковском приложении'
      : `Оплата по смете #${estimateId}`;
    const amountHtml = data.amount ? `<div class="qr-amount">${money(data.amount)}</div>` : '';
    const missingFields = Array.isArray(data.missing_bank_fields) ? data.missing_bank_fields : [];

    container.innerHTML = `
      <div class="qr-viewer">
        ${amountHtml}
        <div class="qr-label">${subtitle}</div>

        ${data.qr_image ? `
          <div class="qr-image-wrap">
            <img src="data:image/png;base64,${data.qr_image}" alt="QR код для оплаты" class="qr-image">
          </div>
          <div class="qr-hint">Отсканируйте QR-код в приложении банка</div>
        ` : ''}

        <div class="card mt-12">
          <div class="card-title">${title}</div>
          ${data.recipient ? payRow('Получатель', data.recipient) : ''}
          ${data.bank ? payRow('Банк', data.bank) : ''}
          ${data.account ? payRow('Р/с', data.account, true) : ''}
          ${data.correspondent_account ? payRow('Корр. счет', data.correspondent_account, true) : ''}
          ${data.bik ? payRow('БИК', data.bik, true) : ''}
          ${data.inn ? payRow('ИНН', data.inn, true) : ''}
          ${data.card ? payRow('Карта', data.card, true) : ''}
          ${data.sbp_phone ? payRow('СБП (телефон)', data.sbp_phone, true) : ''}
        </div>

        ${missingFields.length ? `
          <div class="card mt-12">
            <div class="card-title">Что нужно заполнить для банковского QR</div>
            <div class="text-muted">${missingFields.join(', ')}</div>
          </div>
        ` : ''}

        ${data.sbp_phone ? `
          <div class="sbp-section mt-12">
            <div class="sbp-label">Перевод по СБП</div>
            <div class="sbp-phone" onclick="copyToClipboard('${data.sbp_phone}')">${data.sbp_phone} <span class="copy-icon">📋</span></div>
            <div class="sbp-hint">Нажмите, чтобы скопировать номер</div>
          </div>
        ` : ''}
      </div>
    `;
  } catch (e) {
    container.innerHTML = `
      <div class="empty-state">
        <p>${e.message || 'Ошибка загрузки QR-кода'}</p>
        <p class="text-muted">Убедитесь, что заполнены банковские реквизиты мастера</p>
        <button class="btn btn-primary mt-12" onclick="navigate('profile-edit')">Заполнить реквизиты</button>
      </div>
    `;
  }
}

function payRow(label, value, copyable) {
  if (!value) return '';
  const onclick = copyable ? `onclick="copyToClipboard('${esc(value)}')"` : '';
  return `
    <div class="pay-row" ${onclick}>
      <span class="pay-label">${label}</span>
      <span class="pay-value">${value}${copyable ? ' <span class="copy-icon">📋</span>' : ''}</span>
    </div>
  `;
}

function copyToClipboard(text) {
  navigator.clipboard.writeText(text).then(() => toast('Скопировано'))
    .catch(() => {
      // Fallback for older browsers
      const ta = document.createElement('textarea');
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      toast('Скопировано');
    });
}

// ─── Notifications ──────────────────────────────────────────
async function showNotifications() {
  navigate('notifications');
}

async function loadNotificationsPage(page) {
  state.notifications.page = Math.max(1, Number(page || 1));
  state.notifications.selectedId = null;
  await loadNotifications();
}

async function loadNotifications() {
  const container = document.getElementById('notifications-list');
  const page = Math.max(1, Number(state.notifications.page || 1));
  const offset = (page - 1) * state.notifications.pageSize;

  container.innerHTML = `
    <div class="card">
      <div class="card-title">Загружаем уведомления...</div>
      <div class="card-subtitle">Подтягиваем текущую страницу и историю.</div>
    </div>
  `;

  try {
    const raw = await api('GET', `/notifications?limit=${state.notifications.pageSize + 1}&offset=${offset}`);
    state.notifications.page = page;
    state.notifications.hasMore = raw.length > state.notifications.pageSize;
    state.notifications.items = raw.slice(0, state.notifications.pageSize);

    if (!state.notifications.items.some(item => item.id === state.notifications.selectedId)) {
      state.notifications.selectedId = null;
    }

    renderNotifications();
  } catch (e) {
    container.innerHTML = `
      <div class="card">
        <div class="card-title">Не удалось загрузить уведомления</div>
        <div class="card-subtitle">${escapeHtml(e.message || 'Попробуйте ещё раз')}</div>
        <button class="btn btn-primary mt-12" onclick="loadNotifications()">
          Обновить
        </button>
      </div>
    `;
    toast(e.message, true);
  }
}

async function openNotification(notifId) {
  const notification = state.notifications.items.find(item => item.id === notifId);
  if (!notification) return;

  state.notifications.selectedId = notifId;
  if (notification.is_unread) {
    try {
      await api('POST', `/notifications/${notifId}/read`);
      notification.is_unread = false;
      notification.status = 'read';
      state.notifications.unreadCount = Math.max(0, Number(state.notifications.unreadCount || 0) - 1);
      setNotificationBadge(state.notifications.unreadCount);
    } catch (e) {
      console.warn('Failed to mark notification as read', e);
    }
  }

  renderNotifications();
}

function closeNotificationDetail() {
  state.notifications.selectedId = null;
  renderNotifications();
}

function canOpenNotificationTarget(notification) {
  if (!notification) return false;
  if (notification.entity_type === 'estimate' && notification.entity_id) return true;
  if (notification.entity_type === 'order' && notification.entity_id) return true;
  if (notification.entity_type === 'discount_request' || notification.event_type === 'discount.requested') return true;
  return false;
}

function openNotificationTarget() {
  const notification = state.notifications.items.find(item => item.id === state.notifications.selectedId);
  if (!notification) return;

  if (notification.entity_type === 'estimate' && notification.entity_id) {
    navigate('estimate', {id: notification.entity_id});
  } else if (notification.entity_type === 'order' && notification.entity_id) {
    navigate('order', {id: notification.entity_id});
  } else if (notification.entity_type === 'discount_request' || notification.event_type === 'discount.requested') {
    navigate('approvals');
  } else {
    toast('Для этого уведомления нет отдельного экрана', true);
  }
}

function renderNotifications() {
  const container = document.getElementById('notifications-list');
  const notification = state.notifications.items.find(item => item.id === state.notifications.selectedId) || null;

  if (notification) {
    container.innerHTML = renderNotificationDetail(notification);
    return;
  }

  const pageStart = ((state.notifications.page - 1) * state.notifications.pageSize) + 1;
  const pageEnd = pageStart + Math.max(state.notifications.items.length - 1, 0);
  const unreadCount = Number(state.notifications.unreadCount || 0);

  if (state.notifications.items.length === 0) {
    container.innerHTML = `
      <div class="card notif-summary-card">
        <div class="notif-summary-top">
          <div>
            <div class="card-title">Журнал уведомлений</div>
            <div class="card-subtitle">Здесь сохраняется вся история, ничего не пропадает.</div>
          </div>
          <div class="notif-summary-count">${unreadCount}</div>
        </div>
      </div>
      <div class="empty-state card">
        <p>Уведомлений пока нет</p>
        <p class="text-muted">Когда появятся события, они останутся в этом журнале.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = `
    <div class="card notif-summary-card">
      <div class="notif-summary-top">
        <div>
          <div class="card-title">Журнал уведомлений</div>
          <div class="card-subtitle">
            Записи ${pageStart}-${pageEnd}. Непрочитанных: ${unreadCount}.
          </div>
        </div>
        <div class="notif-summary-count">${unreadCount}</div>
      </div>
      <div class="notif-page-hint">
        Страница ${state.notifications.page}${state.notifications.hasMore ? ' • доступны более ранние уведомления' : ''}
      </div>
    </div>
    <div class="notif-list">
      ${state.notifications.items.map(n => `
        <div class="notif-row ${n.is_unread ? 'unread' : ''}" onclick="openNotification(${n.id})">
          <div class="notif-icon">${notificationIcon(n.event_type)}</div>
          <div class="notif-body">
            <div class="notif-title">${escapeHtml(n.title || 'Уведомление')}</div>
            <div class="notif-text">${escapeHtml(n.body || '')}</div>
            <div class="notif-time">${formatNotificationListTime(n.created_at)}</div>
          </div>
          ${n.is_unread ? '<div class="notif-dot"></div>' : ''}
        </div>
      `).join('')}
    </div>
    <div class="pager">
      <button
        class="btn btn-secondary btn-sm"
        onclick="loadNotificationsPage(${state.notifications.page - 1})"
        ${state.notifications.page === 1 ? 'disabled' : ''}
      >
        ← Новее
      </button>
      <div class="pager-label">Страница ${state.notifications.page}</div>
      <button
        class="btn btn-secondary btn-sm"
        onclick="loadNotificationsPage(${state.notifications.page + 1})"
        ${!state.notifications.hasMore ? 'disabled' : ''}
      >
        Старее →
      </button>
    </div>
  `;
}

function renderNotificationDetail(notification) {
  const canOpenTarget = canOpenNotificationTarget(notification);
  const bodyHtml = escapeHtml(notification.body || '').replace(/\n/g, '<br>');

  return `
    <div class="card notif-detail-card">
      <div class="notif-detail-meta">
        <span class="notif-chip ${notification.is_unread ? 'unread' : 'read'}">
          ${notification.is_unread ? 'Новое' : 'Просмотрено'}
        </span>
        <span class="notif-chip">${formatNotificationDetailTime(notification.created_at)}</span>
        <span class="notif-chip">${escapeHtml(notification.event_type || 'event')}</span>
      </div>
      <div class="notif-detail-title">${escapeHtml(notification.title || 'Уведомление')}</div>
      <div class="notif-detail-body">${bodyHtml || 'Без дополнительного текста'}</div>
      ${canOpenTarget ? `
      <div class="notif-target-box">
        <div class="notif-target-label">Связанное действие</div>
        <div class="notif-target-value">${escapeHtml(notification.target_label || 'Открыть связанную сущность')}</div>
      </div>
      ` : ''}
      <div class="notif-detail-actions">
        ${canOpenTarget ? `
        <button class="btn btn-primary" onclick="openNotificationTarget()">
          ${escapeHtml(notification.target_label || 'Открыть')}
        </button>
        ` : ''}
        <button class="btn btn-secondary" onclick="closeNotificationDetail()">← К списку</button>
      </div>
    </div>
    <div class="pager">
      <button
        class="btn btn-secondary btn-sm"
        onclick="loadNotificationsPage(${state.notifications.page - 1})"
        ${state.notifications.page === 1 ? 'disabled' : ''}
      >
        ← Новее
      </button>
      <div class="pager-label">Страница ${state.notifications.page}</div>
      <button
        class="btn btn-secondary btn-sm"
        onclick="loadNotificationsPage(${state.notifications.page + 1})"
        ${!state.notifications.hasMore ? 'disabled' : ''}
      >
        Старее →
      </button>
    </div>
  `;
}

// ─── Helpers ────────────────────────────────────────────────
function money(amount) {
  return new Intl.NumberFormat('ru-RU').format(amount || 0) + '₽';
}

function formatPercent(value) {
  return new Intl.NumberFormat('ru-RU', {
    maximumFractionDigits: 2,
  }).format(Number(value || 0)) + '%';
}

function esc(str) {
  return (str || '').replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

function escapeHtml(str) {
  return String(str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function complexityLabel(c) {
  return {basic:'Простая', std:'Стандарт', complex:'Сложная', hard:'Тяжёлая'}[c] || c;
}

function itemRow(item) {
  return `
    <div class="item-row" onclick="navigate('item', {id: ${item.id}, title: '${esc(item.name).substring(0,25)}'})">
      <div class="item-info">
        <div class="item-name">${item.name}</div>
        <div class="item-meta">${item.unit}${item.popular ? ' · ⭐' : ''}</div>
      </div>
      <div class="item-price">${money(item.price)}</div>
      <div class="item-add" onclick="event.stopPropagation(); addToEstimate(${item.id}, '${esc(item.name)}')">+</div>
    </div>
  `;
}

function toast(text, isError = false) {
  const el = document.getElementById('toast');
  el.textContent = text;
  el.style.background = isError ? 'var(--destructive)' : 'var(--text)';
  el.classList.remove('hidden');
  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.classList.add('hidden'), 2500);
}

function updateFAB() {
  const fab = document.getElementById('fab-cart');
  const count = document.getElementById('fab-count');
  if (state.activeEstimateId && state.cartItems > 0) {
    fab.classList.remove('hidden');
    count.textContent = state.cartItems;
  } else {
    fab.classList.add('hidden');
  }
}

function setNotificationBadge(count) {
  const badge = document.getElementById('notif-badge');
  const value = Math.max(0, Number(count || 0));
  if (value > 0) {
    badge.textContent = value > 99 ? '99+' : String(value);
    badge.classList.remove('hidden');
  } else {
    badge.textContent = '0';
    badge.classList.add('hidden');
  }
}

function confirmAction(message) {
  if (tg?.showConfirm) {
    return new Promise(resolve => tg.showConfirm(message, resolve));
  }
  return Promise.resolve(window.confirm(message));
}

function notificationIcon(eventType) {
  return {
    'suggestion.created': '💡',
    'discount.requested': '💸',
    'discount.approved': '✅',
    'discount.rejected': '❌',
    'estimate.for_review': '📊',
    'estimate.approved': '✅',
    'estimate.deleted': '🗑',
    'order.assigned': '👷',
    'order.completed': '✅',
    'payment.received': '💰',
    'invite.pending_approval': '📨',
    'staffing.action': '👥',
  }[eventType] || '🔔';
}

function formatNotificationListTime(value) {
  if (!value) return '';
  return new Date(value).toLocaleString('ru-RU', {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatNotificationDetailTime(value) {
  if (!value) return 'Дата неизвестна';
  return new Date(value).toLocaleString('ru-RU', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

// ─── Start ──────────────────────────────────────────────────
init();
