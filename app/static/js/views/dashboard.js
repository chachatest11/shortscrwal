// 대시보드: 요약 KPI · 인사이트 · 최근 업로드 · 채널 현황 표
import { h, svg, fmt, deltaEl, avatarEl, thumbEl, badge, uploadStatus, sparkline, emptyState, store, clear,
         periodLabel, youtubeVideoUrl, youtubeChannelUrl, debounce } from '../ui.js';

export const title = '대시보드';

const PERIODS = [1, 7, 30, 90];
const SORTS = {
    subs: { label: '구독자', key: (c) => c.subscriber_count ?? -1 },
    subs_delta: { label: '구독자 증감', key: (c) => c.delta?.subscriber_count ?? -Infinity },
    views_delta: { label: '조회수 증감', key: (c) => c.delta?.view_count ?? -Infinity },
    uploads: { label: '업로드', key: (c) => c.uploads_in_period },
    latest: { label: '최근 업로드', key: (c) => -(c.days_since_upload ?? 9999) },
    title: { label: '이름', key: (c) => c.title, asc: true },
};

export async function render(container, params, ctx) {
    const state = {
        days: store.get('dash.days', 7),
        groupId: store.get('dash.group', 0),
        query: '',
        sort: store.get('dash.sort', 'subs'),
        sortDesc: store.get('dash.sortDesc', true),
        data: null,
    };
    ctx.setTitle('대시보드', '');

    const groups = await ctx.groups();
    const filterRow = buildFilterRow(state, groups, () => load(), () => renderTable());
    const onboarding = h('div', { class: 'stack', style: { marginBottom: '18px' } });
    const kpiRow = h('div', { class: 'grid grid-kpi', style: { marginBottom: '14px' } });
    const insightsCard = h('div', { class: 'card' });
    const latestCard = h('div', { class: 'card' });
    const middle = h('div', { class: 'grid grid-2 dash-middle', style: { marginBottom: '14px' } }, insightsCard, latestCard);
    const tableCard = h('div', { class: 'card' });
    container.append(filterRow, onboarding, kpiRow, middle, tableCard);

    async function load() {
        container.classList.add('is-loading');
        try {
            state.data = await ctx.api.get('/api/overview', { group_id: state.groupId, days: state.days });
            renderAll();
        } catch (error) {
            ctx.toast(error.message, 'error');
        } finally {
            container.classList.remove('is-loading');
        }
    }

    function renderAll() {
        const d = state.data;
        const groupName = state.groupId ? (groups.find(g => g.id === state.groupId)?.name || '') : '전체';
        ctx.setTitle('대시보드', `${groupName} · 채널 ${d.summary.channel_count}개 · 최근 ${periodLabel(state.days)} 기준`);
        renderOnboarding(onboarding, d, ctx);
        renderKpis(kpiRow, d);
        renderInsights(insightsCard, d, ctx);
        renderLatest(latestCard, d);
        renderTable();
    }

    function renderTable() {
        if (state.data) buildTable(tableCard, state, ctx);
    }

    const off = ctx.onRefreshDone(() => load());
    await load();
    return () => off();
}

// ---------- 필터 ----------
function buildFilterRow(state, groups, reload, resort) {
    const seg = h('div', { class: 'segment', role: 'group', 'aria-label': '기간' });
    PERIODS.forEach(days => {
        const btn = h('button', { type: 'button', class: days === state.days ? 'active' : '' }, periodLabel(days));
        btn.addEventListener('click', () => {
            state.days = days;
            store.set('dash.days', days);
            seg.querySelectorAll('button').forEach(b => b.classList.toggle('active', b === btn));
            reload();
        });
        seg.appendChild(btn);
    });

    const groupSelect = h('select', { class: 'select select-sm' }, h('option', { value: '0' }, '전체 그룹'),
        ...groups.map(g => h('option', { value: String(g.id), selected: g.id === state.groupId }, `${g.name} (${g.active_count})`)));
    groupSelect.addEventListener('change', () => {
        state.groupId = Number(groupSelect.value);
        store.set('dash.group', state.groupId);
        reload();
    });

    const search = h('input', { class: 'input input-sm', type: 'search', placeholder: '채널 이름 검색' });
    search.addEventListener('input', debounce(() => { state.query = search.value.trim().toLowerCase(); resort(); }, 150));

    const exportBtn = h('a', { class: 'btn btn-secondary btn-sm', href: '#' }, svg('download'), 'CSV');
    exportBtn.addEventListener('click', (e) => {
        e.preventDefault();
        window.location.href = `/api/export/channels.csv?group_id=${state.groupId}&days=${state.days}`;
    });

    return h('div', { class: 'filter-row' },
        h('div', { class: 'field' }, h('span', { class: 'field-label' }, '기간'), seg),
        h('div', { class: 'field' }, h('label', { for: 'dashGroup' }, '그룹'), Object.assign(groupSelect, { id: 'dashGroup' })),
        h('div', { class: 'field grow' }, h('label', { for: 'dashSearch' }, '검색'),
            h('div', { class: 'search-box' }, svg('search'), Object.assign(search, { id: 'dashSearch' }))),
        h('div', { class: 'field' }, h('span', { class: 'field-label' }, ' '), exportBtn),
    );
}

