// 채널 상세: KPI · 추이 차트 · 일별 증감표 · 최근 영상 · 메모
import { h, svg, fmt, deltaEl, avatarEl, thumbEl, badge, uploadStatus, emptyState, store, clear, toast, confirmDialog,
         debounce, periodLabel, youtubeChannelUrl, youtubeVideoUrl, studioUrl } from '../ui.js';
import { lineChart, barChart, destroyChart, hasChartJs } from '../charts.js';

export const title = '채널 상세';
const PERIODS = [7, 30, 90];

export async function render(container, params, ctx) {
    const id = params.id;
    const state = { days: store.get('chd.days', 30), sort: 'published', detail: null, history: null, videos: null, showAllDays: false,
                    outlierMultiplier: 1.75, staleDays: 7 };
    let charts = [];
    const groups = await ctx.groups();

    const back = h('div', { style: { marginBottom: '12px' } }, h('a', { href: '#/channels', class: 'btn btn-ghost btn-sm' }, svg('chevronLeft'), '채널 관리'));
    const headerRow = h('div', { class: 'grid channel-head', style: { gridTemplateColumns: 'minmax(0, 2fr) minmax(280px, 1fr)', marginBottom: '14px' } });
    const controls = h('div', { class: 'filter-row' });
    const kpiRow = h('div', { class: 'grid grid-kpi', style: { marginBottom: '14px' } });
    const chartsRow = h('div', { class: 'grid grid-2', style: { marginBottom: '14px' } });
    const dailyCard = h('div', { class: 'card', style: { marginBottom: '14px' } });
    const videosCard = h('div', { class: 'card' });
    container.append(back, headerRow, controls, kpiRow, chartsRow, dailyCard, videosCard);

    async function load() {
        container.classList.add('is-loading');
        try {
            const [detail, history, videos, settings] = await Promise.all([
                ctx.api.get(`/api/channels/${id}`, { days: state.days }),
                ctx.api.get(`/api/channels/${id}/history`, { days: state.days }),
                ctx.api.get(`/api/channels/${id}/videos`, { limit: 100, sort: state.sort }),
                ctx.api.get('/api/settings'),
            ]);
            state.detail = detail; state.history = history.history; state.videos = videos.videos;
            state.outlierMultiplier = settings.settings.outlier_multiplier;
            state.staleDays = settings.settings.stale_days;
            renderAll();
        } catch (error) {
            if (error.status === 404) {
                clear(container);
                container.appendChild(emptyState({ iconName: 'channels', title: '채널을 찾을 수 없습니다', text: '삭제되었거나 잘못된 주소입니다.', action: h('a', { class: 'btn btn-primary', href: '#/channels' }, '채널 관리로') }));
                return;
            }
            toast(error.message, 'error');
        } finally {
            container.classList.remove('is-loading');
        }
    }

    function renderAll() {
        const d = state.detail;
        ctx.setTitle(d.title, d.handle || d.youtube_id);
        renderHeader();
        renderControls();
        renderKpis();
        renderCharts();
        renderDaily();
        renderVideos();
    }

    function renderHeader() {
        const d = state.detail;
        clear(headerRow);
        const groupSelect = h('select', { class: 'select select-sm', style: { width: 'auto' } },
            ...groups.map(g => h('option', { value: String(g.id), selected: g.id === d.group_id }, g.name)));
        groupSelect.addEventListener('change', async () => {
            try { await ctx.api.patch(`/api/channels/${id}`, { group_id: Number(groupSelect.value) }); ctx.invalidateGroups(); toast('그룹을 변경했습니다', 'success', { timeout: 1500 }); }
            catch (error) { toast(error.message, 'error'); }
        });
        const toggle = h('input', { type: 'checkbox', checked: !!d.is_active });
        toggle.addEventListener('change', async () => {
            try { await ctx.api.patch(`/api/channels/${id}`, { is_active: toggle.checked }); toast(toggle.checked ? '활성화했습니다 (자동 갱신 대상)' : '비활성화했습니다 (갱신 제외)', 'success', { timeout: 2000 }); }
            catch (error) { toast(error.message, 'error'); toggle.checked = !toggle.checked; }
        });
        const status = uploadStatus(d.days_since_upload, !!d.latest_video, state.staleDays);

        headerRow.appendChild(h('div', { class: 'card' }, h('div', { class: 'card-body', style: { display: 'flex', gap: '16px', flexWrap: 'wrap', alignItems: 'flex-start' } },
            avatarEl(d, 'lg'),
            h('div', { style: { flex: 1, minWidth: '220px' } },
                h('div', { class: 'row', style: { gap: '8px' } }, h('h2', { style: { fontSize: '20px' } }, d.title), badge(status.label, status.kind, status.icon), !d.is_active ? badge('비활성', 'outline') : null),
                h('div', { class: 'muted', style: { fontSize: '13px', marginTop: '4px' } },
                    d.handle ? `${d.handle} · ` : '', d.country ? `${d.country} · ` : '', d.published_at ? `개설 ${fmt.date(d.published_at)} · ` : '',
                    d.stats_updated_at ? `갱신 ${fmt.relative(d.stats_updated_at)}` : '아직 갱신 안 함'),
                h('div', { class: 'row', style: { marginTop: '12px', gap: '8px' } },
                    h('a', { class: 'btn btn-secondary btn-sm', href: youtubeChannelUrl(d), target: '_blank', rel: 'noopener' }, svg('youtube'), 'YouTube'),
                    h('a', { class: 'btn btn-secondary btn-sm', href: studioUrl(d), target: '_blank', rel: 'noopener' }, svg('external'), '스튜디오'),
                    h('button', { class: 'btn btn-secondary btn-sm', type: 'button', onclick: () => ctx.startRefresh({ scope: 'channel', channel_id: id }) }, svg('refresh'), '이 채널만 업데이트'),
                    h('label', { class: 'row', style: { gap: '6px', fontSize: '13px' } }, '그룹', groupSelect),
                    h('label', { class: 'row', style: { gap: '6px', fontSize: '13px' } }, h('span', { class: 'switch' }, toggle, h('span', { class: 'track' })), '활성'),
                    h('button', { class: 'btn btn-danger btn-sm', type: 'button', onclick: async () => {
                        if (await confirmDialog({ title: '채널 삭제', message: `"${d.title}" 채널과 수집된 영상·이력을 삭제합니다.`, confirmText: '삭제', danger: true })) {
                            try { await ctx.api.delete(`/api/channels/${id}`); ctx.invalidateGroups(); toast('삭제했습니다', 'success'); ctx.navigate('#/channels'); }
                            catch (error) { toast(error.message, 'error'); }
                        } } }, svg('trash'), '삭제'),
                )))));

        // 메모
        const memo = h('textarea', { class: 'textarea', rows: '5', placeholder: '운영 메모 (담당자, 업로드 계획, 소재 아이디어…)', style: { fontFamily: 'inherit', minHeight: '110px' } }, d.memo || '');
        const saved = h('span', { class: 'muted', style: { fontSize: '12px' } }, '');
        memo.addEventListener('input', debounce(async () => {
            try { await ctx.api.patch(`/api/channels/${id}`, { memo: memo.value }); saved.textContent = `저장됨 ${fmt.datetime(new Date().toISOString())}`; }
            catch (error) { saved.textContent = '저장 실패'; toast(error.message, 'error'); }
        }, 600));
        headerRow.appendChild(h('div', { class: 'card' },
            h('div', { class: 'card-header' }, h('h3', {}, svg('notebook'), '메모'), saved),
            h('div', { class: 'card-body' }, memo)));
    }

    function renderControls() {
        clear(controls);
        const seg = h('div', { class: 'segment' });
        PERIODS.forEach(days => {
            const btn = h('button', { type: 'button', class: days === state.days ? 'active' : '' }, `${days}일`);
            btn.addEventListener('click', () => { state.days = days; store.set('chd.days', days); load(); });
            seg.appendChild(btn);
        });
        controls.append(h('div', { class: 'field' }, h('span', { class: 'field-label' }, '기간'), seg));
    }

    function renderKpis() {
        const d = state.detail;
        clear(kpiRow);
        const p = periodLabel(state.days);
        const vs = () => h('span', { class: 'muted' }, `vs ${p} 전`);
        const tile = (label, iconName, value, foot) => h('div', { class: 'card kpi' },
            h('div', { class: 'kpi-label' }, svg(iconName), label), h('div', { class: 'kpi-value' }, value), h('div', { class: 'kpi-foot' }, foot));
        kpiRow.append(
            tile('구독자', 'users', d.subscriber_hidden ? '비공개' : fmt.compact(d.subscriber_count), d.subscriber_hidden ? '소유자가 비공개로 설정' : [deltaEl(d.delta.subscriber_count, { partial: d.delta.partial, baselineAt: d.delta.baseline_at }), vs()]),
            tile('총 조회수', 'eye', fmt.compact(d.view_count), [deltaEl(d.delta.view_count, { partial: d.delta.partial, baselineAt: d.delta.baseline_at }), vs()]),
            tile('영상 수', 'film', fmt.int(d.video_count), [deltaEl(d.delta.video_count, { partial: d.delta.partial, baselineAt: d.delta.baseline_at }), vs()]),
            tile(`${p} 업로드`, 'upload', fmt.int(d.uploads_in_period), d.uploads_in_period ? `업로드 영상 조회수 ${fmt.compact(d.period_upload_views)}` : '기간 내 업로드 없음'),
            tile('영상당 평균 조회수', 'barChart', d.avg_views_per_upload !== null ? fmt.compact(d.avg_views_per_upload) : '—',
                d.median_views_per_day ? `평소 조회수/일 중앙값 ${fmt.compact(d.median_views_per_day)}` : '표본 부족 (영상 3개 이상 필요)'),
        );
    }

    function renderCharts() {
        charts.forEach(destroyChart); charts = [];
        clear(chartsRow);
        const hist = state.history || [];
        const labels = hist.map(r => fmt.shortDate(r.day));
        const mk = (titleText, iconName, note) => {
            const canvas = h('canvas');
            const card = h('div', { class: 'card' }, h('div', { class: 'card-header' }, h('h3', {}, svg(iconName), titleText), h('span', { class: 'card-sub' }, note)),
                h('div', { class: 'card-body' }, hist.length >= 2 && hasChartJs() ? h('div', { class: 'chart-box' }, canvas)
                    : h('div', { class: 'empty-inline' }, hasChartJs() ? '이틀 이상 기록이 쌓이면 추이가 표시됩니다.' : '차트 라이브러리를 불러오지 못했습니다.')));
            return { card, canvas };
        };
        const a = mk('구독자 추이', 'lineChart', `${state.days}일 · 하루 마지막 기록`);
        const b = mk('일별 조회수 증가', 'barChart', '전일 대비 채널 총 조회수 증가');
        chartsRow.append(a.card, b.card);
        if (hist.length >= 2 && hasChartJs()) {
            charts.push(lineChart(a.canvas, { labels, values: hist.map(r => r.subscriber_count), label: '구독자' }));
            charts.push(barChart(b.canvas, { labels, values: hist.map(r => r.view_delta), label: '조회수 증가', signed: true }));
        }
    }

    function renderDaily() {
        clear(dailyCard);
        const hist = (state.history || []).slice().reverse();
        dailyCard.appendChild(h('div', { class: 'card-header' }, h('h3', {}, svg('calendar'), '일별 증감'),
            h('span', { class: 'card-sub' }, hist.length ? `${hist.length}일치 기록` : '')));
        if (!hist.length) { dailyCard.appendChild(h('div', { class: 'empty-inline' }, '아직 기록이 없습니다. 업데이트가 쌓이면 날짜별 증감이 표시됩니다.')); return; }
        const rows = state.showAllDays ? hist : hist.slice(0, 14);
        const table = h('table', { class: 'table' }, h('thead', {}, h('tr', {},
            h('th', {}, '날짜'), h('th', { class: 'num' }, '구독자'), h('th', { class: 'num' }, '증감'), h('th', { class: 'num' }, '총 조회수'), h('th', { class: 'num' }, '증감'), h('th', { class: 'num' }, '영상'), h('th', { class: 'num' }, '증감'))));
        const tbody = h('tbody');
        rows.forEach(r => tbody.appendChild(h('tr', {},
            h('td', {}, fmt.date(r.day)), h('td', { class: 'num' }, fmt.int(r.subscriber_count)), h('td', { class: 'num' }, r.subscriber_delta === null ? h('span', { class: 'muted' }, '—') : deltaEl(r.subscriber_delta, { compact: false })),
            h('td', { class: 'num' }, fmt.int(r.view_count)), h('td', { class: 'num' }, r.view_delta === null ? h('span', { class: 'muted' }, '—') : deltaEl(r.view_delta, { compact: false })),
            h('td', { class: 'num' }, fmt.int(r.video_count)), h('td', { class: 'num' }, r.video_delta === null ? h('span', { class: 'muted' }, '—') : deltaEl(r.video_delta, { compact: false })))));
        table.appendChild(tbody);
        dailyCard.appendChild(h('div', { class: 'table-wrap' }, table));
        if (hist.length > 14) {
            dailyCard.appendChild(h('div', { class: 'card-footer' }, h('button', { class: 'link-btn', type: 'button', onclick: () => { state.showAllDays = !state.showAllDays; renderDaily(); } },
                state.showAllDays ? '최근 14일만 보기' : `전체 ${hist.length}일 보기`)));
        }
    }

    function renderVideos() {
        clear(videosCard);
        const sortSelect = h('select', { class: 'select select-sm', style: { width: 'auto' } },
            ...[['published', '최신순'], ['views', '조회수'], ['views_per_day', '조회수/일'], ['delta', '최근 증가'], ['likes', '좋아요'], ['comments', '댓글']]
                .map(([v, l]) => h('option', { value: v, selected: v === state.sort }, l)));
        sortSelect.addEventListener('change', () => { state.sort = sortSelect.value; load(); });
        videosCard.appendChild(h('div', { class: 'card-header' }, h('h3', {}, svg('video'), '최근 영상', h('span', { class: 'card-sub' }, `${state.videos.length}개 수집됨`)),
            h('div', { class: 'row' }, h('label', { class: 'muted', style: { fontSize: '12.5px' } }, '정렬'), sortSelect)));
        if (!state.videos.length) { videosCard.appendChild(h('div', { class: 'empty-inline' }, '수집된 영상이 없습니다. 업데이트하면 최근 업로드가 표시됩니다.')); return; }
        const table = h('table', { class: 'table' }, h('thead', {}, h('tr', {},
            h('th', { class: 'sticky-col' }, '영상'), h('th', {}, '게시'), h('th', { class: 'num' }, '조회수'), h('th', { class: 'num' }, '조회수/일'), h('th', { class: 'num' }, '최근 증가'),
            h('th', { class: 'num' }, '좋아요'), h('th', { class: 'num' }, '댓글'), h('th', {}, '길이'), h('th', { class: 'num' }, '평소 대비'))));
        const tbody = h('tbody');
        state.videos.forEach(v => tbody.appendChild(videoRow(v, state.outlierMultiplier)));
        table.appendChild(tbody);
        videosCard.appendChild(h('div', { class: 'table-wrap' }, table));
    }

    const off = ctx.onRefreshDone(() => load());
    const onTheme = () => renderCharts();
    window.addEventListener('cb:theme', onTheme);
    await load();
    return () => { off(); window.removeEventListener('cb:theme', onTheme); charts.forEach(destroyChart); };
}

