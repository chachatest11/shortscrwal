// ========================================
// 채널 대시보드
// - /api/dashboard/overview : DB 기반 현황 조회 (API 쿼터 소모 없음)
// - /api/dashboard/refresh  : YouTube Data API로 갱신 (쿼터 소모)
// 공통 포맷 함수(formatViewCount, formatDate, escapeHtml)는 app.js 사용
// ========================================

const DASH_PREFS_KEY = 'dashboard_prefs';

const dashState = {
    days: 7,
    categoryId: 0,
    sort: 'subs_desc',
    query: '',
    autoRefreshMinutes: 0,
    maxVideos: 10,
    data: null,
    expanded: new Set(),
    refreshing: false,
    autoRefreshTimer: null
};

// ----------------------------------------
// 초기화
// ----------------------------------------

window.addEventListener('DOMContentLoaded', initDashboard);

function initDashboard() {
    loadPrefs();

    const period = byId('periodSelect');
    const category = byId('categorySelect');
    const sort = byId('sortSelect');
    const autoRefresh = byId('autoRefreshSelect');
    const maxVideos = byId('maxVideosInput');
    const search = byId('searchInput');

    setSelectValue(period, String(dashState.days), '7');
    dashState.days = parseInt(period.value, 10);
    setSelectValue(category, String(dashState.categoryId), '0');
    dashState.categoryId = parseInt(category.value, 10);
    setSelectValue(sort, dashState.sort, 'subs_desc');
    dashState.sort = sort.value;
    setSelectValue(autoRefresh, String(dashState.autoRefreshMinutes), '0');
    dashState.autoRefreshMinutes = parseInt(autoRefresh.value, 10);
    maxVideos.value = dashState.maxVideos;

    period.addEventListener('change', () => {
        dashState.days = parseInt(period.value, 10);
        savePrefs();
        loadOverview();
    });
    category.addEventListener('change', () => {
        dashState.categoryId = parseInt(category.value, 10);
        savePrefs();
        loadOverview();
    });
    sort.addEventListener('change', () => {
        dashState.sort = sort.value;
        savePrefs();
        renderTable();
    });
    autoRefresh.addEventListener('change', () => {
        dashState.autoRefreshMinutes = parseInt(autoRefresh.value, 10);
        savePrefs();
        setupAutoRefresh();
    });
    maxVideos.addEventListener('change', () => {
        const value = Math.min(50, Math.max(1, parseInt(maxVideos.value, 10) || 10));
        maxVideos.value = value;
        dashState.maxVideos = value;
        savePrefs();
    });
    search.addEventListener('input', () => {
        dashState.query = search.value.trim().toLowerCase();
        renderTable();
    });

    loadOverview();
    setupAutoRefresh();
    setInterval(updateLastRefreshLabel, 30000);
}

function loadPrefs() {
    try {
        const raw = localStorage.getItem(DASH_PREFS_KEY);
        if (!raw) return;
        const prefs = JSON.parse(raw);
        ['days', 'categoryId', 'sort', 'autoRefreshMinutes', 'maxVideos'].forEach(key => {
            if (prefs[key] !== undefined && prefs[key] !== null) {
                dashState[key] = prefs[key];
            }
        });
    } catch (error) {
        // 로컬 스토리지를 사용할 수 없어도 기본값으로 동작
    }
}

function savePrefs() {
    try {
        localStorage.setItem(DASH_PREFS_KEY, JSON.stringify({
            days: dashState.days,
            categoryId: dashState.categoryId,
            sort: dashState.sort,
            autoRefreshMinutes: dashState.autoRefreshMinutes,
            maxVideos: dashState.maxVideos
        }));
    } catch (error) {
        // 무시
    }
}

function setupAutoRefresh() {
    if (dashState.autoRefreshTimer) {
        clearInterval(dashState.autoRefreshTimer);
        dashState.autoRefreshTimer = null;
    }
    if (dashState.autoRefreshMinutes > 0) {
        dashState.autoRefreshTimer = setInterval(
            () => refreshDashboard(true),
            dashState.autoRefreshMinutes * 60 * 1000
        );
    }
}

// ----------------------------------------
// 데이터 로드 / 갱신
// ----------------------------------------

