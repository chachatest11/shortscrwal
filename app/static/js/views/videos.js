// 영상 탐색: 전체 채널의 영상을 필터·정렬
import { h, svg, fmt, badge, emptyState, store, clear, toast, debounce } from '../ui.js';
import { videoRow } from './channel.js';

export const title = '영상';
const PERIODS = [[7, '7일'], [30, '30일'], [90, '90일'], [0, '전체']];
const KINDS = [['all', '전체'], ['short', '쇼츠'], ['long', '롱폼']];
const SORTS = [['published', '최신순'], ['views', '조회수'], ['views_per_day', '조회수/일'], ['delta', '최근 증가'], ['ratio', '평소 대비'], ['likes', '좋아요'], ['comments', '댓글']];
const LIMIT = 50;

export async function render(container, params, ctx) {
    const state = {
        groupId: store.get('vid.group', 0), channelId: 0, days: store.get('vid.days', 30), kind: store.get('vid.kind', 'all'),
        sort: store.get('vid.sort', 'published'), query: '', offset: 0, items: [], total: 0, shortCount: 0, longCount: 0, multiplier: 1.75,
    };
    ctx.setTitle('영상', '');
    const [groups, channelList, settings] = await Promise.all([ctx.groups(), ctx.api.get('/api/channels'), ctx.api.get('/api/settings')]);
    state.multiplier = settings.settings.outlier_multiplier;

    const filterRow = h('div', { class: 'filter-row' });
    const summary = h('div', { class: 'muted', style: { fontSize: '13px', marginBottom: '10px' } });
    const card = h('div', { class: 'card' });
    const more = h('div', { style: { textAlign: 'center', marginTop: '14px' } });
    container.append(filterRow, summary, card, more);

    function buildFilters() {
        clear(filterRow);
        const groupSelect = h('select', { class: 'select select-sm', id: 'vidGroup' }, h('option', { value: '0' }, '전체 그룹'),
            ...groups.map(g => h('option', { value: String(g.id), selected: g.id === state.groupId }, g.name)));
        groupSelect.addEventListener('change', () => { state.groupId = Number(groupSelect.value); store.set('vid.group', state.groupId); buildFilters(); reload(); });
        const channels = channelList.channels.filter(c => !state.groupId || c.group_id === state.groupId);
        const channelSelect = h('select', { class: 'select select-sm', id: 'vidChannel' }, h('option', { value: '0' }, '전체 채널'),
            ...channels.map(c => h('option', { value: String(c.id), selected: c.id === state.channelId }, c.title)));
        channelSelect.addEventListener('change', () => { state.channelId = Number(channelSelect.value); reload(); });

        const seg = (items, current, onPick) => {
            const el = h('div', { class: 'segment' });
            items.forEach(([value, label]) => {
                const btn = h('button', { type: 'button', class: value === current ? 'active' : '' }, label);
                btn.addEventListener('click', () => { onPick(value); el.querySelectorAll('button').forEach(b => b.classList.toggle('active', b === btn)); });
                el.appendChild(btn);
            });
            return el;
        };
        const sortSelect = h('select', { class: 'select select-sm', id: 'vidSort' }, ...SORTS.map(([v, l]) => h('option', { value: v, selected: v === state.sort }, l)));
        sortSelect.addEventListener('change', () => { state.sort = sortSelect.value; store.set('vid.sort', state.sort); reload(); });
        const search = h('input', { class: 'input input-sm', type: 'search', placeholder: '제목 검색', id: 'vidSearch', value: state.query });
        search.addEventListener('input', debounce(() => { state.query = search.value.trim(); reload(); }, 250));
        const exportBtn = h('a', { class: 'btn btn-secondary btn-sm', href: '#' }, svg('download'), 'CSV');
        exportBtn.addEventListener('click', (e) => { e.preventDefault(); window.location.href = `/api/export/videos.csv?${queryString()}`; });

        filterRow.append(
            h('div', { class: 'field' }, h('span', { class: 'field-label' }, '게시 기간'), seg(PERIODS, state.days, v => { state.days = v; store.set('vid.days', v); reload(); })),
            h('div', { class: 'field' }, h('span', { class: 'field-label' }, '유형'), seg(KINDS, state.kind, v => { state.kind = v; store.set('vid.kind', v); reload(); })),
            h('div', { class: 'field' }, h('label', { for: 'vidGroup' }, '그룹'), groupSelect),
            h('div', { class: 'field' }, h('label', { for: 'vidChannel' }, '채널'), channelSelect),
            h('div', { class: 'field' }, h('label', { for: 'vidSort' }, '정렬'), sortSelect),
            h('div', { class: 'field grow' }, h('label', { for: 'vidSearch' }, '검색'), h('div', { class: 'search-box' }, svg('search'), search)),
            h('div', { class: 'field' }, h('span', { class: 'field-label' }, ' '), exportBtn),
        );
    }

    function queryString() {
        return new URLSearchParams({ group_id: state.groupId, channel_id: state.channelId, days: state.days, kind: state.kind, sort: state.sort, q: state.query }).toString();
    }

    async function reload() { state.offset = 0; state.items = []; await load(); }

    async function load() {
        container.classList.add('is-loading');
        try {
            const r = await ctx.api.get('/api/videos', { group_id: state.groupId, channel_id: state.channelId, days: state.days, kind: state.kind,
                                                       sort: state.sort, q: state.query, limit: LIMIT, offset: state.offset });
            state.items = state.offset ? state.items.concat(r.videos) : r.videos;
            state.total = r.total; state.shortCount = r.short_count; state.longCount = r.long_count;
            renderTable();
        } catch (error) { toast(error.message, 'error'); }
        finally { container.classList.remove('is-loading'); }
    }

    function renderTable() {
        clear(card); clear(more);
        summary.textContent = `${fmt.int(state.total)}개 영상 · 쇼츠 ${fmt.int(state.shortCount)} · 롱폼 ${fmt.int(state.longCount)}`;
        ctx.setTitle('영상', summary.textContent);
        if (!state.items.length) {
            card.appendChild(emptyState({ iconName: 'video', title: '조건에 맞는 영상이 없습니다', text: '기간이나 유형 필터를 넓혀 보세요. 영상은 채널 업데이트 때 수집됩니다.' }));
            return;
        }
        const table = h('table', { class: 'table' }, h('thead', {}, h('tr', {},
            h('th', { class: 'sticky-col' }, '영상'), h('th', {}, '게시'), h('th', { class: 'num' }, '조회수'), h('th', { class: 'num' }, '조회수/일'), h('th', { class: 'num' }, '최근 증가'),
            h('th', { class: 'num' }, '좋아요'), h('th', { class: 'num' }, '댓글'), h('th', {}, '길이'), h('th', { class: 'num' }, '평소 대비'))));
        const tbody = h('tbody');
        state.items.forEach(v => tbody.appendChild(videoRow(v, state.multiplier, h('a', { href: `#/channels/${v.channel_id}` }, v.channel_title))));
        table.appendChild(tbody);
        card.appendChild(h('div', { class: 'table-wrap' }, table));
        if (state.items.length < state.total) {
            more.appendChild(h('button', { class: 'btn btn-secondary', type: 'button', onclick: () => { state.offset += LIMIT; load(); } },
                `더 보기 (${fmt.int(state.items.length)} / ${fmt.int(state.total)})`));
        }
    }

    buildFilters();
    await load();
    const off = ctx.onRefreshDone(() => reload());
    return () => off();
}
