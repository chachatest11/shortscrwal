// 설정: API 키 · 자동 갱신 · 데이터 · 외관
import { h, svg, fmt, badge, clear, toast, confirmDialog, setBusy, store } from '../ui.js';

export const title = '설정';

export async function render(container, params, ctx) {
    ctx.setTitle('설정', 'API 키 · 자동 갱신 · 데이터 · 외관');
    const keysCard = h('div', { class: 'card' });
    const refreshCard = h('div', { class: 'card' });
    const dataCard = h('div', { class: 'card' });
    const lookCard = h('div', { class: 'card' });
    container.append(h('div', { class: 'stack', style: { gap: '14px' } }, keysCard, refreshCard, lookCard, dataCard));

    let settings = null, info = null;

    async function loadAll() {
        try {
            const [s, k, r] = await Promise.all([ctx.api.get('/api/settings'), ctx.api.get('/api/keys'), ctx.api.get('/api/refresh/runs', { limit: 10 })]);
            settings = s.settings; info = s.info;
            renderKeys(k); renderRefresh(); renderLook(); renderData(r.runs);
        } catch (error) { toast(error.message, 'error'); }
    }

    // ---------- API 키 ----------
    function renderKeys(k) {
        clear(keysCard);
        keysCard.appendChild(h('div', { class: 'card-header' }, h('h3', {}, svg('key'), 'YouTube API 키'),
            h('span', { class: 'card-sub' }, `오늘 사용 ${fmt.int(k.used_today_total)} / ${fmt.int(k.daily_quota_per_key * Math.max(k.keys.length, 1))} units (${k.quota_date} 기준)`)));
        const body = h('div', { class: 'card-body stack', style: { gap: '14px' } });
        keysCard.appendChild(body);

        if (!k.keys.length) {
            body.appendChild(h('div', { class: 'callout info' }, svg('info'), h('div', {},
                h('b', {}, 'API 키가 없습니다. '), 'Google Cloud Console에서 YouTube Data API v3를 활성화하고 API 키를 만들어 아래에 추가하세요. 키 하나로 하루 10,000 units를 쓸 수 있고, 채널 50개 갱신에 1 unit이 듭니다.')));
        } else {
            const table = h('table', { class: 'table' }, h('thead', {}, h('tr', {}, h('th', {}, '키'), h('th', {}, '이름'), h('th', {}, '상태'), h('th', { class: 'num' }, '오늘 사용'), h('th', {}, '마지막 사용'), h('th', {}, ''))));
            const tbody = h('tbody');
            k.keys.forEach(key => {
                const toggle = h('input', { type: 'checkbox', checked: key.is_active });
                toggle.addEventListener('change', async () => {
                    try { await ctx.api.patch(`/api/keys/${key.id}`, { is_active: toggle.checked }); loadAll(); ctx.fetchStatus(); }
                    catch (error) { toast(error.message, 'error'); toggle.checked = !toggle.checked; }
                });
                const status = key.quota_exceeded ? badge('쿼터 초과', 'danger', 'alert') : key.is_active ? badge('사용 중', 'good', 'check') : badge('비활성', 'outline');
                tbody.appendChild(h('tr', {},
                    h('td', { class: 'mono' }, key.masked), h('td', {}, key.name || h('span', { class: 'muted' }, '—')), h('td', {}, status),
                    h('td', { class: 'num' }, fmt.int(key.used_today)), h('td', { class: 'muted' }, key.last_used_at ? fmt.relative(key.last_used_at) : '—'),
                    h('td', {}, h('div', { class: 'row', style: { gap: '6px', flexWrap: 'nowrap', justifyContent: 'flex-end' } },
                        h('label', { class: 'switch', title: '활성/비활성' }, toggle, h('span', { class: 'track' })),
                        h('button', { class: 'btn btn-secondary btn-sm', type: 'button', onclick: async (e) => {
                            setBusy(e.currentTarget, true);
                            try { const r = await ctx.api.post(`/api/keys/${key.id}/test`); toast(r.ok ? '키가 정상 동작합니다 (1 unit 사용)' : `키 오류: ${r.error}`, r.ok ? 'success' : 'error', { timeout: 6000 }); loadAll(); }
                            catch (error) { toast(error.message, 'error'); } finally { setBusy(e.currentTarget, false); }
                        } }, '테스트'),
                        key.quota_exceeded ? h('button', { class: 'btn btn-secondary btn-sm', type: 'button', onclick: async () => { await ctx.api.post(`/api/keys/${key.id}/reset`); toast('쿼터 상태를 초기화했습니다', 'success'); loadAll(); ctx.fetchStatus(); } }, '초기화') : null,
                        h('button', { class: 'icon-btn', type: 'button', title: '삭제', onclick: async () => {
                            if (await confirmDialog({ title: 'API 키 삭제', message: `${key.masked} 키를 삭제합니다.`, confirmText: '삭제', danger: true })) {
                                await ctx.api.delete(`/api/keys/${key.id}`); toast('삭제했습니다', 'success'); loadAll(); ctx.fetchStatus();
                            } } }, svg('trash')))),
                ));
            });
            table.appendChild(tbody);
            body.appendChild(h('div', { class: 'table-wrap' }, table));
        }

        const keyInput = h('input', { class: 'input', placeholder: 'AIza… 로 시작하는 API 키', autocomplete: 'off', spellcheck: 'false' });
        const nameInput = h('input', { class: 'input', placeholder: '이름 (선택, 예: 메인 프로젝트)' });
        const addBtn = h('button', { class: 'btn btn-primary', type: 'button' }, svg('plus'), '키 추가');
        addBtn.addEventListener('click', async () => {
            const api_key = keyInput.value.trim();
            if (!api_key) return toast('API 키를 입력하세요', 'warn');
            setBusy(addBtn, true);
            try {
                await ctx.api.post('/api/keys', { api_key, name: nameInput.value.trim() || null, verify: true });
                toast('키를 확인하고 추가했습니다', 'success'); keyInput.value = ''; nameInput.value = '';
                loadAll(); ctx.fetchStatus();
            } catch (error) { toast(error.message, 'error', { timeout: 8000 }); }
            finally { setBusy(addBtn, false); }
        });
        keyInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') addBtn.click(); });
        body.appendChild(h('div', { class: 'row', style: { alignItems: 'flex-end' } },
            h('div', { class: 'field', style: { flex: 2, minWidth: '260px' } }, h('label', {}, '새 API 키'), keyInput),
            h('div', { class: 'field', style: { flex: 1, minWidth: '160px' } }, h('label', {}, '이름'), nameInput), addBtn));
        body.appendChild(h('details', { class: 'muted', style: { fontSize: '13px' } }, h('summary', { style: { cursor: 'pointer' } }, 'API 키 만드는 방법'),
            h('ol', { style: { margin: '8px 0 0 18px', lineHeight: 1.8 } },
                h('li', {}, h('a', { href: 'https://console.cloud.google.com/', target: '_blank', rel: 'noopener' }, 'Google Cloud Console'), '에서 프로젝트를 만들거나 선택'),
                h('li', {}, '"API 및 서비스 → 라이브러리"에서 YouTube Data API v3 를 사용 설정'),
                h('li', {}, '"사용자 인증 정보 → 사용자 인증 정보 만들기 → API 키"'),
                h('li', {}, '만든 키를 위에 붙여넣고 "키 추가" (등록 시 1 unit 으로 동작 여부를 확인합니다)'),
                h('li', {}, '키를 여러 개 등록하면 하나가 쿼터를 다 쓸 때 자동으로 다음 키를 씁니다'))));
    }

    // ---------- 자동 갱신 ----------
    function renderRefresh() {
        clear(refreshCard);
        const s = settings;
        const enabled = h('input', { type: 'checkbox', checked: s.auto_refresh_enabled });
        const interval = h('select', { class: 'select' }, ...[1, 3, 6, 12, 24].map(v => h('option', { value: String(v), selected: v === s.auto_refresh_interval_hours }, `${v}시간마다`)));
        const maxVideos = h('input', { class: 'input', type: 'number', min: '1', max: '50', value: s.max_videos_per_channel });
        const windowDays = h('select', { class: 'select' }, ...[30, 90, 180, 365].map(v => h('option', { value: String(v), selected: v === s.video_stats_window_days }, `${v}일`)));
        const staleDays = h('input', { class: 'input', type: 'number', min: '1', max: '90', value: s.stale_days });
        const multiplier = h('input', { class: 'input', type: 'number', min: '1.1', max: '10', step: '0.05', value: s.outlier_multiplier });
        const shortsMax = h('input', { class: 'input', type: 'number', min: '30', max: '600', value: s.shorts_max_seconds });
        const saveBtn = h('button', { class: 'btn btn-primary', type: 'button' }, '저장');
        const nextInfo = h('span', { class: 'muted', style: { fontSize: '12.5px' } },
            info.next_run_at ? `다음 자동 갱신: ${fmt.datetime(info.next_run_at)}` : (s.auto_refresh_enabled ? '자동 갱신 대상이 없습니다 (API 키와 활성 채널 필요)' : '자동 갱신 꺼짐'));
        saveBtn.addEventListener('click', async () => {
            setBusy(saveBtn, true);
            try {
                await ctx.api.put('/api/settings', { values: {
                    auto_refresh_enabled: enabled.checked, auto_refresh_interval_hours: Number(interval.value), max_videos_per_channel: Number(maxVideos.value),
                    video_stats_window_days: Number(windowDays.value), stale_days: Number(staleDays.value), outlier_multiplier: Number(multiplier.value), shorts_max_seconds: Number(shortsMax.value) } });
                toast('설정을 저장했습니다', 'success'); await loadAll(); ctx.fetchStatus();
            } catch (error) { toast(error.message, 'error', { timeout: 6000 }); }
            finally { setBusy(saveBtn, false); }
        });
        const field = (label, el, hint) => h('div', { class: 'field' }, h('label', {}, label), el, hint ? h('span', { class: 'muted', style: { fontSize: '12px' } }, hint) : null);
        refreshCard.append(
            h('div', { class: 'card-header' }, h('h3', {}, svg('refresh'), '갱신 설정'), nextInfo),
            h('div', { class: 'card-body stack', style: { gap: '16px' } },
                h('label', { class: 'row', style: { gap: '10px', fontSize: '14px' } }, h('span', { class: 'switch' }, enabled, h('span', { class: 'track' })),
                    h('span', {}, h('b', {}, '자동 갱신'), h('span', { class: 'muted' }, ' — 서버가 켜져 있는 동안 주기적으로 모든 활성 채널을 갱신합니다'))),
                h('div', { class: 'grid grid-3' },
                    field('갱신 주기', interval, '채널 30개 기준 1회 약 40 units'),
                    field('채널당 최근 영상 수', maxVideos, '갱신할 때 채널마다 가져올 최신 영상 수 (1~50)'),
                    field('영상 통계 재수집 기간', windowDays, '이 기간 안에 게시된 영상은 조회수를 계속 갱신'),
                    field('업로드 공백 기준 (일)', staleDays, '이 일수 이상 업로드가 없으면 경고'),
                    field('급상승 기준 배수', multiplier, '채널 평소 조회수/일 중앙값 대비'),
                    field('쇼츠 판정 최대 길이 (초)', shortsMax, '이 길이 이하 영상을 쇼츠로 표시')),
                h('div', {}, saveBtn)));
    }

    // ---------- 외관 ----------
    function renderLook() {
        clear(lookCard);
        let pref = 'system';
        try { pref = localStorage.getItem('cb:theme') || 'system'; } catch (e) { /* 무시 */ }
        const seg = h('div', { class: 'segment' });
        [['system', '시스템 설정'], ['light', '라이트'], ['dark', '다크']].forEach(([v, l]) => {
            const btn = h('button', { type: 'button', class: v === pref ? 'active' : '' }, l);
            btn.addEventListener('click', () => { ctx.setThemePref(v); seg.querySelectorAll('button').forEach(b => b.classList.toggle('active', b === btn)); });
            seg.appendChild(btn);
        });
        lookCard.append(h('div', { class: 'card-header' }, h('h3', {}, svg('sun'), '외관')),
            h('div', { class: 'card-body row', style: { gap: '14px' } }, h('span', { style: { fontSize: '14px' } }, '테마'), seg));
    }

    // ---------- 데이터 ----------
    function renderData(runs) {
        clear(dataCard);
        const c = info.counts;
        const importBtn = info.legacy_db_exists ? h('button', { class: 'btn btn-secondary btn-sm', type: 'button', onclick: async (e) => {
            setBusy(e.currentTarget, true);
            try { const r = await ctx.api.post('/api/settings/import-legacy'); toast(`가져오기 완료: 그룹 ${r.imported.groups}, 채널 ${r.imported.channels}, 키 ${r.imported.api_keys}, 스냅샷 ${r.imported.snapshots}`, 'success', { timeout: 7000 }); ctx.invalidateGroups(); loadAll(); }
            catch (error) { toast(error.message, 'error'); } finally { setBusy(e.currentTarget, false); }
        } }, svg('database'), '이전 버전 데이터 가져오기') : null;

        const statusBadge = (st) => st === 'success' ? badge('성공', 'good', 'check') : st === 'partial' ? badge('일부', 'warn', 'alert') : st === 'running' ? badge('실행 중', 'info', 'refresh') : badge('실패', 'danger', 'xCircle');
        const runsTable = runs.length ? h('table', { class: 'table' }, h('thead', {}, h('tr', {}, h('th', {}, '시작'), h('th', {}, '상태'), h('th', {}, '유형'), h('th', { class: 'num' }, '채널'), h('th', { class: 'num' }, '영상'), h('th', { class: 'num' }, '쿼터'), h('th', {}, '메시지'))),
            h('tbody', {}, ...runs.map(r => h('tr', {}, h('td', { title: r.started_at }, fmt.datetime(r.started_at)), h('td', {}, statusBadge(r.status)),
                h('td', { class: 'muted' }, r.trigger === 'auto' ? '자동' : '수동', r.scope !== 'all' ? ` (${r.scope})` : ''),
                h('td', { class: 'num' }, `${r.channels_updated}/${r.channels_total}`), h('td', { class: 'num' }, fmt.int(r.videos_updated)), h('td', { class: 'num' }, fmt.int(r.quota_used)),
                h('td', { class: 'muted', style: { maxWidth: '320px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }, title: r.error || '' }, r.error || '')))))
            : h('div', { class: 'empty-inline' }, '아직 갱신 기록이 없습니다.');

        dataCard.append(
            h('div', { class: 'card-header' }, h('h3', {}, svg('database'), '데이터'), importBtn),
            h('div', { class: 'card-body stack', style: { gap: '14px' } },
                h('div', { class: 'grid grid-3', style: { gap: '10px' } },
                    stat('채널', `${fmt.int(c.channels)} (활성 ${fmt.int(c.active_channels)})`), stat('영상', fmt.int(c.videos)), stat('통계 기록', fmt.int(c.snapshots)),
                    stat('그룹', fmt.int(c.groups)), stat('API 키', fmt.int(c.keys)), stat('DB 크기', fmt.bytes(info.db_size_bytes))),
                h('div', { class: 'muted mono', style: { fontSize: '12px' } }, `DB: ${info.db_path}`),
                info.legacy_db_exists ? h('div', { class: 'callout info' }, svg('info'), h('div', {}, '이전 버전(쇼츠 수집기) 데이터베이스가 있습니다. ', info.legacy_imported_at ? `마지막 가져오기: ${fmt.datetime(info.legacy_imported_at)}` : '아직 가져오지 않았습니다.')) : null,
                h('div', {}, h('div', { class: 'section-title' }, '최근 갱신 기록'), h('div', { class: 'table-wrap' }, runsTable)),
                h('div', { class: 'muted', style: { fontSize: '12.5px' } }, `ChannelBoard v${info.version} · 기획안: docs/PLAN.md · 공개 API 키만으로 동작하며 시청 시간·수익 등 애널리틱스 데이터는 포함하지 않습니다.`)));
    }

    function stat(label, value) {
        return h('div', { style: { padding: '10px 12px', background: 'var(--surface-2)', borderRadius: 'var(--r)' } }, h('div', { class: 'muted', style: { fontSize: '12px' } }, label), h('div', { style: { fontWeight: 700, fontSize: '15px' } }, value));
    }

    await loadAll();
    const off = ctx.onRefreshDone(() => loadAll());
    return () => off();
}