async function loadOverview() {
    const page = document.querySelector('.dashboard-page');
    page.classList.add('is-loading');

    try {
        const params = new URLSearchParams({
            category_id: dashState.categoryId,
            days: dashState.days
        });
        const response = await fetch(`/api/dashboard/overview?${params}`);
        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(extractDetail(error) || `HTTP ${response.status}`);
        }
        dashState.data = await response.json();

        renderKpis();
        renderTable();
        updateLastRefreshLabel();
        showNeverRefreshedHint();
    } catch (error) {
        console.error('대시보드 로드 실패:', error);
        showMessage('대시보드 데이터를 불러오지 못했습니다: ' + error.message, 'error');
    } finally {
        page.classList.remove('is-loading');
    }
}

async function refreshDashboard(isAuto = false) {
    if (dashState.refreshing) return;
    dashState.refreshing = true;

    const button = byId('btnRefresh');
    button.disabled = true;
    button.textContent = '업데이트 중...';
    showMessage(isAuto ? '자동 업데이트 중... YouTube에서 채널 현황을 가져오고 있습니다.' : 'YouTube에서 채널 현황을 가져오는 중입니다...', 'info');

    try {
        const response = await fetch('/api/dashboard/refresh', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                category_id: dashState.categoryId,
                include_videos: true,
                max_videos: dashState.maxVideos
            })
        });
        const result = await response.json().catch(() => ({}));

        if (!response.ok) {
            throw new Error(extractDetail(result) || `HTTP ${response.status}`);
        }

        if (result.updated === 0 && result.failed === 0) {
            showMessage(result.message || '업데이트할 활성 채널이 없습니다.', 'warn');
        } else {
            const parts = [
                `${result.updated}개 채널 업데이트 완료`,
                `최근 영상 ${result.videos_upserted}개 수집`,
                `API 쿼터 약 ${result.quota_used} units 사용`
            ];
            if (result.failed > 0) parts.push(`실패 ${result.failed}개`);
            const level = result.quota_exceeded ? 'error' : (result.errors && result.errors.length ? 'warn' : 'success');
            showMessage(parts.join(' · '), level, result.errors);
        }

        await loadOverview();
    } catch (error) {
        console.error('대시보드 업데이트 실패:', error);
        showMessage('업데이트 실패: ' + error.message, 'error');
    } finally {
        dashState.refreshing = false;
        button.disabled = false;
        button.textContent = '🔄 지금 업데이트';
    }
}

// ----------------------------------------
// KPI 타일
// ----------------------------------------

function renderKpis() {
    const row = byId('kpiRow');
    row.innerHTML = '';

    const data = dashState.data;
    if (!data) return;
    const s = data.summary;
    const periodLabel = periodText(data.period_days);
    const baselineNote = s.channels_with_baseline > 0 && s.channels_with_baseline < s.channel_count
        ? `${s.channels_with_baseline}/${s.channel_count}개 채널 기준`
        : null;

    const channelSub = s.channels_never_refreshed > 0
        ? { text: `${s.channels_never_refreshed}개 채널 미갱신`, warn: true }
        : { text: '활성 채널' };

    row.appendChild(kpiTile('채널', formatInt(s.channel_count), null, channelSub));
    const subsNote = s.channels_subscriber_hidden > 0
        ? `비공개 채널 ${s.channels_subscriber_hidden}개 제외`
        : baselineNote;
    row.appendChild(kpiTile('총 구독자', formatCompact(s.subscriber_count), deltaEl(s.subscriber_delta), { text: subsNote, period: periodLabel, hasDelta: true }));
    row.appendChild(kpiTile('총 조회수', formatCompact(s.view_count), deltaEl(s.view_delta), { text: baselineNote, period: periodLabel, hasDelta: true }));
    row.appendChild(kpiTile('총 영상 수', formatCompact(s.video_count), deltaEl(s.video_delta), { text: baselineNote, period: periodLabel, hasDelta: true }));

    const uploadSub = s.channels_without_upload > 0
        ? { text: `▲ 업로드 없는 채널 ${s.channels_without_upload}개`, warn: true }
        : { text: s.channel_count > 0 ? '모든 채널이 업로드함' : '' };
    const uploadsTile = kpiTile(`${periodLabel} 업로드`, formatInt(s.uploads_in_period), null, uploadSub);
    if (s.uploads_in_period > 0) {
        uploadsTile.appendChild(h('div', { class: 'kpi-sub' }, `업로드 영상 조회수 ${formatCompact(s.period_upload_views)}`));
    }
    row.appendChild(uploadsTile);
}