// ---------- 온보딩 ----------
function renderOnboarding(el, data, ctx) {
    clear(el);
    const status = ctx.getStatus();
    const hasKey = status ? status.quota.key_count > 0 : true;
    const hasChannels = data.summary.channel_count > 0;
    const refreshed = !!data.last_refresh_at;
    if (hasKey && hasChannels && refreshed) return;

    const step = (no, done, title, sub, action) => h('div', { class: `step${done ? ' done' : ''}` },
        h('span', { class: 'step-no' }, done ? '✓' : String(no)),
        h('div', { class: 'step-body' }, h('span', { class: 'step-title' }, title), h('span', { class: 'step-sub' }, sub)),
        !done && action ? action : null);

    el.appendChild(h('div', { class: 'card' },
        h('div', { class: 'card-header' }, h('h3', {}, svg('sparkles'), '시작하기'),
            h('span', { class: 'card-sub' }, '세 단계면 대시보드가 채워집니다')),
        h('div', { class: 'card-body' }, h('div', { class: 'pill-steps' },
            step(1, hasKey, 'YouTube API 키 등록', 'Google Cloud Console에서 Data API v3 키를 만들어 설정에 추가',
                h('a', { class: 'btn btn-primary btn-sm', href: '#/settings' }, '설정으로')),
            step(2, hasChannels, '채널 추가', '채널 URL, @핸들, 채널 ID, 영상 URL을 붙여넣기',
                h('a', { class: 'btn btn-primary btn-sm', href: '#/channels?add=1' }, '채널 추가')),
            step(3, refreshed, '첫 업데이트', '"지금 업데이트"를 누르면 구독자·조회수·최근 영상을 수집',
                h('button', { class: 'btn btn-primary btn-sm', type: 'button', onclick: () => ctx.startRefresh({ scope: 'all' }) }, '지금 업데이트')),
        ))));
}

// ---------- KPI ----------
function kpi(label, iconName, value, foot, extra) {
    return h('div', { class: 'card kpi' },
        h('div', { class: 'kpi-label' }, svg(iconName), label),
        h('div', { class: 'kpi-value', title: typeof value === 'string' ? value : '' }, value),
        foot ? h('div', { class: `kpi-foot${extra?.warn ? ' warn' : ''}` }, foot) : h('div', { class: 'kpi-foot' }),
    );
}