export function videoRow(v, multiplier = 1.75, channelCell = null) {
    const ratioEl = v.ratio === null || v.ratio === undefined ? h('span', { class: 'muted' }, '—')
        : v.ratio >= multiplier ? badge(fmt.multiple(v.ratio), 'good', 'trendingUp')
        : v.ratio <= 0.5 ? badge(fmt.multiple(v.ratio), 'outline') : h('span', {}, fmt.multiple(v.ratio));
    return h('tr', {},
        h('td', { class: 'sticky-col' }, h('div', { class: 'cell-main' }, thumbEl(v),
            h('div', { style: { minWidth: 0 } },
                h('div', { class: 'cell-title', style: { maxWidth: '320px' } }, h('a', { href: youtubeVideoUrl(v.youtube_id), target: '_blank', rel: 'noopener', title: v.title }, v.title)),
                h('div', { class: 'cell-sub' }, v.is_short ? badge('쇼츠', 'outline') : null, channelCell)))),
        h('td', { title: fmt.datetime(v.published_at), style: { whiteSpace: 'nowrap' } }, fmt.relative(v.published_at)),
        h('td', { class: 'num' }, h('span', { class: 'stat', title: fmt.int(v.view_count) }, fmt.compact(v.view_count))),
        h('td', { class: 'num' }, fmt.compact(v.views_per_day)),
        h('td', { class: 'num' }, v.view_delta === null || v.view_delta === undefined ? h('span', { class: 'muted' }, '—') : deltaEl(v.view_delta)),
        h('td', { class: 'num' }, fmt.compact(v.like_count)),
        h('td', { class: 'num' }, fmt.compact(v.comment_count)),
        h('td', { class: 'muted' }, fmt.duration(v.duration_seconds)),
        h('td', { class: 'num' }, ratioEl),
    );
}