function kpiTile(label, value, delta, sub) {
    const tile = h('div', { class: 'kpi-tile' },
        h('div', { class: 'kpi-label' }, label),
        h('div', { class: 'kpi-value', title: value }, value)
    );

    if (delta) {
        const line = h('div', { class: 'kpi-delta' }, delta);
        if (sub && sub.period) {
            line.appendChild(h('span', { class: 'delta-period' }, `vs ${sub.period} 전`));
        }
        tile.appendChild(line);
    }

    if (sub && sub.text) {
        tile.appendChild(h('div', { class: 'kpi-sub' + (sub.warn ? ' warn' : '') }, sub.text));
    } else if (sub && sub.hasDelta && !sub.text) {
        // 빈 줄로 높이 맞춤
        tile.appendChild(h('div', { class: 'kpi-sub' }));
    }

    return tile;
}

// ----------------------------------------
// 채널 표
// ----------------------------------------

const sorters = {
    subs_desc: (a, b) => numDesc(a.subscriber_count, b.subscriber_count),
    subs_delta_desc: (a, b) => numDesc(a.delta.subscriber_count, b.delta.subscriber_count) || numDesc(a.subscriber_count, b.subscriber_count),
    views_delta_desc: (a, b) => numDesc(a.delta.view_count, b.delta.view_count) || numDesc(a.view_count, b.view_count),
    latest_upload: (a, b) => strDesc(a.latest_video && a.latest_video.published_at, b.latest_video && b.latest_video.published_at),
    stale_first: (a, b) => numDesc(a.days_since_upload, b.days_since_upload, true),
    uploads_desc: (a, b) => numDesc(a.uploads_in_period, b.uploads_in_period) || numDesc(a.subscriber_count, b.subscriber_count),
    title_asc: (a, b) => (a.title || '').localeCompare(b.title || '', 'ko')
};

function renderTable() {
    const body = byId('channelTableBody');
    const empty = byId('emptyState');
    const countLabel = byId('channelCountLabel');
    body.innerHTML = '';

    const data = dashState.data;
    if (!data) return;

    let channels = data.channels.slice();
    if (dashState.query) {
        channels = channels.filter(ch =>
            (ch.title || '').toLowerCase().includes(dashState.query) ||
            (ch.custom_url || '').toLowerCase().includes(dashState.query) ||
            ch.channel_id.toLowerCase().includes(dashState.query)
        );
    }
    channels.sort(sorters[dashState.sort] || sorters.subs_desc);

    countLabel.textContent = dashState.query
        ? `${channels.length} / ${data.channels.length}개`
        : `${data.channels.length}개`;

    if (channels.length === 0) {
        empty.innerHTML = '';
        if (data.channels.length === 0) {
            empty.append(
                '등록된 활성 채널이 없습니다.',
                h('br'),
                h('a', { href: '/' }, '쇼츠 수집 페이지'),
                '에서 운영 중인 채널의 URL, @핸들 또는 채널 ID를 등록한 뒤 "지금 업데이트"를 누르세요.'
            );
        } else {
            empty.textContent = '검색어와 일치하는 채널이 없습니다.';
        }
        empty.style.display = 'block';
        byId('channelTable').style.display = 'none';
        return;
    }

    empty.style.display = 'none';
    byId('channelTable').style.display = '';

    channels.forEach(ch => {
        const row = buildChannelRow(ch, data.period_days);
        body.appendChild(row);
        if (dashState.expanded.has(ch.channel_id)) {
            row.classList.add('expanded');
            const detail = buildDetailRow(ch);
            body.appendChild(detail);
            loadChannelVideos(ch, detail);
        }
    });
}