function renderKpis(row, data) {
    clear(row);
    const s = data.summary;
    const p = periodLabel(data.period_days);
    const baseNote = s.channels_with_baseline > 0 && s.channels_with_baseline < s.channel_count
        ? h('span', { class: 'muted' }, `${s.channels_with_baseline}/${s.channel_count}개 채널 기준`) : null;
    const vs = h('span', { class: 'muted' }, `vs ${p} 전`);

    row.appendChild(kpi('채널', 'channels', fmt.int(s.channel_count),
        s.channels_never_refreshed ? `${s.channels_never_refreshed}개 채널 아직 미갱신` : '활성 채널', { warn: s.channels_never_refreshed > 0 }));
    row.appendChild(kpi('총 구독자', 'users', fmt.compact(s.subscriber_count),
        [deltaEl(s.subscriber_delta), vs.cloneNode(true), s.channels_subscriber_hidden ? h('span', { class: 'muted' }, `비공개 ${s.channels_subscriber_hidden}개 제외`) : baseNote]));
    row.appendChild(kpi('총 조회수', 'eye', fmt.compact(s.view_count), [deltaEl(s.view_delta), vs.cloneNode(true)]));
    row.appendChild(kpi('총 영상', 'film', fmt.int(s.video_count), [deltaEl(s.video_delta), vs.cloneNode(true)]));
    const uploadsFoot = s.channels_without_upload > 0
        ? [svg('alert'), `업로드 없는 채널 ${s.channels_without_upload}개`]
        : (s.channel_count ? '모든 채널이 업로드함' : '');
    const uploadsTile = kpi(`${p} 업로드`, 'upload', fmt.int(s.uploads_in_period), uploadsFoot, { warn: s.channels_without_upload > 0 });
    if (s.uploads_in_period > 0) {
        uploadsTile.appendChild(h('div', { class: 'kpi-foot' }, `업로드 영상 조회수 ${fmt.compact(s.period_upload_views)}`));
    }
    row.appendChild(uploadsTile);
}

// ---------- 인사이트 ----------
function renderInsights(card, data, ctx) {
    clear(card);
    const ins = data.insights;
    const total = ins.stale.length + ins.declining.length + ins.rising.length + ins.milestones.length + ins.uploaded_today.length;
    card.appendChild(h('div', { class: 'card-header' }, h('h3', {}, svg('sparkles'), '인사이트'),
        h('span', { class: 'card-sub' }, total ? `${total}건` : '')));
    const body = h('div', { class: 'list insight-list' });
    card.appendChild(body);

    if (!data.last_refresh_at) {
        body.appendChild(h('div', { class: 'empty-inline' }, '첫 업데이트 후에 채널 신호가 여기에 표시됩니다.'));
        return;
    }
    if (total === 0) {
        body.appendChild(h('div', { class: 'empty-inline' }, '지금은 특별한 신호가 없습니다. 모든 채널이 정상 범위입니다.'));
        return;
    }

    const item = (kind, iconName, title, sub, end, href) => {
        const el = h('a', { class: 'list-item clickable', href, style: { color: 'inherit', textDecoration: 'none' } },
            h('span', { class: `insight-icon ${kind}` }, svg(iconName)),
            h('div', { class: 'list-body' }, h('span', { class: 'list-title' }, title), h('span', { class: 'list-sub' }, sub)),
            end ? h('div', { class: 'list-end' }, end) : null);
        return el;
    };
    const section = (label, items) => {
        if (!items.length) return;
        body.appendChild(h('div', { class: 'insight-section' }, label));
        items.forEach(x => body.appendChild(x));
    };

    section('업로드 공백', ins.stale.slice(0, 5).map(x => item('warn', 'alert', x.title,
        x.has_videos ? `${Math.floor(x.days_since_upload)}일째 새 영상이 없습니다` : '수집된 영상이 없습니다',
        x.has_videos ? h('span', { class: 'stat' }, `${Math.floor(x.days_since_upload)}일`) : null, `#/channels/${x.channel_id}`)));
    section('구독자 감소', ins.declining.slice(0, 5).map(x => item('danger', 'trendingDown', x.title,
        `${periodLabel(data.period_days)} 동안 구독자 감소 · 현재 ${fmt.compact(x.subscriber_count)}`,
        deltaEl(x.subscriber_delta), `#/channels/${x.channel_id}`)));
    section('급상승 영상', ins.rising.slice(0, 5).map(x => {
        const sub = x.reason === 'baseline'
            ? `${x.channel_title} · 채널 평소의 ${fmt.multiple(x.ratio)} · 조회수/일 ${fmt.compact(x.views_per_day)}`
            : `${x.channel_title} · 최근 갱신 사이 +${fmt.compact(x.view_delta)} · 조회수 ${fmt.compact(x.view_count)}`;
        return item('good', 'trendingUp', x.title, sub, h('span', { class: 'stat' }, fmt.compact(x.view_count)), youtubeVideoUrl(x.youtube_id));
    }));
    section('마일스톤', ins.milestones.slice(0, 5).map(x => item(x.achieved ? 'good' : 'info', 'award', x.title,
        x.achieved ? `구독자 ${fmt.compact(x.milestone)} 달성! 현재 ${fmt.int(x.subscriber_count)}`
                   : `${fmt.compact(x.milestone)}까지 ${fmt.int(x.remaining)}명 남음`,
        h('span', { class: 'stat' }, fmt.compact(x.subscriber_count)), `#/channels/${x.channel_id}`)));
    section('오늘 업로드', ins.uploaded_today.slice(0, 5).map(x => item('info', 'zap', x.title,
        `${x.video_title} · ${fmt.relative(x.published_at)}`, h('span', { class: 'stat' }, fmt.compact(x.view_count)), youtubeVideoUrl(x.video_youtube_id))));
    body.querySelectorAll('.insight-list a').forEach(a => {
        if (a.getAttribute('href').startsWith('http')) { a.target = '_blank'; a.rel = 'noopener'; }
    });
}

