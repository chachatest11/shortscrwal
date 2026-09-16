// 채널 관리: 목록 · 추가 · 그룹 · 일괄 작업 · CSV
import { h, svg, fmt, avatarEl, badge, uploadStatus, emptyState, store, clear, toast, openModal, confirmDialog,
         setBusy, debounce, youtubeChannelUrl } from '../ui.js';

export const title = '채널 관리';

export async function render(container, params, ctx) {
    const state = {
        groupId: store.get('ch.group', 0),
        query: '',
        includeInactive: true,
        selected: new Set(),
        channels: [],
        groups: [],
        staleDays: 7,
    };
    ctx.setTitle('채널 관리', '');
    state.groups = await ctx.groups(true);

    const toolbar = h('div', { class: 'filter-row' });
    const bulkBar = h('div', { class: 'bulk-bar', hidden: true });
    const card = h('div', { class: 'card' });
    container.append(toolbar, bulkBar, card);

    buildToolbar();

    async function load() {
        container.classList.add('is-loading');
        try {
            const [list, settings] = await Promise.all([
                ctx.api.get('/api/channels', { group_id: state.groupId, q: state.query, include_inactive: state.includeInactive }),
                ctx.api.get('/api/settings'),
            ]);
            state.channels = list.channels;
            state.staleDays = settings.settings.stale_days;
            state.groups = await ctx.groups();
            state.selected = new Set([...state.selected].filter(id => state.channels.some(c => c.id === id)));
            ctx.setTitle('채널 관리', `${state.channels.length}개 채널 · ${state.groups.length}개 그룹`);
            buildTable();
            updateBulkBar();
        } catch (error) {
            toast(error.message, 'error');
        } finally {
            container.classList.remove('is-loading');
        }
    }

    function buildToolbar() {
        clear(toolbar);
        const groupSelect = h('select', { class: 'select select-sm', id: 'chGroup' }, h('option', { value: '0' }, '전체 그룹'),
            ...state.groups.map(g => h('option', { value: String(g.id), selected: g.id === state.groupId }, `${g.name} (${g.channel_count})`)));
        groupSelect.addEventListener('change', () => { state.groupId = Number(groupSelect.value); store.set('ch.group', state.groupId); load(); });

        const search = h('input', { class: 'input input-sm', type: 'search', placeholder: '채널 이름, 핸들, ID', id: 'chSearch' });
        search.addEventListener('input', debounce(() => { state.query = search.value.trim(); load(); }, 250));

        const inactive = h('input', { type: 'checkbox', class: 'checkbox', checked: state.includeInactive });
        inactive.addEventListener('change', () => { state.includeInactive = inactive.checked; load(); });

        toolbar.append(
            h('div', { class: 'field' }, h('label', { for: 'chGroup' }, '그룹'), groupSelect),
            h('div', { class: 'field grow' }, h('label', { for: 'chSearch' }, '검색'), h('div', { class: 'search-box' }, svg('search'), search)),
            h('label', { class: 'row', style: { gap: '6px', fontSize: '13px', paddingBottom: '8px' } }, inactive, '비활성 포함'),
            h('div', { class: 'spacer' }),
            h('button', { class: 'btn btn-secondary btn-sm', type: 'button', onclick: openGroupsModal }, svg('layers'), '그룹 관리'),
            h('a', { class: 'btn btn-secondary btn-sm', href: '#', onclick: (e) => { e.preventDefault(); window.location.href = `/api/export/channels.csv?group_id=${state.groupId}&days=7`; } }, svg('download'), 'CSV'),
            h('button', { class: 'btn btn-primary btn-sm', type: 'button', onclick: openAddModal }, svg('plus'), '채널 추가'),
        );
    }

    function buildTable() {
        clear(card);
        const channels = state.channels;
        if (!channels.length) {
            card.appendChild(emptyState({
                iconName: 'channels', title: state.query ? '검색 결과가 없습니다' : '등록된 채널이 없습니다',
                text: state.query ? '' : '채널 URL, @핸들, 채널 ID, 영상 URL을 붙여넣어 추가하세요. 여러 개를 한 번에 넣을 수 있습니다.',
                action: state.query ? null : h('button', { class: 'btn btn-primary', type: 'button', onclick: openAddModal }, svg('plus'), '채널 추가'),
            }));
            return;
        }
        const allChecked = channels.every(c => state.selected.has(c.id));
        const master = h('input', { type: 'checkbox', class: 'checkbox', checked: allChecked, 'aria-label': '전체 선택' });
        master.addEventListener('change', () => {
            channels.forEach(c => master.checked ? state.selected.add(c.id) : state.selected.delete(c.id));
            buildTable(); updateBulkBar();
        });

        const table = h('table', { class: 'table manage-table' },
            h('thead', {}, h('tr', {},
                h('th', { style: { width: '36px' } }, master),
                h('th', { class: 'sticky-col' }, '채널'), h('th', {}, '그룹'), h('th', { class: 'num' }, '구독자'),
                h('th', { class: 'num' }, '영상 수'), h('th', {}, '최근 업로드'), h('th', {}, '활성'), h('th', {}, '마지막 갱신'), h('th', {}, ''))));
        const tbody = h('tbody');
        channels.forEach(c => {
            const cb = h('input', { type: 'checkbox', class: 'checkbox', checked: state.selected.has(c.id), 'aria-label': `${c.title} 선택` });
            cb.addEventListener('change', () => { cb.checked ? state.selected.add(c.id) : state.selected.delete(c.id); row.classList.toggle('selected', cb.checked); updateBulkBar(); });

            const groupSelect = h('select', { class: 'select select-sm', style: { width: 'auto', minWidth: '120px' }, 'aria-label': '그룹 변경' },
                ...state.groups.map(g => h('option', { value: String(g.id), selected: g.id === c.group_id }, g.name)));
            groupSelect.addEventListener('change', async () => {
                try {
                    await ctx.api.patch(`/api/channels/${c.id}`, { group_id: Number(groupSelect.value) });
                    toast(`${c.title} → ${groupSelect.selectedOptions[0].textContent}`, 'success', { timeout: 2000 });
                    ctx.invalidateGroups();
                    if (state.groupId) load();
                } catch (error) { toast(error.message, 'error'); }
            });

            const toggle = h('input', { type: 'checkbox', checked: !!c.is_active });
            toggle.addEventListener('change', async () => {
                try {
                    await ctx.api.patch(`/api/channels/${c.id}`, { is_active: toggle.checked });
                    c.is_active = toggle.checked ? 1 : 0;
                    row.classList.toggle('dim', !toggle.checked);
                    ctx.invalidateGroups();
                } catch (error) { toast(error.message, 'error'); toggle.checked = !toggle.checked; }
            });

            const status = uploadStatus(c.days_since_upload, !!c.last_published_at, state.staleDays);
            const row = h('tr', { class: `${state.selected.has(c.id) ? 'selected' : ''}${c.is_active ? '' : ' dim'}` },
                h('td', {}, cb),
                h('td', { class: 'sticky-col' }, h('div', { class: 'cell-main' }, avatarEl(c),
                    h('div', { style: { minWidth: 0 } },
                        h('div', { class: 'cell-title' }, h('a', { href: `#/channels/${c.id}` }, c.title)),
                        h('div', { class: 'cell-sub' }, c.handle ? h('span', {}, c.handle) : h('span', { class: 'mono' }, c.youtube_id),
                            h('a', { href: youtubeChannelUrl(c), target: '_blank', rel: 'noopener', title: 'YouTube에서 열기', class: 'muted', style: { display: 'inline-flex' } }, svg('external')))))),
                h('td', {}, groupSelect),
                h('td', { class: 'num' }, c.subscriber_hidden ? h('span', { class: 'muted' }, '비공개') : h('span', { class: 'stat' }, fmt.compact(c.subscriber_count))),
                h('td', { class: 'num' }, fmt.int(c.video_count)),
                h('td', {}, badge(status.label, status.kind, status.icon)),
                h('td', {}, h('label', { class: 'switch' }, toggle, h('span', { class: 'track' }))),
                h('td', { class: 'muted', title: c.stats_updated_at ? fmt.datetime(c.stats_updated_at) : '' }, c.stats_updated_at ? fmt.relative(c.stats_updated_at) : '미갱신'),
                h('td', {}, h('div', { class: 'row', style: { gap: '4px', flexWrap: 'nowrap' } },
                    h('a', { class: 'icon-btn', href: `#/channels/${c.id}`, title: '상세 보기' }, svg('chevronRight')),
                    h('button', { class: 'icon-btn', type: 'button', title: '삭제', onclick: () => removeChannel(c) }, svg('trash')))),
            );
            tbody.appendChild(row);
        });
        table.appendChild(tbody);
        card.appendChild(h('div', { class: 'table-wrap' }, table));
    }

    function updateBulkBar() {
        clear(bulkBar);
        const n = state.selected.size;
        bulkBar.hidden = n === 0;
        if (!n) return;
        const groupSelect = h('select', { class: 'select select-sm', style: { width: 'auto' } }, h('option', { value: '' }, '그룹 선택…'),
            ...state.groups.map(g => h('option', { value: String(g.id) }, g.name)));
        const run = async (action, extra = {}) => {
            try {
                const r = await ctx.api.post('/api/channels/bulk', { ids: [...state.selected], action, ...extra });
                toast(`${r.affected}개 채널 처리됨`, 'success', { timeout: 2500 });
                state.selected.clear();
                ctx.invalidateGroups();
                await load();
            } catch (error) { toast(error.message, 'error'); }
        };
        bulkBar.append(
            h('b', {}, `${n}개 선택`),
            groupSelect,
            h('button', { class: 'btn btn-secondary btn-sm', type: 'button', onclick: () => { if (!groupSelect.value) return toast('이동할 그룹을 선택하세요', 'warn'); run('move', { group_id: Number(groupSelect.value) }); } }, '그룹 이동'),
            h('button', { class: 'btn btn-secondary btn-sm', type: 'button', onclick: () => run('activate') }, '활성'),
            h('button', { class: 'btn btn-secondary btn-sm', type: 'button', onclick: () => run('deactivate') }, '비활성'),
            h('button', { class: 'btn btn-danger btn-sm', type: 'button', onclick: async () => {
                if (await confirmDialog({ title: '채널 삭제', message: `선택한 ${n}개 채널과 수집된 영상·이력을 삭제합니다. 되돌릴 수 없습니다.`, confirmText: '삭제', danger: true })) run('delete');
            } }, '삭제'),
            h('button', { class: 'btn btn-ghost btn-sm', type: 'button', onclick: () => { state.selected.clear(); buildTable(); updateBulkBar(); } }, '선택 해제'),
        );
    }

    async function removeChannel(c) {
        const ok = await confirmDialog({ title: '채널 삭제', message: `"${c.title}" 채널과 수집된 영상·이력을 삭제합니다. 되돌릴 수 없습니다.`, confirmText: '삭제', danger: true });
        if (!ok) return;
        try {
            await ctx.api.delete(`/api/channels/${c.id}`);
            toast('삭제했습니다', 'success', { timeout: 2000 });
            ctx.invalidateGroups();
            load();
        } catch (error) { toast(error.message, 'error'); }
    }

    // ---------- 채널 추가 모달 ----------
    function openAddModal() {
        const textarea = h('textarea', { class: 'textarea', rows: '8',
            placeholder: '한 줄에 하나씩 입력하세요. 형식은 섞어도 됩니다.\n\nhttps://www.youtube.com/@channelhandle\nhttps://www.youtube.com/channel/UCxxxxxxxxxxxxxxxxxxxxxx\n@channelhandle\nUCxxxxxxxxxxxxxxxxxxxxxx\nhttps://www.youtube.com/watch?v=VIDEO_ID  (영상 링크 → 해당 채널)' });
        const groupSelect = h('select', { class: 'select' },
            ...state.groups.map(g => h('option', { value: String(g.id), selected: g.id === (state.groupId || 1) }, g.name)));
        const fetchVideos = h('input', { type: 'checkbox', class: 'checkbox', checked: true });
        const results = h('div', { class: 'result-list', hidden: true });
        const submit = h('button', { class: 'btn btn-primary', type: 'button' }, '추가');
        const closeBtn = h('button', { class: 'btn btn-secondary', type: 'button' }, '닫기');
        const dialog = openModal({
            title: '채널 추가', wide: true,
            body: [
                h('div', { class: 'field' }, h('label', {}, '채널 목록'), textarea),
                h('div', { class: 'row', style: { gap: '16px' } },
                    h('div', { class: 'field', style: { minWidth: '200px' } }, h('label', {}, '그룹'), groupSelect),
                    h('label', { class: 'row', style: { gap: '6px', fontSize: '13px', paddingTop: '22px' } }, fetchVideos, '최근 영상도 바로 수집 (채널당 1~2 units)')),
                h('p', { class: 'muted', style: { fontSize: '12.5px' } }, '채널 하나당 API 쿼터 약 1 unit이 듭니다. 커스텀 URL(/c/이름)은 검색이 필요해 100 units가 들 수 있습니다.'),
                results,
            ],
            footer: [closeBtn, submit],
        });
        closeBtn.addEventListener('click', () => dialog.close());
        submit.addEventListener('click', async () => {
            const inputs = textarea.value.split('\n').map(s => s.trim()).filter(Boolean);
            if (!inputs.length) return toast('추가할 채널을 입력하세요', 'warn');
            setBusy(submit, true);
            try {
                const r = await ctx.api.post('/api/channels', { inputs, group_id: Number(groupSelect.value), fetch_videos: fetchVideos.checked });
                clear(results);
                results.hidden = false;
                r.added.forEach(a => results.appendChild(h('div', { class: 'result-item ok' }, svg('checkCircle'),
                    h('span', {}, h('b', {}, a.title), ` · 구독자 ${fmt.compact(a.subscriber_count)}`, a.note ? h('span', { class: 'muted' }, ` · ${a.note}`) : null))));
                r.skipped.forEach(s => results.appendChild(h('div', { class: 'result-item skip' }, svg('info'), h('span', {}, h('b', {}, s.title || s.input), ` · ${s.reason}`))));
                r.failed.forEach(f => results.appendChild(h('div', { class: 'result-item fail' }, svg('xCircle'), h('span', {}, h('b', {}, f.input), ` · ${f.error}`))));
                const msg = `추가 ${r.added.length} · 건너뜀 ${r.skipped.length} · 실패 ${r.failed.length} · 쿼터 ${r.quota_used} units`;
                toast(msg, r.added.length ? 'success' : (r.failed.length ? 'error' : 'info'), { timeout: 6000 });
                if (r.added.length) {
                    textarea.value = inputs.filter(i => r.failed.some(f => f.input === i)).join('\n');
                    ctx.invalidateGroups();
                    load();
                }
            } catch (error) {
                toast(error.message, 'error', { timeout: 8000 });
                if (error.status === 400 && /API 키/.test(error.message)) { dialog.close(); ctx.navigate('#/settings'); }
            } finally {
                setBusy(submit, false);
            }
        });
        setTimeout(() => textarea.focus(), 50);
    }

    // ---------- 그룹 관리 모달 ----------
    async function openGroupsModal() {
        const list = h('div', { class: 'stack' });
        const nameInput = h('input', { class: 'input', placeholder: '새 그룹 이름 (예: 내 채널, 참고 채널)' });
        const addBtn = h('button', { class: 'btn btn-primary', type: 'button' }, svg('plus'), '추가');
        const dialog = openModal({
            title: '그룹 관리',
            body: [h('div', { class: 'row' }, h('div', { style: { flex: 1 } }, nameInput), addBtn), list],
            footer: [h('button', { class: 'btn btn-secondary', type: 'button', onclick: () => dialog.close() }, '닫기')],
            onClose: async () => { ctx.invalidateGroups(); state.groups = await ctx.groups(); buildToolbar(); load(); },
        });

        async function refreshList() {
            const groups = (await ctx.api.get('/api/groups')).groups;
            clear(list);
            groups.forEach((g, index) => {
                const input = h('input', { class: 'input input-sm', value: g.name, style: { maxWidth: '240px' }, disabled: g.is_default });
                const save = async () => {
                    const name = input.value.trim();
                    if (!name || name === g.name) { input.value = g.name; return; }
                    try { await ctx.api.patch(`/api/groups/${g.id}`, { name }); toast('이름을 바꿨습니다', 'success', { timeout: 1500 }); refreshList(); }
                    catch (error) { toast(error.message, 'error'); input.value = g.name; }
                };
                input.addEventListener('change', save);
                const move = async (dir) => {
                    const ids = groups.map(x => x.id);
                    const j = index + dir;
                    if (j < 0 || j >= ids.length) return;
                    [ids[index], ids[j]] = [ids[j], ids[index]];
                    await ctx.api.post('/api/groups/reorder', { ids });
                    refreshList();
                };
                list.appendChild(h('div', { class: 'row', style: { gap: '8px', padding: '6px 0', borderBottom: '1px solid var(--hairline)' } },
                    h('div', { class: 'row', style: { gap: '2px', flexWrap: 'nowrap' } },
                        h('button', { class: 'icon-btn', type: 'button', title: '위로', disabled: index === 0, onclick: () => move(-1) }, svg('arrowUp')),
                        h('button', { class: 'icon-btn', type: 'button', title: '아래로', disabled: index === groups.length - 1, onclick: () => move(1) }, svg('arrowDown'))),
                    input,
                    h('span', { class: 'muted', style: { fontSize: '12.5px' } }, `채널 ${g.channel_count}개`),
                    g.is_default ? badge('기본', 'outline') : null,
                    h('div', { class: 'spacer', style: { flex: 1 } }),
                    g.is_default ? null : h('button', { class: 'icon-btn', type: 'button', title: '삭제', onclick: async () => {
                        const ok = await confirmDialog({ title: '그룹 삭제', message: `"${g.name}" 그룹을 삭제합니다. 그룹의 채널 ${g.channel_count}개는 기본 그룹으로 이동합니다.`, confirmText: '삭제', danger: true });
                        if (!ok) return;
                        try { await ctx.api.delete(`/api/groups/${g.id}`); toast('그룹을 삭제했습니다', 'success', { timeout: 2000 }); refreshList(); }
                        catch (error) { toast(error.message, 'error'); }
                    } }, svg('trash')),
                ));
            });
        }
        addBtn.addEventListener('click', async () => {
            const name = nameInput.value.trim();
            if (!name) return toast('그룹 이름을 입력하세요', 'warn');
            try { await ctx.api.post('/api/groups', { name }); nameInput.value = ''; refreshList(); }
            catch (error) { toast(error.message, 'error'); }
        });
        nameInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') addBtn.click(); });
        await refreshList();
    }

    await load();
    if (params.query && params.query.get('add') === '1') openAddModal();
    const off = ctx.onRefreshDone(() => load());
    return () => off();
}