function buildChannelRow(ch, periodDays) {
    const row = h('tr', {
        class: 'channel-row' + (ch.is_active ? '' : ' inactive'),
        'data-channel-id': ch.channel_id
    });

    // 채널
    const avatar = ch.thumbnail_url
        ? h('img', { class: 'channel-avatar', src: ch.thumbnail_url, alt: '', loading: 'lazy', referrerpolicy: 'no-referrer' })
        : h('div', { class: 'channel-avatar', 'aria-hidden': 'true' }, (ch.title || '?').charAt(0).toUpperCase());

    const subParts = [];
    if (ch.custom_url) subParts.push(h('span', {}, ch.custom_url));
    if (ch.country) subParts.push(h('span', {}, ch.country));
    ch.categories.forEach(name => subParts.push(h('span', { class: 'category-badge' }, name)));
    if (!ch.is_active) subParts.push(h('span', {}, '비활성'));

    row.appendChild(h('td', {},
        h('div', { class: 'channel-cell' },
            avatar,
            h('div', { class: 'channel-cell-body' },
                h('a', {
                    class: 'channel-name',
                    href: channelUrl(ch),
                    target: '_blank',
                    rel: 'noopener',
                    title: ch.title
                }, ch.title),
                h('div', { class: 'channel-sub' }, subParts)
            )
        )
    ));

    // 구독자 / 조회수 / 영상 수
    if (ch.subscriber_hidden) {
        row.appendChild(h('td', { class: 'num' },
            h('div', { class: 'stat-cell' },
                h('span', { class: 'stat-value stat-muted', title: '채널 소유자가 구독자 수를 비공개로 설정했습니다' }, '비공개'),
                h('span', { class: 'delta delta-none' }, '구독자 비공개')
            )
        ));
    } else {
        row.appendChild(statCell(ch.subscriber_count, ch.delta.subscriber_count, ch.delta));
    }
    row.appendChild(statCell(ch.view_count, ch.delta.view_count, ch.delta));
    row.appendChild(statCell(ch.video_count, ch.delta.video_count, ch.delta));

    // 기간 업로드
    const uploadsCell = h('td', { class: 'num' },
        h('div', { class: 'stat-cell' },
            h('span', { class: 'stat-value' }, formatInt(ch.uploads_in_period)),
            ch.uploads_in_period > 0
                ? h('span', { class: 'stat-secondary' }, `조회수 ${formatCompact(ch.period_upload_views)}`)
                : h('span', { class: 'stat-secondary' }, `${periodText(periodDays)} 없음`)
        )
    );
    row.appendChild(uploadsCell);

    // 최근 업로드
    row.appendChild(h('td', {}, latestCell(ch)));

    // 스파크라인
    row.appendChild(h('td', {}, sparklineCell(ch)));

    // 펼침
    const expandBtn = h('button', {
        class: 'btn-expand',
        type: 'button',
        'aria-label': `${ch.title} 최근 영상 보기`,
        'aria-expanded': dashState.expanded.has(ch.channel_id) ? 'true' : 'false'
    }, '▶');
    row.appendChild(h('td', { class: 'col-expand' }, expandBtn));

    row.addEventListener('click', (event) => {
        if (event.target.closest('a')) return;
        toggleChannelDetails(ch, row);
    });

    return row;
}

function statCell(value, delta, deltaInfo) {
    return h('td', { class: 'num' },
        h('div', { class: 'stat-cell' },
            h('span', { class: 'stat-value', title: value == null ? '' : value.toLocaleString('ko-KR') }, formatCompact(value)),
            deltaEl(delta, deltaInfo)
        )
    );
}