// ---------- 최근 업로드 ----------
function renderLatest(card, data) {
    clear(card);
    card.appendChild(h('div', { class: 'card-header' }, h('h3', {}, svg('upload'), '최근 업로드'),
        h('a', { class: 'card-sub', href: '#/videos' }, '전체 영상 보기 →')));
    const list = h('div', { class: 'list' });
    card.appendChild(list);
    if (!data.latest_videos.length) {
        list.appendChild(h('div', { class: 'empty-inline' }, '수집된 영상이 없습니다. 업데이트 후 최근 업로드가 표시됩니다.'));
        return;
    }
    data.latest_videos.forEach(v => {
        list.appendChild(h('a', { class: 'list-item clickable', href: youtubeVideoUrl(v.youtube_id), target: '_blank', rel: 'noopener',
                                 style: { color: 'inherit', textDecoration: 'none' } },
            thumbEl(v),
            h('div', { class: 'list-body' },
                h('span', { class: 'list-title', title: v.title }, v.title),
                h('span', { class: 'list-sub' }, `${v.channel_title} · ${fmt.relative(v.published_at)}`, v.is_short ? ' · ' : '', v.is_short ? badge('쇼츠', 'outline') : null)),
            h('div', { class: 'list-end' }, h('div', { class: 'stat' }, fmt.compact(v.view_count)), h('div', { class: 'stat-sub' }, '조회수'))));
    });
}

