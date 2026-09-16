// 앱 셸: 라우터, 사이드바, 상단 바(갱신 버튼·상태), 테마, 쿼터 표시
import { api, ApiError } from './api.js';
import { h, svg, toast, fmt, store, clear, setBusy } from './ui.js';
import * as dashboardView from './views/dashboard.js';
import * as channelsView from './views/channels.js';
import * as channelView from './views/channel.js';
import * as videosView from './views/videos.js';
import * as settingsView from './views/settings.js';

const NAV = [
    { id: 'dashboard', href: '#/', label: '대시보드', icon: 'dashboard' },
    { id: 'channels', href: '#/channels', label: '채널 관리', icon: 'channels' },
    { id: 'videos', href: '#/videos', label: '영상', icon: 'video' },
    { id: 'settings', href: '#/settings', label: '설정', icon: 'settings' },
];

const ROUTES = [
    { pattern: /^\/?$/, view: dashboardView, nav: 'dashboard' },
    { pattern: /^\/channels\/?$/, view: channelsView, nav: 'channels' },
    { pattern: /^\/channels\/(\d+)\/?$/, view: channelView, nav: 'channels', params: (m) => ({ id: Number(m[1]) }) },
    { pattern: /^\/videos\/?$/, view: videosView, nav: 'videos' },
    { pattern: /^\/settings\/?$/, view: settingsView, nav: 'settings' },
];

const listeners = { refreshDone: new Set() };
let current = { cleanup: null, route: null, params: null };
let status = null;
let wasRunning = false;
let pollTimer = null;
let groupsCache = null;

// ---------- 컨텍스트 (뷰에 전달) ----------
const ctx = {
    api,
    toast,
    setTitle(title, sub = '') {
        document.getElementById('pageTitle').textContent = title;
        document.getElementById('pageSub').textContent = sub;
        document.title = `${title} · ChannelBoard`;
    },
    startRefresh,
    getStatus: () => status,
    async fetchStatus() { await pollStatus(); return status; },
    onRefreshDone(fn) {
        listeners.refreshDone.add(fn);
        return () => listeners.refreshDone.delete(fn);
    },
    async groups(force = false) {
        if (!groupsCache || force) {
            groupsCache = (await api.get('/api/groups')).groups;
        }
        return groupsCache;
    },
    invalidateGroups() { groupsCache = null; },
    navigate(hash) { window.location.hash = hash; },
    rerender() { route(); },
};

// ---------- 라우터 ----------
function parseHash() {
    const raw = window.location.hash.replace(/^#/, '') || '/';
    const [path, query = ''] = raw.split('?');
    return { path, query: new URLSearchParams(query) };
}

async function route() {
    const { path, query } = parseHash();
    let match = null;
    for (const r of ROUTES) {
        const m = path.match(r.pattern);
        if (m) { match = { route: r, params: r.params ? r.params(m) : {} }; break; }
    }
    if (!match) {
        window.location.hash = '#/';
        return;
    }
    match.params.query = query;

    if (current.cleanup) {
        try { current.cleanup(); } catch (e) { console.error(e); }
    }
    current = { cleanup: null, route: match.route, params: match.params };

    document.querySelectorAll('.nav-link').forEach(a => a.classList.toggle('active', a.dataset.nav === match.route.nav));
    closeSidebar();

    const container = document.getElementById('view');
    clear(container);
    container.scrollTop = 0;
    window.scrollTo({ top: 0 });
    try {
        const cleanup = await match.route.view.render(container, match.params, ctx);
        if (typeof cleanup === 'function') current.cleanup = cleanup;
    } catch (error) {
        console.error(error);
        clear(container);
        container.appendChild(h('div', { class: 'callout danger' }, svg('alert'),
            h('div', {}, h('b', {}, '화면을 불러오지 못했습니다. '), error.message || String(error))));
    }
}

// ---------- 사이드바 ----------
function renderNav() {
    const nav = document.getElementById('nav');
    clear(nav);
    NAV.forEach(item => {
        nav.appendChild(h('a', { class: 'nav-link', href: item.href, dataset: { nav: item.id } }, svg(item.icon), item.label));
    });
}

function openSidebar() {
    document.getElementById('sidebar').classList.add('open');
    document.getElementById('sidebarBackdrop').classList.add('open');
}
function closeSidebar() {
    document.getElementById('sidebar').classList.remove('open');
    document.getElementById('sidebarBackdrop').classList.remove('open');
}

// ---------- 테마 ----------
function applyTheme(pref) {
    const dark = pref === 'dark' || (pref === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
    const btn = document.getElementById('themeToggle');
    clear(btn);
    btn.appendChild(svg(dark ? 'sun' : 'moon'));
    btn.appendChild(document.createTextNode(dark ? '라이트 모드로 전환' : '다크 모드로 전환'));
    window.dispatchEvent(new CustomEvent('cb:theme', { detail: { dark } }));
}

export function setThemePref(pref) {
    store.set('theme', pref);
    try { localStorage.setItem('cb:theme', pref); } catch (e) { /* 무시 */ }
    applyTheme(pref);
}

function initTheme() {
    let pref = 'system';
    try { pref = localStorage.getItem('cb:theme') || 'system'; } catch (e) { /* 무시 */ }
    applyTheme(pref);
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
        let p = 'system';
        try { p = localStorage.getItem('cb:theme') || 'system'; } catch (e) { /* 무시 */ }
        if (p === 'system') applyTheme('system');
    });
    document.getElementById('themeToggle').addEventListener('click', () => {
        const dark = document.documentElement.getAttribute('data-theme') === 'dark';
        setThemePref(dark ? 'light' : 'dark');
    });
}
ctx.setThemePref = setThemePref;