function latestCell(ch) {
    const video = ch.latest_video;
    if (!video) {
        return h('div', { class: 'latest-cell' },
            h('span', { class: 'upload-status status-none' }, '수집된 영상 없음')
        );
    }

    const status = uploadStatus(ch);
    const meta = h('div', { class: 'latest-meta' },
        h('span', { class: `upload-status ${status.cls}` },
            h('span', { class: 'status-icon', 'aria-hidden': 'true' }, status.icon),
            status.label
        ),
        h('span', {}, `조회수 ${formatCompact(video.view_count)}`)
    );
    if (video.is_short) meta.appendChild(h('span', { class: 'shorts-badge' }, '쇼츠'));

    return h('div', { class: 'latest-cell' },
        video.thumbnail_url
            ? h('img', { class: 'latest-thumb', src: video.thumbnail_url, alt: '', loading: 'lazy' })
            : h('div', { class: 'latest-thumb' }),
        h('div', { class: 'latest-body' },
            h('a', {
                class: 'latest-title',
                href: `https://www.youtube.com/watch?v=${encodeURIComponent(video.video_id)}`,
                target: '_blank',
                rel: 'noopener',
                title: video.title
            }, video.title || video.video_id),
            meta
        )
    );
}

function uploadStatus(ch) {
    const days = ch.days_since_upload;
    if (days == null) return { cls: 'status-none', icon: '·', label: '알 수 없음' };
    if (days < 1) return { cls: 'status-good', icon: '●', label: '24시간 내 업로드' };
    if (days < 7) return { cls: 'status-ok', icon: '●', label: `${Math.floor(days)}일 전 업로드` };
    return { cls: 'status-warn', icon: '▲', label: `${Math.floor(days)}일째 업로드 없음` };
}

function sparklineCell(ch) {
    const points = ch.sparkline
        .map(p => p.subscriber_count)
        .filter(v => v !== null && v !== undefined);

    if (points.length < 2) {
        return h('span', { class: 'spark-empty' },
            points.length === 1 ? '추이 수집 중 (1회)' : '추이 데이터 없음');
    }

    const width = 120;
    const height = 32;
    const pad = 4;
    const min = Math.min(...points);
    const max = Math.max(...points);
    const range = (max - min) || 1;
    const stepX = (width - pad * 2) / (points.length - 1);
    const coords = points.map((v, i) => [
        pad + i * stepX,
        height - pad - ((v - min) / range) * (height - pad * 2)
    ]);
    const linePath = coords.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
    const areaPath = `${linePath} L${coords[coords.length - 1][0].toFixed(1)},${height - pad} L${coords[0][0].toFixed(1)},${height - pad} Z`;
    const [lastX, lastY] = coords[coords.length - 1];
    const first = ch.sparkline[0].captured_at;
    const label = `최근 30일 구독자 추이: ${points.length}개 시점, 최소 ${min.toLocaleString('ko-KR')}, 최대 ${max.toLocaleString('ko-KR')}`;

    // 숫자만 사용하므로 innerHTML 안전
    const svg = h('div', {
        html: `<svg class="spark" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" role="img">
            <path class="spark-area" d="${areaPath}"></path>
            <path class="spark-line" d="${linePath}"></path>
            <circle class="spark-dot" cx="${lastX.toFixed(1)}" cy="${lastY.toFixed(1)}" r="4"></circle>
        </svg>`
    });
    svg.querySelector('svg').setAttribute('aria-label', label);
    svg.title = label;

    return h('div', { class: 'spark-cell' },
        svg,
        h('span', { class: 'spark-range' }, `${formatShortDate(first)}~ · ${formatCompact(min)} → ${formatCompact(points[points.length - 1])}`)
    );
}

// ----------------------------------------
// 상세 행 (최근 영상)
// ----------------------------------------

function toggleChannelDetails(ch, row) {
    const button = row.querySelector('.btn-expand');
    const existing = row.nextElementSibling;
    const isOpen = existing && existing.classList.contains('detail-row');

    if (isOpen) {
        existing.remove();
        row.classList.remove('expanded');
        button.setAttribute('aria-expanded', 'false');
        dashState.expanded.delete(ch.channel_id);
        return;
    }

    const detail = buildDetailRow(ch);
    row.after(detail);
    row.classList.add('expanded');
    button.setAttribute('aria-expanded', 'true');
    dashState.expanded.add(ch.channel_id);
    loadChannelVideos(ch, detail);
}

function buildDetailRow(ch) {
    return h('tr', { class: 'detail-row' },
        h('td', { colspan: '8' },
            h('div', { class: 'detail-title' }, `${ch.title} · 최근 영상`),
            h('div', { class: 'video-list' }, h('span', { class: 'spark-empty' }, '불러오는 중...'))
        )
    );
}