// ---------- 채널 표 ----------
function buildTable(card, state, ctx) {
    clear(card);
    const data = state.data;
    let channels = data.channels.slice();
    if (state.query) {
        channels = channels.filter(c => (c.title || '').toLowerCase().includes(state.query) || (c.handle || '').toLowerCase().includes(state.query));
    }
    const sorter = SORTS[state.sort] || SORTS.subs;
    channels.sort((a, b) => {
        const ka = sorter.key(a), kb = sorter.key(b);
        let cmp = typeof ka === 'string' ? ka.localeCompare(kb, 'ko') : (ka > kb ? 1 : ka < kb ? -1 : 0);
        return state.sortDesc ? -cmp : cmp;
    });

    card.appendChild(h('div', { class: 'card-header' },
        h('h3', {}, svg('channels'), '채널 현황', h('span', { class: 'card-sub' }, state.query ? `${channels.length} / ${data.channels.length}개` : `${data.channels.length}개`)),
        h('span', { class: 'card-sub' }, '열 제목을 누르면 정렬 · 행을 누르면 상세')));

    if (!channels.length) {
        card.appendChild(data.channels.length
            ? h('div', { class: 'empty-inline' }, '검색어와 일치하는 채널이 없습니다.')
            : emptyState({ iconName: 'channels', title: '등록된 채널이 없습니다', text: '운영 중인 채널의 URL이나 @핸들을 추가하면 이 표가 채워집니다.',
                           action: h('a', { class: 'btn btn-primary', href: '#/channels?add=1' }, svg('plus'), '채널 추가') }));
        return;
    }

    const p = periodLabel(data.period_days);
    const th = (label, key, cls = '') => {
        const el = h('th', { class: `${cls}${key ? ' sortable' : ''}`, scope: 'col' }, label);
        if (key) {
            if (state.sort === key) el.appendChild(h('span', { class: 'sort-ind' }, state.sortDesc ? '▼' : '▲'));
            el.addEventListener('click', () => {
                if (state.sort === key) state.sortDesc = !state.sortDesc;
                else { state.sort = key; state.sortDesc = !SORTS[key].asc; }
                store.set('dash.sort', state.sort);
                store.set('dash.sortDesc', state.sortDesc);
                buildTable(card, state, ctx);
            });
        }
        return el;
    };

    const table = h('table', { class: 'table channel-table' },
        h('thead', {}, h('tr', {},
            th('채널', 'title', 'sticky-col'), th('구독자', 'subs', 'num'), th('구독자 증감', 'subs_delta', 'num'),
            th('총 조회수', null, 'num'), th('조회수 증감', 'views_delta', 'num'), th(`${p} 업로드`, 'uploads', 'num'),
            th('최근 업로드', 'latest'), th('30일 추이', null), h('th', {}, h('span', { class: 'sr-only' }, '상세')))));
    const tbody = h('tbody');
    const staleDays = 7;
    channels.forEach(c => {
        const status = uploadStatus(c.days_since_upload, !!c.latest_video, staleDays);
        const row = h('tr', { class: `clickable${c.is_active ? '' : ' dim'}`, tabindex: '0' });
        row.addEventListener('click', (e) => { if (!e.target.closest('a')) ctx.navigate(`#/channels/${c.id}`); });
        row.addEventListener('keydown', (e) => { if (e.key === 'Enter') ctx.navigate(`#/channels/${c.id}`); });
        row.append(
            h('td', { class: 'sticky-col' }, h('div', { class: 'cell-main' }, avatarEl(c),
                h('div', {}, h('div', { class: 'cell-title' }, c.title),
                    h('div', { class: 'cell-sub' }, c.handle ? h('span', {}, c.handle) : null, c.group_name ? h('span', { class: 'tag' }, c.group_name) : null,
                        c.country ? h('span', {}, c.country) : null, !c.is_active ? badge('비활성', 'outline') : null)))),
            h('td', { class: 'num' }, c.subscriber_hidden ? h('span', { class: 'muted', title: '채널 소유자가 구독자 수를 비공개로 설정' }, '비공개')
                : h('span', { class: 'stat', title: fmt.int(c.subscriber_count) }, fmt.compact(c.subscriber_count))),
            h('td', { class: 'num' }, c.subscriber_hidden ? h('span', { class: 'muted' }, '—') : deltaEl(c.delta.subscriber_count, { partial: c.delta.partial, baselineAt: c.delta.baseline_at })),
            h('td', { class: 'num' }, h('span', { class: 'stat', title: fmt.int(c.view_count) }, fmt.compact(c.view_count))),
            h('td', { class: 'num' }, deltaEl(c.delta.view_count, { partial: c.delta.partial, baselineAt: c.delta.baseline_at })),
            h('td', { class: 'num' }, h('div', { class: 'cell-stack' }, h('span', { class: 'stat' }, fmt.int(c.uploads_in_period)),
                c.uploads_in_period ? h('span', { class: 'stat-sub' }, `조회수 ${fmt.compact(c.period_upload_views)}`) : h('span', { class: 'stat-sub' }, '없음'))),
            h('td', {}, c.latest_video
                ? h('div', { class: 'cell-main' }, thumbEl(c.latest_video), h('div', { style: { minWidth: 0 } },
                    h('div', { class: 'cell-title', style: { maxWidth: '220px', fontWeight: 500 } },
                        h('a', { href: youtubeVideoUrl(c.latest_video.youtube_id), target: '_blank', rel: 'noopener', title: c.latest_video.title }, c.latest_video.title)),
                    h('div', { class: 'cell-sub' }, badge(status.label, status.kind, status.icon), h('span', {}, `조회수 ${fmt.compact(c.latest_video.view_count)}`))))
                : badge(status.label, status.kind, status.icon)),
            h('td', {}, sparkline(c.sparkline, 'subscriber_count')),
            h('td', {}, h('span', { class: 'icon-btn', 'aria-hidden': 'true' }, svg('chevronRight'))),
        );
        tbody.appendChild(row);
    });
    table.appendChild(tbody);
    card.appendChild(h('div', { class: 'table-wrap' }, table));
}
