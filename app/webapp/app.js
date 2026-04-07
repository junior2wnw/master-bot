/* в•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђ
   РњР°СЃС‚РµСЂР‘РѕС‚ Mini App вЂ” Core Application
   Telegram Web App SDK + Vanilla JS SPA
   в•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђв•ђ */

const API = '/api/v1';
const tg = window.Telegram?.WebApp;

// в”Ђв”Ђв”Ђ State в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
const state = {
  user: null,
  screen: 'dashboard',
  currentParams: {},
  history: [],
  activeEstimateId: null,
  currentOrder: null,
  orderCancelReasonPickerOpen: false,
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

const SCREEN_TITLES = {
  dashboard: 'РњР°СЃС‚РµСЂР‘РѕС‚',
  search: 'РџРѕРёСЃРє',
  catalog: 'РљР°С‚Р°Р»РѕРі',
  estimates: 'РЎРјРµС‚С‹',
  estimate: 'РЎРјРµС‚Р°',
  orders: 'Р—Р°РєР°Р·С‹',
  order: 'Р—Р°РєР°Р·',
  earnings: 'Р”РѕС…РѕРґС‹',
  approvals: 'РЎРѕРіР»Р°СЃРѕРІР°РЅРёСЏ',
  analytics: 'РђРЅР°Р»РёС‚РёРєР°',
  profile: 'РџСЂРѕС„РёР»СЊ',
  item: 'Р Р°Р±РѕС‚Р°',
  notifications: 'РЈРІРµРґРѕРјР»РµРЅРёСЏ',
  suggestions: 'РџСЂРµРґР»РѕР¶РµРЅРёСЏ',
  'profile-edit': 'Р›РёС‡РЅС‹Рµ РґР°РЅРЅС‹Рµ',
  qr: 'РћРїР»Р°С‚Р°',
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

function syncShell(screen) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  const el = document.getElementById('screen-' + screen);
  if (el) el.classList.add('active');

  document.querySelectorAll('.tab').forEach(t => {
    t.classList.toggle('active', t.dataset.tab === screen);
  });

  document.getElementById('btn-back').classList.toggle('hidden', state.history.length === 0);
}

function syncHeader(screen, params = {}) {
  document.getElementById('header-title').textContent = params.title || SCREEN_TITLES[screen] || '';
}

function activateScreen(screen, params = {}) {
  state.screen = screen;
  state.currentParams = {...params};
  syncShell(screen);
  syncHeader(screen, params);
  loadScreen(screen, params);
}

// в”Ђв”Ђв”Ђ Init в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
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
    document.getElementById('loader').innerHTML = '<p style="color:var(--destructive);padding:20px">РћС€РёР±РєР° Р°РІС‚РѕСЂРёР·Р°С†РёРё</p>';
    return;
  }

  hideLoader();
  setupSearch();
}

function hideLoader() {
  document.getElementById('loader').classList.add('hidden');
}

// в”Ђв”Ђв”Ђ API в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
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

// в”Ђв”Ђв”Ђ Navigation в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
function navigate(screen, params = {}) {
  if (state.screen !== screen) {
    state.history.push({screen: state.screen, params: {...(state.currentParams || {})}});
  }
  activateScreen(screen, params);
}

function replaceScreen(screen, params = {}) {
  activateScreen(screen, params);
}

function goBack() {
  if (state.history.length > 0) {
    const prev = state.history.pop();
    activateScreen(prev.screen, prev.params || {});
    return;
    state.screen = prev.screen;
    document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
    const el = document.getElementById('screen-' + prev.screen);
    if (el) el.classList.add('active');
    document.querySelectorAll('.tab').forEach(t => {
      t.classList.toggle('active', t.dataset.tab === prev.screen);
    });
    document.getElementById('btn-back').classList.toggle('hidden', state.history.length === 0);
    const titles = {dashboard:'РњР°СЃС‚РµСЂР‘РѕС‚',search:'РџРѕРёСЃРє',catalog:'РљР°С‚Р°Р»РѕРі',estimates:'РЎРјРµС‚С‹',profile:'РџСЂРѕС„РёР»СЊ'};
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
    case 'notifications': await loadNotifications(params); break;
    case 'suggestions': await loadSuggestionsComposer(); break;
    case 'profile-edit': await loadProfileEdit(); break;
    case 'qr': await loadQR(params.estimateId, params.profile); break;
  }
}

// в”Ђв”Ђв”Ђ Setup UI в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
function setupUI() {
  const roles = state.user.roles;
  const isMaster = hasRole(roles, 'master');

  // Show/hide tabs based on role
  if (isMaster) {
    document.getElementById('tab-estimates').classList.remove('hidden');
  }
}