async function loadChannelVideos(ch, detailRow) {
    const list = detailRow.querySelector('.video-list');
    try {
        const response = await fetch(`/api/dashboard/channels/${encodeURIComponent(ch.channel_id)}/videos?limit=20`);
        const data = await response.json();
        list.innerHTML = '';

        if (!data.videos || data.videos.length === 0) {
            list.appendChild(h('span', { class: 'spark-empty' }, '수집된 영상이 없습니다. "지금 업데이트"를 누르면 최근 영상을 가져옵니다.'));
            return;
        }

        data.videos.forEach(video => {
            const meta = h('div', { class: 'video-item-meta' },
                h('span', {}, formatDate(video.published_at)),
                h('span', {}, `조회 ${formatCompact(video.view_count)}`),
                h('span', {}, `좋아요 ${formatCompact(video.like_count)}`),
                h('span', {}, `댓글 ${formatCompact(video.comment_count)}`)
            );
            if (video.is_short) meta.appendChild(h('span', { class: 'shorts-badge' }, '쇼츠'));

            list.appendChild(h('div', { class: 'video-item' },
                video.thumbnail_url
                    ? h('img', { class: 'video-item-thumb', src: video.thumbnail_url, alt: '', loading: 'lazy' })
                    : h('div', { class: 'video-item-thumb' }),
                h('div', { class: 'video-item-body' },
                    h('a', {
                        class: 'video-item-title',
                        href: `https://www.youtube.com/watch?v=${encodeURIComponent(video.video_id)}`,
                        target: '_blank',
                        rel: 'noopener',
                        title: video.title
                    }, video.title || video.video_id),
                    meta
                )
            ));
        });
    } catch (error) {
        console.error('최근 영상 로드 실패:', error);
        list.innerHTML = '';
        list.appendChild(h('span', { class: 'spark-empty' }, '최근 영상을 불러오지 못했습니다.'));
    }
}

// ----------------------------------------
// 메시지 / 라벨
// ----------------------------------------

function showMessage(text, level = 'info', errors = null) {
    const box = byId('dashMessage');
    box.className = `dash-message ${level}`;
    box.innerHTML = '';
    box.appendChild(document.createTextNode(text));

    if (/API 키/.test(text)) {
        box.append(' ', h('a', { href: '/' }, '쇼츠 수집 페이지의 "API 키 관리"에서 키를 추가하세요.'));
    }

    if (errors && errors.length > 0) {
        const list = h('ul', { class: 'dash-message-errors' });
        errors.slice(0, 20).forEach(err => {
            list.appendChild(h('li', {}, `${err.channel_title || err.channel_id || '알 수 없음'}: ${err.error}`));
        });
        if (errors.length > 20) list.appendChild(h('li', {}, `외 ${errors.length - 20}건`));
        box.appendChild(list);
    }

    box.style.display = 'block';
}

function hideMessage() {
    byId('dashMessage').style.display = 'none';
}

function showNeverRefreshedHint() {
    const data = dashState.data;
    if (!data || data.channels.length === 0) return;
    const box = byId('dashMessage');
    if (!data.last_refresh_at && box.style.display === 'none') {
        showMessage('아직 YouTube에서 현황을 가져오지 않았습니다. 오른쪽 위 "지금 업데이트"를 누르면 구독자·조회수·최근 영상을 수집합니다.', 'info');
    }
}

function updateLastRefreshLabel() {
    const label = byId('lastRefreshLabel');
    const at = dashState.data && dashState.data.last_refresh_at;
    if (!at) {
        label.textContent = '마지막 업데이트: 없음';
        return;
    }
    label.textContent = `마지막 업데이트: ${formatDate(at)} (${formatDateTime(at)})`;
}

// ----------------------------------------
// 유틸리티
// ----------------------------------------

function byId(id) {
    return document.getElementById(id);
}