// ---------- 갱신 상태 ----------
async function pollStatus() {
    try {
        status = await api.get('/api/refresh/status');
    } catch (error) {
        return;
    }
    renderStatus();
    const running = status.state.running;
    if (wasRunning && !running) {
        announceRefreshResult(status.last_run);
        listeners.refreshDone.forEach(fn => { try { fn(status); } catch (e) { console.error(e); } });
    }
    wasRunning = running;
    schedulePoll(running ? 1200 : 60000);
}

function schedulePoll(ms) {
    clearTimeout(pollTimer);
    pollTimer = setTimeout(pollStatus, ms);
}

function renderStatus() {
    if (!status) return;
    const { state, last_success, quota, next_run_at } = status;
    const btn = document.getElementById('refreshBtn');
    const line = document.getElementById('progressLine');
    const fill = document.getElementById('progressFill');
    const last = document.getElementById('lastRefresh');

    clear(btn);
    if (state.running) {
        btn.disabled = true;
        btn.appendChild(svg('refresh'));
        const label = state.total ? `${state.message} ${state.done}/${state.total}` : (state.message || '갱신 중');
        btn.appendChild(document.createTextNode(label));
        line.hidden = false;
        if (state.total) {
            fill.classList.remove('indeterminate');
            fill.style.width = `${Math.round((state.done / state.total) * 100)}%`;
        } else {
            fill.classList.add('indeterminate');
        }
    } else {
        btn.disabled = false;
        btn.appendChild(svg('refresh'));
        btn.appendChild(document.createTextNode('지금 업데이트'));
        line.hidden = true;
        fill.classList.remove('indeterminate');
        fill.style.width = '0%';
    }

    if (last_success && last_success.finished_at) {
        last.textContent = `마지막 업데이트 ${fmt.relative(last_success.finished_at)}`;
        last.title = fmt.datetime(last_success.finished_at);
    } else {
        last.textContent = '아직 업데이트 안 함';
        last.title = '';
    }

    const used = quota.used_today || 0;
    const total = quota.per_key * Math.max(quota.key_count, 1);
    document.getElementById('quotaUsed').textContent = fmt.int(used);
    document.getElementById('quotaTotal').textContent = fmt.int(total);
    const ratio = Math.min(1, used / total);
    const meter = document.getElementById('quotaFill');
    meter.style.width = `${Math.round(ratio * 100)}%`;
    meter.classList.toggle('warn', ratio >= 0.7 && ratio < 0.9);
    meter.classList.toggle('danger', ratio >= 0.9);
    const next = document.getElementById('quotaNext');
    if (quota.key_count === 0) {
        next.textContent = 'API 키 없음';
    } else if (next_run_at) {
        const when = new Date(next_run_at);
        next.textContent = when.getTime() <= Date.now() ? '자동 갱신 대기 중' : `다음 자동 갱신 ${fmt.datetime(next_run_at)}`;
    } else {
        next.textContent = '자동 갱신 꺼짐';
    }
}

function announceRefreshResult(run) {
    if (!run) return;
    if (run.status === 'success') {
        toast(`업데이트 완료 · 채널 ${fmt.int(run.channels_updated)}개, 영상 ${fmt.int(run.videos_updated)}개 · 쿼터 ${fmt.int(run.quota_used)} units`, 'success');
    } else if (run.status === 'partial') {
        toast(`일부만 업데이트됨 (채널 ${run.channels_updated}/${run.channels_total}) · ${run.error || ''}`, 'warn', { timeout: 8000 });
    } else if (run.status === 'failed') {
        toast(`업데이트 실패: ${run.error || '알 수 없는 오류'}`, 'error', { timeout: 8000 });
    }
}

async function startRefresh(options = { scope: 'all' }) {
    const btn = document.getElementById('refreshBtn');
    setBusy(btn, true);
    try {
        await api.post('/api/refresh', options);
        toast('YouTube에서 최신 현황을 가져오는 중입니다…', 'info', { timeout: 2500 });
        wasRunning = true;
        await pollStatus();
    } catch (error) {
        if (error.status === 409) {
            toast('이미 업데이트가 진행 중입니다.', 'warn');
        } else if (error.status === 400) {
            toast(error.message, 'error', { timeout: 7000 });
            if (/API 키/.test(error.message)) window.location.hash = '#/settings';
        } else {
            toast(error.message, 'error');
        }
        await pollStatus();
    } finally {
        setBusy(btn, false);
        renderStatus();
    }
}

// ---------- 부트 ----------
function boot() {
    renderNav();
    initTheme();
    document.getElementById('menuBtn').appendChild(svg('menu'));
    document.getElementById('menuBtn').addEventListener('click', openSidebar);
    document.getElementById('sidebarBackdrop').addEventListener('click', closeSidebar);
    document.getElementById('refreshBtn').addEventListener('click', () => startRefresh({ scope: 'all' }));
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') closeSidebar();
    });
    window.addEventListener('hashchange', route);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) pollStatus(); });
    pollStatus();
    route();
}

boot();