// в”Ђв”Ђв”Ђ Dashboard в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
async function loadDashboard() {
  const data = await api('GET', '/dashboard');
  applyRoleContext(data);
  const roles = state.user.roles;
  const primaryRole = highestRole(roles);
  const isMaster = hasRole(roles, 'master');
  const isAdmin = hasRole(roles, 'admin');
  const isSenior = hasRole(roles, 'senior_master');

  document.getElementById('dash-name').textContent = `РџСЂРёРІРµС‚, ${state.user.name}!`;

  const roleLabels = {
    product_owner: 'Product Owner', admin: 'РђРґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂ',
    senior_master: 'РЎС‚Р°СЂС€РёР№ РјР°СЃС‚РµСЂ', master: 'РњР°СЃС‚РµСЂ', client: 'РљР»РёРµРЅС‚',
  };
  document.getElementById('dash-subtitle').textContent =
    data.active_role_label || state.user.active_role_label || roleLabels[primaryRole] || primaryRole || '';

  // Stats
  const stats = [];
  if (isMaster) {
    stats.push({value: data.active_estimates || 0, label: 'РђРєС‚РёРІРЅС‹С… СЃРјРµС‚'});
    stats.push({value: money(data.total_earned || 0), label: 'Р—Р°СЂР°Р±РѕС‚Р°РЅРѕ'});
  }
  stats.push({value: data.active_orders || 0, label: 'РђРєС‚РёРІРЅС‹С… Р·Р°РєР°Р·РѕРІ'});
  if (data.pending_approvals) {
    stats.push({value: data.pending_approvals, label: 'РћР¶РёРґР°СЋС‚ РґРµР№СЃС‚РІРёСЏ'});
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
    icon: 'рџ”Ќ', color: 'blue', title: 'Р‘С‹СЃС‚СЂС‹Р№ РїРѕРёСЃРє',
    desc: 'РќР°Р№С‚Рё СЂР°Р±РѕС‚Сѓ Р·Р° СЃРµРєСѓРЅРґС‹', action: "navigate('search')",
  });
  actions.push({
    icon: 'рџ“‹', color: 'green', title: 'РљР°С‚Р°Р»РѕРі СЂР°Р±РѕС‚',
    desc: 'Р’СЃРµ СѓСЃР»СѓРіРё РїРѕ РєР°С‚РµРіРѕСЂРёСЏРј', action: "navigate('catalog')",
  });

  if (isMaster) {
    actions.push({
      icon: 'рџ“Љ', color: 'orange', title: 'РњРѕРё СЃРјРµС‚С‹',
      desc: 'РЎРѕР·РґР°С‚СЊ РёР»Рё РїСЂРѕСЃРјРѕС‚СЂРµС‚СЊ', action: "navigate('estimates')",
      badge: data.active_estimates || null,
    });
    actions.push({
      icon: 'рџ’°', color: 'purple', title: 'Р”РѕС…РѕРґС‹',
      desc: 'РЎС‚Р°С‚РёСЃС‚РёРєР° Рё РІС‹РїР»Р°С‚С‹', action: "navigate('earnings')",
    });
  }

  if (isSenior || isAdmin) {
    actions.push({
      icon: 'вњ…', color: 'green', title: 'РЎРѕРіР»Р°СЃРѕРІР°РЅРёСЏ',
      desc: 'РЎРєРёРґРєРё Рё Р·Р°РїСЂРѕСЃС‹', action: "navigate('approvals')",
      badge: data.pending_approvals || null,
    });
  }

  if (isAdmin) {
    actions.push({
      icon: 'рџ“€', color: 'red', title: 'РђРЅР°Р»РёС‚РёРєР°',
      desc: 'РњРѕРЅРёС‚РѕСЂРёРЅРі РїР»Р°С‚С„РѕСЂРјС‹', action: "navigate('analytics')",
    });
  }

  actions.push({
    icon: 'рџ“ќ', color: 'blue', title: 'Р—Р°РєР°Р·С‹',
    desc: 'РћС‚СЃР»РµР¶РёРІР°РЅРёРµ Рё РёСЃС‚РѕСЂРёСЏ', action: "navigate('orders')",
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

// в”Ђв”Ђв”Ђ Search в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
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

// в”Ђв”Ђв”Ђ Catalog в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
async function loadCatalog(params = {}) {
  const container = document.getElementById('catalog-content');

  if (params.subgroupId) {
    // Show items in subgroup
    const items = await api('GET', `/catalog/items?subgroup_id=${params.subgroupId}`);
    container.innerHTML = `
      <p class="section-title">${params.title || 'Р Р°Р±РѕС‚С‹'}</p>
      <div class="item-list">${items.map(it => itemRow(it)).join('')}</div>
    `;
  } else if (params.groupId) {
    // Show subgroups or items
    const subs = await api('GET', `/catalog/subgroups/${params.groupId}`);
    if (subs.length > 0) {
      container.innerHTML = `
        <p class="section-title">${params.title || 'РџРѕРґРєР°С‚РµРіРѕСЂРёРё'}</p>
        <div class="catalog-grid">
          ${subs.map(s => `
            <div class="catalog-card" onclick="navigate('catalog', {groupId: ${params.groupId}, subgroupId: ${s.id}, title: '${esc(s.name)}'})">
              <div class="label">${s.name}</div>
              <div class="count">${s.count} СЂР°Р±РѕС‚</div>
            </div>
          `).join('')}
        </div>
        <p class="section-title mt-12">Р’СЃРµ СЂР°Р±РѕС‚С‹</p>
        <div class="item-list" id="group-items-${params.groupId}"></div>
      `;
      // Also load items
      const items = await api('GET', `/catalog/items?group_id=${params.groupId}`);
      document.getElementById(`group-items-${params.groupId}`).innerHTML = items.map(it => itemRow(it)).join('');
    } else {
      const items = await api('GET', `/catalog/items?group_id=${params.groupId}`);
      container.innerHTML = `
        <p class="section-title">${params.title || 'Р Р°Р±РѕС‚С‹'}</p>
        <div class="item-list">${items.map(it => itemRow(it)).join('')}</div>
      `;
    }
  } else if (params.professionId) {
    // Show groups
    const groups = await api('GET', `/catalog/groups/${params.professionId}`);
    container.innerHTML = `
      <p class="section-title">${params.title || 'РљР°С‚РµРіРѕСЂРёРё'}</p>
      <div class="catalog-grid">
        ${groups.map(g => `
          <div class="catalog-card" onclick="navigate('catalog', {professionId: ${params.professionId}, groupId: ${g.id}, title: '${esc(g.name)}'})">
            <div class="label">${g.name}</div>
            <div class="count">${g.count} СЂР°Р±РѕС‚</div>
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
            <div class="count">${p.count} СЂР°Р±РѕС‚</div>
          </div>
        `).join('')}
      </div>
      <div class="mt-12">
        <p class="section-title">РџРѕРїСѓР»СЏСЂРЅС‹Рµ СЂР°Р±РѕС‚С‹</p>
        <div class="item-list" id="popular-items"></div>
      </div>
    `;
    // Load popular items
    const popular = await api('GET', '/catalog/items?popular=true&limit=10');
    document.getElementById('popular-items').innerHTML = popular.map(it => itemRow(it)).join('');
  }
}

// в”Ђв”Ђв”Ђ Item Detail в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
async function loadItem(itemId) {
  const item = await api('GET', `/catalog/items/${itemId}`);
  const container = document.getElementById('item-detail');

  container.innerHTML = `
    <div class="card">
      <h3 style="font-size:17px;font-weight:700;margin-bottom:8px">${item.name}</h3>
      <div style="font-size:13px;color:var(--text-muted);margin-bottom:12px">
        <code>${item.code}</code> В· ${item.unit}
        ${item.complexity ? ` В· ${complexityLabel(item.complexity)}` : ''}
      </div>

      <div class="stat-grid" style="grid-template-columns:repeat(3,1fr);margin-bottom:12px">
        <div class="stat-card">
          <div class="stat-value" style="font-size:16px">${money(item.price_min)}</div>
          <div class="stat-label">РњРёРЅРёРјСѓРј</div>
        </div>
        <div class="stat-card">
          <div class="stat-value" style="font-size:16px">${money(item.price)}</div>
          <div class="stat-label">Р РµРєРѕРјРµРЅРґ.</div>
        </div>
        <div class="stat-card">
          <div class="stat-value" style="font-size:16px">${money(item.price_max)}</div>
          <div class="stat-label">РњР°РєСЃРёРјСѓРј</div>
        </div>
      </div>

      ${item.description ? `<p style="font-size:14px;margin-bottom:8px">${item.description}</p>` : ''}
      ${item.note ? `<p style="font-size:13px;color:var(--text-muted)">рџ“ќ ${item.note}</p>` : ''}
      ${item.aliases ? `<p style="font-size:12px;color:var(--text-muted);margin-top:8px">рџ”Ќ ${item.aliases}</p>` : ''}
    </div>

    <button class="btn btn-primary btn-block" onclick="addToEstimate(${item.id}, '${esc(item.name)}')">
      вћ• Р”РѕР±Р°РІРёС‚СЊ РІ СЃРјРµС‚Сѓ
    </button>
  `;
}

// в”Ђв”Ђв”Ђ Estimates в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
async function loadEstimates() {
  const estimates = await api('GET', '/estimates');
  const container = document.getElementById('estimates-list');

  if (estimates.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <p>РЈ РІР°СЃ РїРѕРєР° РЅРµС‚ СЃРјРµС‚</p>
        <button class="btn btn-primary mt-12" onclick="createEstimate()">вћ• РЎРѕР·РґР°С‚СЊ СЃРјРµС‚Сѓ</button>
      </div>
    `;
    return;
  }

  const statusIcons = {draft:'рџ“ќ', approved:'вњ…', client_review:'рџ‘Ѓ', paid:'рџ’°', completed:'в‘пёЏ', cancelled:'вќЊ'};
  const statusLabels = {draft:'Р§РµСЂРЅРѕРІРёРє', approved:'РЎРѕРіР»Р°СЃРѕРІР°РЅР°', client_review:'РќР° РїСЂРѕРІРµСЂРєРµ', paid:'РћРїР»Р°С‡РµРЅР°', completed:'Р—Р°РІРµСЂС€РµРЅР°', cancelled:'РћС‚РјРµРЅРµРЅР°', master_proposed:'РџСЂРµРґР»РѕР¶РµРЅР°', in_progress:'Р’ СЂР°Р±РѕС‚Рµ'};

  container.innerHTML = `
    <button class="btn btn-primary btn-block mb-12" onclick="createEstimate()">вћ• РќРѕРІР°СЏ СЃРјРµС‚Р°</button>
    ${estimates.map(e => `
      <div class="estimate-row" onclick="navigate('estimate', {id: ${e.id}})">
        <div class="est-icon">${statusIcons[e.status] || 'рџ“‹'}</div>
        <div class="est-info">
          <div class="est-title">РЎРјРµС‚Р° #${e.id} <span style="font-weight:400;color:var(--text-muted)">v${e.version}</span></div>
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
  const statusLabels = {draft:'Р§РµСЂРЅРѕРІРёРє', approved:'РЎРѕРіР»Р°СЃРѕРІР°РЅР°', client_review:'РќР° РїСЂРѕРІРµСЂРєРµ', paid:'РћРїР»Р°С‡РµРЅР°', completed:'Р—Р°РІРµСЂС€РµРЅР°', master_proposed:'РџСЂРµРґР»РѕР¶РµРЅР°', in_progress:'Р’ СЂР°Р±РѕС‚Рµ'};
  const caps = est.capabilities || {};
  const isDraft = est.status === 'draft';
  const canEdit = Boolean(caps.can_edit);
  const canDelete = Boolean(caps.can_delete) && isDraft;
  const canSendToClient = Boolean(caps.can_send_to_client);
  const canRequestDiscount = Boolean(caps.can_request_discount);
  const canClientRespond = Boolean(caps.can_client_respond);
  const canCreateOrder = Boolean(caps.can_create_order);
  const canExport = caps.can_export !== false;

  let itemsHtml = '';
  if (est.items.length === 0) {
    itemsHtml = `
      <div class="empty-state">
        <p>РЎРјРµС‚Р° РїСѓСЃС‚Р°</p>
        <p class="text-muted">${canEdit ? 'Р”РѕР±Р°РІСЊС‚Рµ СЂР°Р±РѕС‚С‹ С‡РµСЂРµР· РїРѕРёСЃРє РёР»Рё РєР°С‚Р°Р»РѕРі' : 'Р’ СЃРјРµС‚Рµ РїРѕРєР° РЅРµС‚ РїРѕР·РёС†РёР№'}</p>
        ${canEdit ? `
        <div style="display:flex;gap:8px;justify-content:center;margin-top:12px">
          <button class="btn btn-primary btn-sm" onclick="navigate('search')">рџ”Ќ РџРѕРёСЃРє</button>
          <button class="btn btn-secondary btn-sm" onclick="navigate('catalog')">рџ“‹ РљР°С‚Р°Р»РѕРі</button>
        </div>
        ` : ''}
      </div>
    `;
  } else {
    itemsHtml = est.items.map((it, i) => `
      <div class="cart-item">
        <div class="cart-item-info">
          <div class="cart-item-name">${i+1}. ${it.name}</div>
          <div class="cart-item-meta">${it.unit} Г— ${money(it.unit_price)}${it.coefficients ? ' ' + Object.values(it.coefficients).map(v => 'Г—'+v).join(' ') : ''}</div>
          <div class="cart-item-price">${money(it.subtotal)}</div>
        </div>
        ${isDraft && canEdit ? `
        <div class="cart-item-controls">
          <button class="qty-btn" onclick="changeQty(${est.id}, ${it.id}, ${it.quantity - 1})">в€’</button>
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
        <button class="btn btn-primary" onclick="navigate('search')">вћ• Р”РѕР±Р°РІРёС‚СЊ</button>
        ${canSendToClient ? `<button class="btn btn-secondary" onclick="sendToClient(${est.id})">рџ“¤ РљР»РёРµРЅС‚Сѓ</button>` : ''}
      </div>
      ${canRequestDiscount ? `
      <div class="cart-actions mt-8">
        <button class="btn btn-ghost btn-sm" onclick="requestDiscount(${est.id})">рџ’ё РЎРєРёРґРєР°</button>
      </div>
      ` : ''}
      ${canDelete ? `
      <div class="cart-actions mt-8">
        <button class="btn btn-danger btn-block" onclick="deleteEstimate(${est.id}, ${est.items.length}, ${est.final})">
          🗑 Удалить смету
        </button>
      </div>
      ` : ''}
    `;
  } else if (est.status === 'client_review' && canClientRespond) {
    actionsHtml = `
      <div class="cart-actions">
        <button class="btn btn-primary" onclick="approveEstimate(${est.id})">вњ… РЎРѕРіР»Р°СЃРѕРІР°С‚СЊ</button>
        <button class="btn btn-danger" onclick="rejectEstimate(${est.id})">вќЊ РћС‚РєР»РѕРЅРёС‚СЊ</button>
      </div>
    `;
  } else if (est.status === 'approved' && canCreateOrder) {
    actionsHtml = `
      <div class="cart-actions">
        <button class="btn btn-primary btn-block" onclick="createOrderFromEstimate(${est.id})">рџ“ќ РЎРѕР·РґР°С‚СЊ Р·Р°РєР°Р·</button>
      </div>
    `;
  }

  if (est.items.length > 0 && canExport) {
    actionsHtml += `
      <div class="export-bar mt-12">
        <div class="export-title">Р’С‹РіСЂСѓР·РёС‚СЊ СЃРјРµС‚Сѓ</div>
        <div class="export-buttons">
          <a class="btn btn-secondary btn-sm" href="${API}/estimates/${est.id}/export/pdf?tg_id=${state.user.telegram_id}" target="_blank">рџ“„ PDF</a>
          <a class="btn btn-secondary btn-sm" href="${API}/estimates/${est.id}/export/xlsx?tg_id=${state.user.telegram_id}" target="_blank">рџ“Љ XLSX</a>
          <button class="btn btn-secondary btn-sm" onclick="navigate('qr', {estimateId: ${est.id}})">рџ’і QR РѕРїР»Р°С‚Р°</button>
        </div>
      </div>
    `;
  }

  container.innerHTML = `
    <div class="cart-header">
      <h3>РЎРјРµС‚Р° #${est.id} <span style="font-weight:400;color:var(--text-muted)">v${est.version}</span></h3>
      <span class="cart-status ${est.status}">${statusLabels[est.status] || est.status}</span>
    </div>
    ${itemsHtml}
    <div class="cart-totals">
      <div class="cart-total-row">
        <span>РЎСѓРјРјР°</span>
        <span>${money(est.total)}</span>
      </div>
      ${est.discount > 0 ? `
      <div class="cart-total-row">
        <span>РЎРєРёРґРєР°</span>
        <span class="discount">в€’${money(est.discount)}</span>
      </div>
      ` : ''}
      <div class="cart-total-row final">
        <span>РС‚РѕРіРѕ</span>
        <span class="text-accent">${money(est.final)}</span>
      </div>
    </div>
    ${actionsHtml}
  `;

  // Update FAB
  state.cartItems = est.items.length;
  updateFAB();
}

// в”Ђв”Ђв”Ђ Estimate Actions в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
async function createEstimate() {
  try {
    const est = await api('POST', '/estimates');
    state.activeEstimateId = est.id;
    toast('РЎРјРµС‚Р° СЃРѕР·РґР°РЅР°');
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
    toast(`вњ… ${itemName} в†’ СЃРјРµС‚Р°`);

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
    toast('РЈРґР°Р»РµРЅРѕ');
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
    replaceScreen('estimates');
  } catch (e) {
    toast(e.message, true);
  }
}

async function sendToClient(estimateId) {
  // For now, just change status to client_review
  try {
    await api('POST', `/estimates/${estimateId}/status`, {status: 'client_review'});
    toast('рџ“¤ РЎРјРµС‚Р° РѕС‚РїСЂР°РІР»РµРЅР° РєР»РёРµРЅС‚Сѓ');
    await loadEstimate(estimateId);
  } catch (e) { toast(e.message, true); }
}

async function approveEstimate(estimateId) {
  try {
    await api('POST', `/estimates/${estimateId}/status`, {status: 'approved'});
    toast('вњ… РЎРјРµС‚Р° СЃРѕРіР»Р°СЃРѕРІР°РЅР°');
    await loadEstimate(estimateId);
  } catch (e) { toast(e.message, true); }
}

async function rejectEstimate(estimateId) {
  try {
    await api('POST', `/estimates/${estimateId}/status`, {status: 'draft'});
    toast('РЎРјРµС‚Р° РѕС‚РєР»РѕРЅРµРЅР°');
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

// в”Ђв”Ђв”Ђ Orders в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
async function loadOrders() {
  const orders = await api('GET', '/orders');
  const container = document.getElementById('orders-list');

  if (orders.length === 0) {
    container.innerHTML = '<div class="empty-state"><p>Р—Р°РєР°Р·РѕРІ РїРѕРєР° РЅРµС‚</p></div>';
    return;
  }

  const statusIcons = {draft:'рџ“ќ', submitted:'рџ“¤', assigned:'рџ‘·', in_progress:'рџ”Ё', completed:'вњ…', paid:'рџ’°', cancelled:'вќЊ'};
  const statusLabels = {draft:'Р§РµСЂРЅРѕРІРёРє', submitted:'РћС‚РїСЂР°РІР»РµРЅ', assigned:'РќР°Р·РЅР°С‡РµРЅ', in_progress:'Р’ СЂР°Р±РѕС‚Рµ', completed:'Р—Р°РІРµСЂС€С‘РЅ', paid:'РћРїР»Р°С‡РµРЅ', cancelled:'РћС‚РјРµРЅС‘РЅ'};

  container.innerHTML = orders.map(o => `
    <div class="order-row" onclick="navigate('order', {id: ${o.id}})">
      <div style="font-size:24px">${statusIcons[o.status] || 'рџ“‹'}</div>
      <div style="flex:1">
        <div style="font-weight:600">Р—Р°РєР°Р· #${o.id}</div>
        <div style="font-size:12px;color:var(--text-muted)">${statusLabels[o.status] || o.status}${o.address ? ' В· ' + o.address.substring(0,25) : ''}</div>
      </div>
    </div>
  `).join('');
}

async function loadOrder(orderId) {
  const order = await api('GET', `/orders/${orderId}`);
  const container = document.getElementById('order-detail');
  const caps = order.capabilities || {};
  const reasonOptions = Array.isArray(order.cancel_reasons) ? order.cancel_reasons : [];

  if (!state.currentOrder || state.currentOrder.id !== order.id) {
    state.orderCancelReasonPickerOpen = false;
  }
  if (!caps.can_cancel || reasonOptions.length === 0) {
    state.orderCancelReasonPickerOpen = false;
  }
  state.currentOrder = order;

  const statusIcons = {draft:'рџ“ќ', submitted:'рџ“¤', assigned:'рџ‘·', in_progress:'рџ”Ё', completed:'вњ…', paid:'рџ’°', cancelled:'вќЊ'};
  const statusLabels = {draft:'Р§РµСЂРЅРѕРІРёРє', submitted:'РћС‚РїСЂР°РІР»РµРЅ', assigned:'РќР°Р·РЅР°С‡РµРЅ', in_progress:'Р’ СЂР°Р±РѕС‚Рµ', completed:'Р—Р°РІРµСЂС€С‘РЅ', paid:'РћРїР»Р°С‡РµРЅ', cancelled:'РћС‚РјРµРЅС‘РЅ'};
  const urgencyLabels = {normal:'РћР±С‹С‡РЅР°СЏ', urgent:'РЎСЂРѕС‡РЅР°СЏ', emergency:'Р­РєСЃС‚СЂРµРЅРЅР°СЏ'};

  // Estimate items section
  let itemsHtml = '';
  if (order.estimate) {
    itemsHtml = `
      <div class="card mt-12">
        <div class="card-title">РЎРѕСЃС‚Р°РІ СЂР°Р±РѕС‚ (v${order.estimate.version})</div>
        ${order.estimate.items.map((it, i) => `
          <div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border);font-size:14px">
            <span>${i+1}. ${it.name} Г— ${it.quantity}</span>
            <span style="white-space:nowrap">${money(it.subtotal)}</span>
          </div>
        `).join('')}
        <div style="display:flex;justify-content:space-between;padding:8px 0;font-weight:700;font-size:15px">
          <span>РС‚РѕРіРѕ</span>
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
        <div class="card-title">РСЃС‚РѕСЂРёСЏ</div>
        <div class="timeline">
          ${order.history.map(h => `
            <div class="timeline-item">
              <div class="timeline-dot"></div>
              <div class="timeline-content">
                <span class="timeline-status">${statusLabels[h.to] || h.to}</span>
                <span class="timeline-time">${h.at ? new Date(h.at).toLocaleString('ru-RU', {day:'numeric', month:'short', hour:'2-digit', minute:'2-digit'}) : ''}</span>
                ${h.reason ? `<div class="text-muted" style="margin-top:4px">${escapeHtml(h.reason)}</div>` : ''}
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
    actionsHtml = `<button class="btn btn-primary btn-block" onclick="updateOrderStatus(${order.id}, 'submitted')">рџ“¤ РћС‚РїСЂР°РІРёС‚СЊ Р·Р°РєР°Р·</button>`;
  } else if (caps.can_assign) {
    actionsHtml = `<button class="btn btn-primary btn-block" onclick="assignOrder(${order.id})">вњ‹ Р’Р·СЏС‚СЊ Р·Р°РєР°Р·</button>`;
  } else if (caps.can_start) {
    actionsHtml = `<button class="btn btn-primary btn-block" onclick="updateOrderStatus(${order.id}, 'in_progress')">рџ”Ё РќР°С‡Р°С‚СЊ СЂР°Р±РѕС‚Сѓ</button>`;
  } else if (caps.can_complete) {
    actionsHtml = `<button class="btn btn-primary btn-block" onclick="updateOrderStatus(${order.id}, 'completed')">вњ… Р—Р°РІРµСЂС€РёС‚СЊ</button>`;
  } else if (caps.can_pay) {
    actionsHtml = `<button class="btn btn-primary btn-block" onclick="showPayment(${order.id})">рџ’і РћРїР»Р°С‚РёС‚СЊ</button>`;
  }

  if (caps.can_cancel) {
    if (reasonOptions.length > 0) {
      actionsHtml += `
        <button class="btn btn-ghost btn-block mt-8" onclick="toggleOrderCancelReasonPicker()">
          Отменить заказ
        </button>
      `;
      if (state.orderCancelReasonPickerOpen) {
        actionsHtml += `
          <div class="card mt-8">
            <div class="card-title">Причина отмены со стороны мастера</div>
            <div class="card-subtitle">Выберите причину, не зависящую от клиента.</div>
            <div style="display:flex;flex-direction:column;gap:8px;margin-top:12px">
              ${reasonOptions.map(reason => `
                <button class="btn btn-secondary btn-block" onclick="cancelOrderWithReason('${esc(reason.code)}')">
                  ${escapeHtml(reason.label)}
                </button>
              `).join('')}
            </div>
          </div>
        `;
      }
    } else {
      actionsHtml += `<button class="btn btn-ghost btn-block mt-8" onclick="updateOrderStatus(${order.id}, 'cancelled')">Отменить заказ</button>`;
    }
  }

  container.innerHTML = `
    <div class="card">
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">
        <div style="font-size:32px">${statusIcons[order.status] || 'рџ“‹'}</div>
        <div>
          <h3 style="font-size:17px;font-weight:700">Р—Р°РєР°Р· #${order.id}</h3>
          <span class="cart-status ${order.status}">${statusLabels[order.status] || order.status}</span>
        </div>
      </div>
      <div class="order-meta">
        ${order.address ? `<div class="meta-row"><span class="meta-icon">рџ“Ќ</span> ${order.address}</div>` : ''}
        <div class="meta-row"><span class="meta-icon">вљЎ</span> ${urgencyLabels[order.urgency] || order.urgency}</div>
        ${order.client_name ? `<div class="meta-row"><span class="meta-icon">рџ‘¤</span> РљР»РёРµРЅС‚: ${order.client_name}</div>` : ''}
        ${order.master_name ? `<div class="meta-row"><span class="meta-icon">рџ”§</span> РњР°СЃС‚РµСЂ: ${order.master_name}</div>` : ''}
        ${order.notes ? `<div class="meta-row"><span class="meta-icon">рџ“ќ</span> ${order.notes}</div>` : ''}
        ${order.cancellation_reason ? `<div class="meta-row"><span class="meta-icon">❌</span> Причина отмены: ${escapeHtml(order.cancellation_reason)}</div>` : ''}
        ${order.payment_status ? `<div class="meta-row"><span class="meta-icon">рџ’і</span> РћРїР»Р°С‚Р°: ${order.payment_status}</div>` : ''}
      </div>
    </div>
    ${itemsHtml}
    ${historyHtml}
    <div class="mt-12">${actionsHtml}</div>
  `;
}

function toggleOrderCancelReasonPicker() {
  if (!state.currentOrder) return;
  state.orderCancelReasonPickerOpen = !state.orderCancelReasonPickerOpen;
  loadOrder(state.currentOrder.id).catch(e => toast(e.message, true));
}

function cancelOrderWithReason(reasonCode) {
  if (!state.currentOrder) return;
  const selectedReason = (state.currentOrder.cancel_reasons || []).find(item => item.code === reasonCode);
  updateOrderStatus(state.currentOrder.id, 'cancelled', {
    reason: reasonCode,
    confirmText: selectedReason
      ? `Отменить заказ по причине: ${selectedReason.label}?`
      : 'Отменить заказ?',
  });
}

async function updateOrderStatus(orderId, status, options = {}) {
  try {
    let reason = options.reason || null;
    if (status === 'cancelled') {
      if (!reason) {
        const input = prompt('Укажите причину отмены заказа:');
        if (!input) return;
        reason = input.trim();
      }
      const confirmed = await confirmAction(options.confirmText || 'Отменить заказ?');
      if (!confirmed) return;
    }

    await api('POST', `/orders/${orderId}/status`, {status, reason});
    state.orderCancelReasonPickerOpen = false;
    toast('РЎС‚Р°С‚СѓСЃ РѕР±РЅРѕРІР»С‘РЅ');
    await loadOrder(orderId);
  } catch (e) { toast(e.message, true); }
}

async function assignOrder(orderId) {
  try {
    await api('POST', `/orders/${orderId}/assign-self`);
    toast('Р—Р°РєР°Р· РЅР°Р·РЅР°С‡РµРЅ РІР°Рј');
    await loadOrder(orderId);
  } catch (e) { toast(e.message, true); }
}

async function showPayment(orderId) {
  try {
    const info = await api('GET', `/orders/${orderId}/payment`);
    const container = document.getElementById('order-detail');
    container.innerHTML += `
      <div class="card mt-12 payment-card">
        <div class="card-title">рџ’і РћРїР»Р°С‚Р°</div>
        <div class="payment-amount">${money(info.amount)}</div>
        ${info.recipient ? `<div class="meta-row">РџРѕР»СѓС‡Р°С‚РµР»СЊ: ${info.recipient}</div>` : ''}
        ${info.bank_name ? `<div class="meta-row">Р‘Р°РЅРє: ${info.bank_name}</div>` : ''}
        ${info.phone ? `<div class="meta-row">РўРµР»РµС„РѕРЅ: ${info.phone}</div>` : ''}
        ${info.qr_data ? `<div class="meta-row" style="margin-top:8px;font-size:12px;color:var(--text-muted)">QR-РґР°РЅРЅС‹Рµ: ${info.qr_data}</div>` : ''}
      </div>
    `;
  } catch (e) { toast(e.message, true); }
}

async function createOrderFromEstimate(estimateId) {
  const address = prompt('РђРґСЂРµСЃ РІС‹РїРѕР»РЅРµРЅРёСЏ СЂР°Р±РѕС‚:');
  if (!address) return;
  try {
    const order = await api('POST', '/orders', {
      estimate_id: estimateId, address, urgency: 'normal',
    });
    toast(`Р—Р°РєР°Р· #${order.id} СЃРѕР·РґР°РЅ`);
    navigate('orders');
  } catch (e) { toast(e.message, true); }
}

// в”Ђв”Ђв”Ђ Earnings в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
async function loadEarnings() {
  const data = await api('GET', '/earnings');
  document.getElementById('earnings-content').innerHTML = `
    <div class="earning-stat">
      <div class="earning-value">${money(data.total_earned)}</div>
      <div class="earning-label">РћР±С‰РёР№ Р·Р°СЂР°Р±РѕС‚РѕРє</div>
    </div>
    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-value" style="font-size:18px">${data.completed}</div>
        <div class="stat-label">Р’С‹РїРѕР»РЅРµРЅРѕ Р·Р°РєР°Р·РѕРІ</div>
      </div>
      <div class="stat-card">
        <div class="stat-value" style="font-size:18px">${money(data.pending)}</div>
        <div class="stat-label">РћР¶РёРґР°РµС‚ РѕРїР»Р°С‚С‹</div>
      </div>
    </div>
    <div class="card mt-12">
      <div class="card-title">РљРѕРјРёСЃСЃРёСЏ РїР»Р°С‚С„РѕСЂРјС‹</div>
      <p style="font-size:14px;color:var(--text-muted);margin-top:4px">${money(data.commission_paid)}</p>
    </div>
  `;
}

// в”Ђв”Ђв”Ђ Approvals в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
async function loadApprovals() {
  const items = await api('GET', '/approvals');
  const container = document.getElementById('approvals-list');

  if (items.length === 0) {
    container.innerHTML = '<div class="empty-state"><p>РќРµС‚ РѕР¶РёРґР°СЋС‰РёС… СЃРѕРіР»Р°СЃРѕРІР°РЅРёР№</p></div>';
    return;
  }

  container.innerHTML = items.map(dr => `
    <div class="card">
      <div class="card-header">
        <div>
          <div class="card-title">Смета #${dr.estimate_id}</div>
          <div class="card-subtitle">${dr.type === 'fixed' ? `${money(dr.value)} (legacy)` : formatPercent(dr.value)}</div>
        </div>
      </div>
      <div style="display:flex;gap:8px">
        <button class="btn btn-primary btn-sm flex-1" onclick="processApproval(${dr.id}, 'approve')">вњ… РћРґРѕР±СЂРёС‚СЊ</button>
        <button class="btn btn-danger btn-sm flex-1" onclick="processApproval(${dr.id}, 'reject')">вќЊ РћС‚РєР»РѕРЅРёС‚СЊ</button>
      </div>
    </div>
  `).join('');
}

async function processApproval(requestId, action) {
  try {
    await api('POST', `/approvals/${requestId}`, {action});
    toast(action === 'approve' ? 'вњ… РћРґРѕР±СЂРµРЅРѕ' : 'вќЊ РћС‚РєР»РѕРЅРµРЅРѕ');
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
        <div class="stat-card"><div class="stat-value">${data.users}</div><div class="stat-label">РџРѕР»СЊР·РѕРІР°С‚РµР»РµР№</div></div>
        <div class="stat-card"><div class="stat-value">${data.masters}</div><div class="stat-label">РњР°СЃС‚РµСЂРѕРІ</div></div>
        <div class="stat-card"><div class="stat-value">${data.estimates}</div><div class="stat-label">РЎРјРµС‚</div></div>
        <div class="stat-card"><div class="stat-value">${data.orders}</div><div class="stat-label">Р—Р°РєР°Р·РѕРІ</div></div>
      </div>

      <div class="analytics-card">
        <h3 style="font-size:15px;font-weight:600;margin-bottom:12px">рџ’° Р¤РёРЅР°РЅСЃС‹</h3>
        <div class="cart-total-row"><span>РћР±РѕСЂРѕС‚</span><span class="font-bold">${money(data.gross)}</span></div>
        <div class="cart-total-row"><span>РљРѕРјРёСЃСЃРёСЏ</span><span class="font-bold">${money(data.platform_fee)}</span></div>
        <div class="cart-total-row"><span>  РЎС‚. РјР°СЃС‚РµСЂР°Рј</span><span>${money(data.senior_share)}</span></div>
        <div class="cart-total-row"><span>  РђРґРјРёРЅР°Рј</span><span>${money(data.admin_share)}</span></div>
        <div class="cart-total-row final"><span>Р§РёСЃС‚Р°СЏ РїСЂРёР±С‹Р»СЊ</span><span class="text-accent">${money(data.platform_net)}</span></div>
      </div>

      <div class="analytics-card">
        <h3 style="font-size:15px;font-weight:600;margin-bottom:12px">рџ“Љ Р’РѕСЂРѕРЅРєР° Р·Р°РєР°Р·РѕРІ</h3>
        ${['draft','submitted','assigned','in_progress','completed','paid','cancelled'].map(s => {
          const labels = {draft:'Р§РµСЂРЅРѕРІРёРєРё', submitted:'РћС‚РїСЂР°РІР»РµРЅС‹', assigned:'РќР°Р·РЅР°С‡РµРЅС‹', in_progress:'Р’ СЂР°Р±РѕС‚Рµ', completed:'Р—Р°РІРµСЂС€РµРЅС‹', paid:'РћРїР»Р°С‡РµРЅС‹', cancelled:'РћС‚РјРµРЅРµРЅС‹'};
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

// в”Ђв”Ђв”Ђ Profile в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
function loadProfile() {
  const u = state.user;
  const primaryRole = highestRole(u.roles);
  const roleLabels = {
    product_owner: 'рџЏў Product Owner', admin: 'вљ™пёЏ РђРґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂ',
    senior_master: 'рџ‘ЁвЂЌрџ”§ РЎС‚Р°СЂС€РёР№ РјР°СЃС‚РµСЂ', master: 'рџ”§ РњР°СЃС‚РµСЂ', client: 'рџ‘¤ РљР»РёРµРЅС‚',
  };

  const isMaster = hasRole(u.roles, 'master');
  const isAdmin = hasRole(u.roles, 'admin');
  const activeRoleLabel = u.active_role_label || roleLabels[primaryRole] || primaryRole || '';
  const maxRoleLabel = u.max_role_label || activeRoleLabel;

  let menuItems = '';
  menuItems += profileItem('рџ‘¤', 'Р›РёС‡РЅС‹Рµ РґР°РЅРЅС‹Рµ Рё СЂРµРєРІРёР·РёС‚С‹', "navigate('profile-edit')");
  if (isMaster) {
    menuItems += profileItem('рџЏ¦', 'РњРѕРё СЂРµРєРІРёР·РёС‚С‹ Рё QR', "navigate('qr', {profile: 1})");
    menuItems += profileItem('рџ’°', 'Р”РѕС…РѕРґС‹', "navigate('earnings')");
    menuItems += profileItem('рџ“Љ', 'РњРѕРё СЃРјРµС‚С‹', "navigate('estimates')");
  }
  menuItems += profileItem('📝', 'Мои заказы', "navigate('orders')");
  menuItems += profileItem('💡', 'Предложения', "navigate('suggestions')");
  if (isAdmin) {
    menuItems += profileItem('рџ“€', 'РђРЅР°Р»РёС‚РёРєР°', "navigate('analytics')");
    menuItems += profileItem('вњ…', 'РЎРѕРіР»Р°СЃРѕРІР°РЅРёСЏ', "navigate('approvals')");
  }

  const roleContext = u.can_switch_role ? `
    <div class="card profile-context">
      <div class="card-title">рџЋ­ Р РµР¶РёРј СЂРѕР»Рё</div>
      <div class="profile-meta"><span>РЎРµР№С‡Р°СЃ</span><strong>${activeRoleLabel}</strong></div>
      <div class="profile-meta"><span>РњР°РєСЃРёРјСѓРј</span><strong>${maxRoleLabel}</strong></div>
      ${u.is_role_switched ? '<div class="profile-note">Р’РєР»СЋС‡РµРЅ РІСЂРµРјРµРЅРЅС‹Р№ С‚РµСЃС‚РѕРІС‹Р№ РєРѕРЅС‚СѓСЂ РїСЂР°РІ. РџСЂСЏРјС‹Рµ СЂРѕР»Рё РІ Р±Р°Р·Рµ РЅРµ РјРµРЅСЏСЋС‚СЃСЏ.</div>' : ''}
      <div class="role-switcher">
        <button class="role-chip ${!u.role_override ? 'active' : ''}" onclick="setRoleMode(null)">РђРІС‚Рѕ</button>
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
      ${u.is_role_switched ? `<div class="profile-roles">РњР°РєСЃРёРјР°Р»СЊРЅР°СЏ СЂРѕР»СЊ: ${maxRoleLabel}</div>` : ''}
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
    toast(`Р РµР¶РёРј: ${payload.active_role_label}`);
  } catch (e) {
    toast(e.message, true);
  }
}

// в”Ђв”Ђв”Ђ Profile Editor в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
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
      <div class="card-title">рџ‘¤ Р›РёС‡РЅС‹Рµ РґР°РЅРЅС‹Рµ</div>
      <p style="font-size:12px;color:var(--text-muted);margin-bottom:12px">Р­С‚Рё РґР°РЅРЅС‹Рµ РёСЃРїРѕР»СЊР·СѓСЋС‚СЃСЏ РІ С€Р°РїРєРµ СЃРјРµС‚ (PDF/XLSX)</p>
      ${formField('pe-full_name', 'Р¤РРћ', p.full_name, 'РРІР°РЅРѕРІ РРІР°РЅ РРІР°РЅРѕРІРёС‡')}
      ${formField('pe-phone', 'РўРµР»РµС„РѕРЅ', p.phone, '+7 999 123-45-67')}
      ${formField('pe-email', 'Email', p.email, 'master@mail.ru')}
      ${formField('pe-telegram_username', 'Telegram', p.telegram_username, '@username')}
      ${formField('pe-company_name', 'РљРѕРјРїР°РЅРёСЏ / РРџ', p.company_name, 'РРџ РРІР°РЅРѕРІ Р.Р.')}
      ${formField('pe-inn', 'РРќРќ', p.inn, '123456789012')}
      ${formField('pe-address', 'РђРґСЂРµСЃ', p.address, 'Рі. РЎС‚РµСЂР»РёС‚Р°РјР°Рє, СѓР». ...')}
      ${formField('pe-specialization', 'РЎРїРµС†РёР°Р»РёР·Р°С†РёСЏ', p.specialization, 'Р­Р»РµРєС‚СЂРёРє, РЎР°РЅС‚РµС…РЅРёРє')}
    </div>

    <div class="card mt-12">
      <div class="card-title">рџЏ¦ Р‘Р°РЅРєРѕРІСЃРєРёРµ СЂРµРєРІРёР·РёС‚С‹</div>
      <p style="font-size:12px;color:var(--text-muted);margin-bottom:12px">Р”Р»СЏ QR-РєРѕРґР° РѕРїР»Р°С‚С‹ Рё СЂРµРєРІРёР·РёС‚РѕРІ РІ СЃРјРµС‚Рµ</p>
      ${formField('pe-payment_recipient', 'РџРѕР»СѓС‡Р°С‚РµР»СЊ РїР»Р°С‚РµР¶Р°', p.payment_recipient, 'РРџ РРІР°РЅРѕРІ РРІР°РЅ РРІР°РЅРѕРІРёС‡')}
      ${formField('pe-bank_name', 'Р‘Р°РЅРє', p.bank_name, 'РЎР±РµСЂР±Р°РЅРє')}
      ${formField('pe-settlement_account', 'Р Р°СЃС‡С‘С‚РЅС‹Р№ СЃС‡С‘С‚', p.settlement_account, '40802810...')}
      ${formField('pe-correspondent_account', 'РљРѕСЂСЂ. СЃС‡С‘С‚', p.correspondent_account, '30101810...')}
      ${formField('pe-bik', 'Р‘РРљ', p.bik, '042202603')}
      ${formField('pe-card_number', 'РќРѕРјРµСЂ РєР°СЂС‚С‹', p.card_number, '2202 **** **** 1234')}
      ${formField('pe-sbp_phone', 'РўРµР»РµС„РѕРЅ РЎР‘Рџ', p.sbp_phone, '+7 999 123-45-67')}
    </div>

    <button class="btn btn-primary btn-block mt-12" onclick="saveProfile()">рџ’ѕ РЎРѕС…СЂР°РЅРёС‚СЊ</button>
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
    toast('Р”Р°РЅРЅС‹Рµ СЃРѕС…СЂР°РЅРµРЅС‹');
  } catch (e) { toast(e.message, true); }
}

// в”Ђв”Ђв”Ђ QR Payment Viewer в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
async function loadQR(estimateId, profileMode = false) {
  const container = document.getElementById('qr-content');

  try {
    const data = profileMode
      ? await api('GET', '/profile/payment-qr')
      : await api('GET', `/estimates/${estimateId}/qr`);

    const qrMode = data.qr_mode || (data.has_bank_qr ? 'bank' : (data.has_qr ? 'sbp_phone' : 'none'));
    const isSBPFallback = qrMode === 'sbp_phone';
    const title = profileMode ? 'РњРѕРё СЂРµРєРІРёР·РёС‚С‹' : `РћРїР»Р°С‚Р° РїРѕ СЃРјРµС‚Рµ #${estimateId}`;
    let subtitle = profileMode
      ? 'QR РїРѕРєР° РЅРµ СЃС„РѕСЂРјРёСЂРѕРІР°РЅ'
      : `РћРїР»Р°С‚Р° РїРѕ СЃРјРµС‚Рµ #${estimateId}`;
    let qrHint = 'РћС‚СЃРєР°РЅРёСЂСѓР№С‚Рµ QR-РєРѕРґ РІ РїСЂРёР»РѕР¶РµРЅРёРё Р±Р°РЅРєР°';

    if (qrMode === 'bank') {
      subtitle = profileMode
        ? 'Р‘Р°РЅРєРѕРІСЃРєРёР№ QR Р±РµР· СЃСѓРјРјС‹: СЃСѓРјРјСѓ РјРѕР¶РЅРѕ РІРІРµСЃС‚Рё РІСЂСѓС‡РЅСѓСЋ РІ Р±Р°РЅРєРѕРІСЃРєРѕРј РїСЂРёР»РѕР¶РµРЅРёРё'
        : `Р‘Р°РЅРєРѕРІСЃРєРёР№ QR РґР»СЏ РѕРїР»Р°С‚С‹ РїРѕ СЃРјРµС‚Рµ #${estimateId}`;
    } else if (qrMode === 'sbp_phone') {
      subtitle = profileMode
        ? 'Р‘С‹СЃС‚СЂС‹Р№ QR РґР»СЏ РїРµСЂРµРІРѕРґР° РїРѕ РЎР‘Рџ РїРѕ РЅРѕРјРµСЂСѓ С‚РµР»РµС„РѕРЅР°'
        : `Р‘С‹СЃС‚СЂС‹Р№ РїРµСЂРµРІРѕРґ РїРѕ РЎР‘Рџ РїРѕ СЃРјРµС‚Рµ #${estimateId}`;
      qrHint = 'Р•СЃР»Рё РїСЂРёР»РѕР¶РµРЅРёРµ Р±Р°РЅРєР° РЅРµ СЂР°СЃРїРѕР·РЅР°С‘С‚ QR, РїРµСЂРµРІРµРґРёС‚Рµ РїРѕ РЅРѕРјРµСЂСѓ С‚РµР»РµС„РѕРЅР° Рё СЃСѓРјРјРµ РЅРёР¶Рµ';
    }

    const amountHtml = data.amount ? `<div class="qr-amount">${money(data.amount)}</div>` : '';
    const missingFields = Array.isArray(data.missing_bank_fields) ? data.missing_bank_fields : [];

    container.innerHTML = `
      <div class="qr-viewer">
        ${amountHtml}
        <div class="qr-label">${subtitle}</div>

        ${data.qr_image ? `
          <div class="qr-image-wrap">
            <img src="data:image/png;base64,${data.qr_image}" alt="QR РєРѕРґ РґР»СЏ РѕРїР»Р°С‚С‹" class="qr-image">
          </div>
          <div class="qr-hint">${qrHint}</div>
        ` : ''}

        ${isSBPFallback && data.fallback_notice ? `
          <div class="card mt-12">
            <div class="card-title">Р РµР¶РёРј РѕРїР»Р°С‚С‹</div>
            <div class="text-muted">${data.fallback_notice}</div>
          </div>
        ` : ''}

        <div class="card mt-12">
          <div class="card-title">${title}</div>
          ${qrMode === 'bank' ? payRow('Р РµР¶РёРј QR', 'Р‘Р°РЅРєРѕРІСЃРєРёР№ QR') : ''}
          ${isSBPFallback ? payRow('Р РµР¶РёРј QR', 'РЎР‘Рџ РїРѕ РЅРѕРјРµСЂСѓ С‚РµР»РµС„РѕРЅР°') : ''}
          ${data.recipient ? payRow('РџРѕР»СѓС‡Р°С‚РµР»СЊ', data.recipient) : ''}
          ${data.bank ? payRow('Р‘Р°РЅРє', data.bank) : ''}
          ${data.account ? payRow('Р /СЃ', data.account, true) : ''}
          ${data.correspondent_account ? payRow('РљРѕСЂСЂ. СЃС‡РµС‚', data.correspondent_account, true) : ''}
          ${data.bik ? payRow('Р‘РРљ', data.bik, true) : ''}
          ${data.inn ? payRow('РРќРќ', data.inn, true) : ''}
          ${data.card ? payRow('РљР°СЂС‚Р°', data.card, true) : ''}
          ${data.sbp_phone ? payRow('РЎР‘Рџ (С‚РµР»РµС„РѕРЅ)', data.sbp_phone, true) : ''}
        </div>

        ${missingFields.length ? `
          <div class="card mt-12">
            <div class="card-title">Р§С‚Рѕ РЅСѓР¶РЅРѕ Р·Р°РїРѕР»РЅРёС‚СЊ РґР»СЏ РїРѕР»РЅРѕС†РµРЅРЅРѕРіРѕ Р±Р°РЅРєРѕРІСЃРєРѕРіРѕ QR</div>
            <div class="text-muted">${missingFields.join(', ')}</div>
          </div>
        ` : ''}

        ${data.sbp_phone ? `
          <div class="sbp-section mt-12">
            <div class="sbp-label">РџРµСЂРµРІРѕРґ РїРѕ РЎР‘Рџ</div>
            <div class="sbp-phone" onclick="copyToClipboard('${esc(data.sbp_phone)}')">${data.sbp_phone} <span class="copy-icon">рџ“‹</span></div>
            <div class="sbp-hint">РќР°Р¶РјРёС‚Рµ, С‡С‚РѕР±С‹ СЃРєРѕРїРёСЂРѕРІР°С‚СЊ РЅРѕРјРµСЂ${data.amount ? ' Рё РїРµСЂРµРІРµРґРёС‚Рµ СЃСѓРјРјСѓ РёР· РєР°СЂС‚РѕС‡РєРё РІС‹С€Рµ' : ''}</div>
          </div>
        ` : ''}
      </div>
    `;
  } catch (e) {
    container.innerHTML = `
      <div class="empty-state">
        <p>${e.message || 'РћС€РёР±РєР° Р·Р°РіСЂСѓР·РєРё QR-РєРѕРґР°'}</p>
        <p class="text-muted">РЈР±РµРґРёС‚РµСЃСЊ, С‡С‚Рѕ Р·Р°РїРѕР»РЅРµРЅ С‚РµР»РµС„РѕРЅ РЎР‘Рџ РёР»Рё Р±Р°РЅРєРѕРІСЃРєРёРµ СЂРµРєРІРёР·РёС‚С‹ РјР°СЃС‚РµСЂР°</p>
        <button class="btn btn-primary mt-12" onclick="navigate('profile-edit')">Р—Р°РїРѕР»РЅРёС‚СЊ СЂРµРєРІРёР·РёС‚С‹</button>
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
      <span class="pay-value">${value}${copyable ? ' <span class="copy-icon">рџ“‹</span>' : ''}</span>
    </div>
  `;
}

function copyToClipboard(text) {
  navigator.clipboard.writeText(text).then(() => toast('РЎРєРѕРїРёСЂРѕРІР°РЅРѕ'))
    .catch(() => {
      // Fallback for older browsers
      const ta = document.createElement('textarea');
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      toast('РЎРєРѕРїРёСЂРѕРІР°РЅРѕ');
    });
}

// в”Ђв”Ђв”Ђ Notifications в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
async function showNotifications() {
  navigate('notifications', {page: state.notifications.page || 1, notificationId: null});
}

async function openNotification(notifId) {
  await openNotificationDetail(notifId);
}

async function loadNotificationsPage(page) {
  const nextPage = Math.max(1, Number(page || 1));
  state.notifications.selectedId = null;
  await loadNotifications({page: nextPage, notificationId: null});
}

async function openNotificationDetail(notifId) {
  const notification = state.notifications.items.find(item => item.id === notifId);
  if (!notification) return;

  state.notifications.selectedId = notifId;
  if (state.screen === 'notifications') {
    state.currentParams = {
      page: state.notifications.page,
      notificationId: state.notifications.selectedId,
    };
  }

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
  if (state.screen === 'notifications') {
    state.currentParams = {
      page: state.notifications.page,
      notificationId: null,
    };
  }
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
  navigateToNotificationTarget(notification);
}


function money(amount) {
  return new Intl.NumberFormat('ru-RU').format(amount || 0) + 'в‚Ѕ';
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
  return {basic:'РџСЂРѕСЃС‚Р°СЏ', std:'РЎС‚Р°РЅРґР°СЂС‚', complex:'РЎР»РѕР¶РЅР°СЏ', hard:'РўСЏР¶С‘Р»Р°СЏ'}[c] || c;
}

function itemRow(item) {
  return `
    <div class="item-row" onclick="navigate('item', {id: ${item.id}, title: '${esc(item.name).substring(0,25)}'})">
      <div class="item-info">
        <div class="item-name">${item.name}</div>
        <div class="item-meta">${item.unit}${item.popular ? ' В· в­ђ' : ''}</div>
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

async function loadNotifications(params = {}) {
  const container = document.getElementById('notifications-list');
  const requestedPage = Math.max(1, Number(params.page || state.notifications.page || 1));
  const offset = (requestedPage - 1) * state.notifications.pageSize;
  const hasExplicitSelection = Object.prototype.hasOwnProperty.call(params, 'notificationId');

  container.innerHTML = `
    <div class="card">
      <div class="card-title">\u0417\u0430\u0433\u0440\u0443\u0436\u0430\u0435\u043c \u0443\u0432\u0435\u0434\u043e\u043c\u043b\u0435\u043d\u0438\u044f...</div>
      <div class="card-subtitle">\u041f\u043e\u0434\u0442\u044f\u0433\u0438\u0432\u0430\u0435\u043c \u0442\u0435\u043a\u0443\u0449\u0443\u044e \u0441\u0442\u0440\u0430\u043d\u0438\u0446\u0443 \u0438 \u0438\u0441\u0442\u043e\u0440\u0438\u044e.</div>
    </div>
  `;

  try {
    const raw = await api(
      'GET',
      `/notifications?limit=${state.notifications.pageSize + 1}&offset=${offset}`
    );
    const items = raw.slice(0, state.notifications.pageSize);

    state.notifications.page = requestedPage;
    state.notifications.hasMore = raw.length > state.notifications.pageSize;
    state.notifications.items = items;

    if (hasExplicitSelection) {
      const nextSelectedId = Number(params.notificationId);
      state.notifications.selectedId = Number.isFinite(nextSelectedId) && nextSelectedId > 0
        ? nextSelectedId
        : null;
    }

    if (!items.some(item => item.id === state.notifications.selectedId)) {
      state.notifications.selectedId = null;
    }

    if (state.screen === 'notifications') {
      state.currentParams = {
        page: state.notifications.page,
        notificationId: state.notifications.selectedId,
      };
    }

    renderNotifications();
  } catch (e) {
    container.innerHTML = `
      <div class="card">
        <div class="card-title">\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0437\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044c \u0443\u0432\u0435\u0434\u043e\u043c\u043b\u0435\u043d\u0438\u044f</div>
        <div class="card-subtitle">${escapeHtml(e.message || '\u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u0435\u0449\u0451 \u0440\u0430\u0437')}</div>
        <button class="btn btn-primary mt-12" onclick="loadNotifications({page: ${requestedPage}, notificationId: null})">
          \u041e\u0431\u043d\u043e\u0432\u0438\u0442\u044c
        </button>
      </div>
    `;
    toast(e.message, true);
  }
}

function renderNotifications() {
  const container = document.getElementById('notifications-list');
  const notification = state.notifications.items.find(item => item.id === state.notifications.selectedId) || null;

  if (state.screen === 'notifications') {
    state.currentParams = {
      page: state.notifications.page,
      notificationId: state.notifications.selectedId,
    };
  }

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
            <div class="card-title">\u0416\u0443\u0440\u043d\u0430\u043b \u0443\u0432\u0435\u0434\u043e\u043c\u043b\u0435\u043d\u0438\u0439</div>
            <div class="card-subtitle">\u0417\u0434\u0435\u0441\u044c \u0441\u043e\u0445\u0440\u0430\u043d\u044f\u0435\u0442\u0441\u044f \u0432\u0441\u044f \u0438\u0441\u0442\u043e\u0440\u0438\u044f, \u043d\u0438\u0447\u0435\u0433\u043e \u043d\u0435 \u043f\u0440\u043e\u043f\u0430\u0434\u0430\u0435\u0442.</div>
          </div>
          <div class="notif-summary-count">${unreadCount}</div>
        </div>
      </div>
      <div class="empty-state card">
        <p>\u0423\u0432\u0435\u0434\u043e\u043c\u043b\u0435\u043d\u0438\u0439 \u043f\u043e\u043a\u0430 \u043d\u0435\u0442</p>
        <p class="text-muted">\u041a\u043e\u0433\u0434\u0430 \u043f\u043e\u044f\u0432\u044f\u0442\u0441\u044f \u0441\u043e\u0431\u044b\u0442\u0438\u044f, \u043e\u043d\u0438 \u043e\u0441\u0442\u0430\u043d\u0443\u0442\u0441\u044f \u0432 \u044d\u0442\u043e\u043c \u0436\u0443\u0440\u043d\u0430\u043b\u0435.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = `
    <div class="card notif-summary-card">
      <div class="notif-summary-top">
        <div>
          <div class="card-title">\u0416\u0443\u0440\u043d\u0430\u043b \u0443\u0432\u0435\u0434\u043e\u043c\u043b\u0435\u043d\u0438\u0439</div>
          <div class="card-subtitle">
            \u0417\u0430\u043f\u0438\u0441\u0438 ${pageStart}-${pageEnd}. \u041d\u0435\u043f\u0440\u043e\u0447\u0438\u0442\u0430\u043d\u043d\u044b\u0445: ${unreadCount}.
          </div>
        </div>
        <div class="notif-summary-count">${unreadCount}</div>
      </div>
      <div class="notif-page-hint">
        \u0421\u0442\u0440\u0430\u043d\u0438\u0446\u0430 ${state.notifications.page}${state.notifications.hasMore ? ' В· \u0434\u043e\u0441\u0442\u0443\u043f\u043d\u044b \u0431\u043e\u043b\u0435\u0435 \u0440\u0430\u043d\u043d\u0438\u0435 \u0443\u0432\u0435\u0434\u043e\u043c\u043b\u0435\u043d\u0438\u044f' : ''}
      </div>
    </div>
    <div class="notif-list">
      ${state.notifications.items.map(n => `
        <div class="notif-row ${n.is_unread ? 'unread' : ''}" onclick="openNotification(${n.id})">
          <div class="notif-icon">${notificationIcon(n.event_type)}</div>
          <div class="notif-body">
            <div class="notif-title">${escapeHtml(n.title || '\u0423\u0432\u0435\u0434\u043e\u043c\u043b\u0435\u043d\u0438\u0435')}</div>
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
        \u2190 \u041d\u043e\u0432\u0435\u0435
      </button>
      <div class="pager-label">\u0421\u0442\u0440\u0430\u043d\u0438\u0446\u0430 ${state.notifications.page}</div>
      <button
        class="btn btn-secondary btn-sm"
        onclick="loadNotificationsPage(${state.notifications.page + 1})"
        ${!state.notifications.hasMore ? 'disabled' : ''}
      >
        \u0421\u0442\u0430\u0440\u0435\u0435 \u2192
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
          ${notification.is_unread ? '\u041d\u043e\u0432\u043e\u0435' : '\u041f\u0440\u043e\u0441\u043c\u043e\u0442\u0440\u0435\u043d\u043e'}
        </span>
        <span class="notif-chip">${formatNotificationDetailTime(notification.created_at)}</span>
        <span class="notif-chip">${escapeHtml(notification.event_type || 'event')}</span>
      </div>
      <div class="notif-detail-title">${escapeHtml(notification.title || '\u0423\u0432\u0435\u0434\u043e\u043c\u043b\u0435\u043d\u0438\u0435')}</div>
      <div class="notif-detail-body">${bodyHtml || '\u0411\u0435\u0437 \u0434\u043e\u043f\u043e\u043b\u043d\u0438\u0442\u0435\u043b\u044c\u043d\u043e\u0433\u043e \u0442\u0435\u043a\u0441\u0442\u0430'}</div>
      ${canOpenTarget ? `
      <div class="notif-target-box">
        <div class="notif-target-label">\u0421\u0432\u044f\u0437\u0430\u043d\u043d\u043e\u0435 \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u0435</div>
        <div class="notif-target-value">${escapeHtml(notification.target_label || '\u041e\u0442\u043a\u0440\u044b\u0442\u044c \u0441\u0432\u044f\u0437\u0430\u043d\u043d\u0443\u044e \u0441\u0443\u0449\u043d\u043e\u0441\u0442\u044c')}</div>
      </div>
      ` : ''}
      <div class="notif-detail-actions">
        ${canOpenTarget ? `
        <button class="btn btn-primary" onclick="openNotificationTarget()">
          ${escapeHtml(notification.target_label || '\u041e\u0442\u043a\u0440\u044b\u0442\u044c')}
        </button>
        ` : ''}
        <button class="btn btn-secondary" onclick="closeNotificationDetail()">\u2190 \u041a \u0441\u043f\u0438\u0441\u043a\u0443</button>
      </div>
    </div>
    <div class="pager">
      <button
        class="btn btn-secondary btn-sm"
        onclick="loadNotificationsPage(${state.notifications.page - 1})"
        ${state.notifications.page === 1 ? 'disabled' : ''}
      >
        \u2190 \u041d\u043e\u0432\u0435\u0435
      </button>
      <div class="pager-label">\u0421\u0442\u0440\u0430\u043d\u0438\u0446\u0430 ${state.notifications.page}</div>
      <button
        class="btn btn-secondary btn-sm"
        onclick="loadNotificationsPage(${state.notifications.page + 1})"
        ${!state.notifications.hasMore ? 'disabled' : ''}
      >
        \u0421\u0442\u0430\u0440\u0435\u0435 \u2192
      </button>
    </div>
  `;
}

function navigateToNotificationTarget(notification) {
  if (notification.entity_type === 'estimate' && notification.entity_id) {
    navigate('estimate', {id: notification.entity_id});
  } else if (notification.entity_type === 'order' && notification.entity_id) {
    navigate('order', {id: notification.entity_id});
  } else if (notification.entity_type === 'discount_request' || notification.event_type === 'discount.requested') {
    navigate('approvals');
  } else {
    toast('\u0414\u043b\u044f \u044d\u0442\u043e\u0433\u043e \u0443\u0432\u0435\u0434\u043e\u043c\u043b\u0435\u043d\u0438\u044f \u043d\u0435\u0442 \u043e\u0442\u0434\u0435\u043b\u044c\u043d\u043e\u0433\u043e \u044d\u043a\u0440\u0430\u043d\u0430', true);
  }
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