// DOM 생성 헬퍼: 텍스트는 항상 textContent로 넣어 XSS 방지
function h(tag, props = {}, ...children) {
    const el = document.createElement(tag);
    Object.entries(props || {}).forEach(([key, value]) => {
        if (value === null || value === undefined || value === false) return;
        if (key === 'class') el.className = value;
        else if (key === 'html') el.innerHTML = value;
        else el.setAttribute(key, value);
    });
    children.flat(Infinity).forEach(child => {
        if (child === null || child === undefined || child === false) return;
        el.appendChild(typeof child === 'string' || typeof child === 'number'
            ? document.createTextNode(String(child))
            : child);
    });
    return el;
}

function setSelectValue(select, value, fallback) {
    select.value = value;
    if (select.value !== value) select.value = fallback;
}

function extractDetail(payload) {
    if (!payload) return '';
    if (typeof payload.detail === 'string') return payload.detail;
    if (Array.isArray(payload.detail)) return payload.detail.map(e => e.msg || JSON.stringify(e)).join(', ');
    if (payload.detail) return JSON.stringify(payload.detail);
    return '';
}

function deltaEl(delta, info) {
    if (delta === null || delta === undefined) {
        return h('span', { class: 'delta delta-none', title: '비교할 이전 스냅샷이 없습니다. 다음 업데이트부터 증감이 표시됩니다.' }, '기준 없음');
    }
    const cls = delta > 0 ? 'delta-up' : (delta < 0 ? 'delta-down' : 'delta-flat');
    const icon = delta > 0 ? '▲' : (delta < 0 ? '▼' : '—');
    const text = (delta > 0 ? '+' : '') + formatCompact(delta);
    const el = h('span', { class: `delta ${cls}`, title: `${delta > 0 ? '+' : ''}${delta.toLocaleString('ko-KR')}` },
        h('span', { class: 'delta-icon', 'aria-hidden': 'true' }, icon),
        text
    );
    if (info && info.baseline_is_partial && info.baseline_at) {
        el.appendChild(h('span', { class: 'delta-partial' }, '*'));
        el.title += ` · ${formatShortDate(info.baseline_at)} 첫 수집 이후 (선택한 기간보다 짧음)`;
    }
    return el;
}

function numDesc(a, b, nullsFirst = false) {
    const aNull = a === null || a === undefined;
    const bNull = b === null || b === undefined;
    if (aNull && bNull) return 0;
    if (aNull) return nullsFirst ? -1 : 1;
    if (bNull) return nullsFirst ? 1 : -1;
    return b - a;
}

function strDesc(a, b) {
    if (!a && !b) return 0;
    if (!a) return 1;
    if (!b) return -1;
    return b.localeCompare(a);
}

function channelUrl(ch) {
    if (ch.custom_url && ch.custom_url.startsWith('@')) {
        return `https://www.youtube.com/${encodeURIComponent(ch.custom_url)}`;
    }
    return `https://www.youtube.com/channel/${encodeURIComponent(ch.channel_id)}`;
}

function periodText(days) {
    if (days === 1) return '24시간';
    return `${days}일`;
}

function formatInt(value) {
    if (value === null || value === undefined) return '—';
    return Number(value).toLocaleString('ko-KR');
}

function formatCompact(value) {
    if (value === null || value === undefined) return '—';
    const n = Number(value);
    if (!isFinite(n)) return '—';
    const sign = n < 0 ? '-' : '';
    const abs = Math.abs(n);

    if (abs >= 100000000) {
        return sign + trimZero(abs / 100000000, abs >= 1000000000 ? 0 : 1) + '억';
    }
    if (abs >= 10000) {
        // 1만 ~ 100만 미만: 소수 1자리 (15.2만), 100만 이상: 정수 (8,690만)
        return sign + trimZero(abs / 10000, abs >= 1000000 ? 0 : 1) + '만';
    }
    return sign + abs.toLocaleString('ko-KR');
}

function trimZero(value, digits) {
    const fixed = value.toFixed(digits);
    const num = Number(fixed);
    return num.toLocaleString('ko-KR', { maximumFractionDigits: digits });
}

function formatShortDate(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    if (isNaN(d.getTime())) return '';
    return `${d.getMonth() + 1}/${d.getDate()}`;
}

function formatDateTime(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    if (isNaN(d.getTime())) return '';
    const pad = n => String(n).padStart(2, '0');
    return `${d.getMonth() + 1}/${d.getDate()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
