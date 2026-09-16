// DOM 생성, 숫자/날짜 포맷, 토스트, 모달, 스파크라인 등 UI 유틸리티
import { icon } from './icons.js';

// ---------- DOM ----------

export function h(tag, props = {}, ...children) {
    const el = document.createElement(tag);
    for (const [key, value] of Object.entries(props || {})) {
        if (value === null || value === undefined || value === false) continue;
        if (key === 'class') el.className = value;
        else if (key === 'html') el.innerHTML = value;           // 신뢰할 수 있는 마크업(아이콘 등)만
        else if (key === 'text') el.textContent = value;
        else if (key === 'style' && typeof value === 'object') Object.assign(el.style, value);
        else if (key.startsWith('on') && typeof value === 'function') el.addEventListener(key.slice(2).toLowerCase(), value);
        else if (key === 'dataset') Object.assign(el.dataset, value);
        else if (value === true) el.setAttribute(key, '');
        else el.setAttribute(key, value);
    }
    append(el, children);
    return el;
}

export function append(el, children) {
    for (const child of children.flat(Infinity)) {
        if (child === null || child === undefined || child === false) continue;
        el.appendChild(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return el;
}

export function svg(name, cls) {
    const tpl = document.createElement('template');
    tpl.innerHTML = icon(name, cls);
    return tpl.content.firstChild;
}

export function clear(el) {
    while (el.firstChild) el.removeChild(el.firstChild);
    return el;
}

export function debounce(fn, ms = 250) {
    let timer = null;
    return (...args) => {
        clearTimeout(timer);
        timer = setTimeout(() => fn(...args), ms);
    };
}

// ---------- 포맷 ----------

function trim(value, digits) {
    return Number(value.toFixed(digits)).toLocaleString('ko-KR', { maximumFractionDigits: digits });
}

export const fmt = {
    int(n) {
        if (n === null || n === undefined || Number.isNaN(Number(n))) return '—';
        return Number(n).toLocaleString('ko-KR');
    },
    compact(n) {
        if (n === null || n === undefined || Number.isNaN(Number(n))) return '—';
        const v = Number(n);
        const sign = v < 0 ? '-' : '';
        const a = Math.abs(v);
        if (a >= 1e8) return sign + trim(a / 1e8, a >= 1e9 ? 0 : 1) + '억';
        if (a >= 1e4) return sign + trim(a / 1e4, a >= 1e6 ? 0 : 1) + '만';
        return sign + Math.round(a).toLocaleString('ko-KR');
    },
    signed(n, compact = true) {
        if (n === null || n === undefined) return '—';
        const v = Number(n);
        const body = compact ? fmt.compact(Math.abs(v)) : fmt.int(Math.abs(v));
        return v > 0 ? '+' + body : v < 0 ? '-' + body : '0';
    },
    pct(ratio, digits = 0) {
        if (ratio === null || ratio === undefined) return '—';
        return (ratio * 100).toFixed(digits) + '%';
    },
    multiple(ratio) {
        if (ratio === null || ratio === undefined) return '—';
        return ratio.toFixed(ratio >= 10 ? 0 : 1) + '×';
    },
    date(iso) {
        const d = parseDate(iso);
        if (!d) return '';
        return `${d.getFullYear()}.${pad(d.getMonth() + 1)}.${pad(d.getDate())}`;
    },
    shortDate(iso) {
        const d = parseDate(iso);
        if (!d) return '';
        return `${d.getMonth() + 1}/${d.getDate()}`;
    },
    datetime(iso) {
        const d = parseDate(iso);
        if (!d) return '';
        return `${d.getMonth() + 1}/${d.getDate()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
    },
    relative(iso) {
        const d = parseDate(iso);
        if (!d) return '';
        const diff = (Date.now() - d.getTime()) / 1000;
        if (diff < 0) return '방금';
        if (diff < 60) return '방금 전';
        if (diff < 3600) return `${Math.floor(diff / 60)}분 전`;
        if (diff < 86400) return `${Math.floor(diff / 3600)}시간 전`;
        if (diff < 86400 * 30) return `${Math.floor(diff / 86400)}일 전`;
        if (diff < 86400 * 365) return `${Math.floor(diff / 86400 / 30)}개월 전`;
        return `${Math.floor(diff / 86400 / 365)}년 전`;
    },
    days(days) {
        if (days === null || days === undefined) return '—';
        if (days < 1) return `${Math.max(1, Math.round(days * 24))}시간`;
        return `${Math.floor(days)}일`;
    },
    duration(sec) {
        if (sec === null || sec === undefined) return '';
        const s = Math.max(0, Math.round(sec));
        const hh = Math.floor(s / 3600), mm = Math.floor((s % 3600) / 60), ss = s % 60;
        return hh ? `${hh}:${pad(mm)}:${pad(ss)}` : `${mm}:${pad(ss)}`;
    },
    bytes(n) {
        if (!n) return '0 B';
        const units = ['B', 'KB', 'MB', 'GB'];
        let i = 0, v = n;
        while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
        return `${v.toFixed(i ? 1 : 0)} ${units[i]}`;
    },
};

export function parseDate(iso) {
    if (!iso) return null;
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? null : d;
}

function pad(n) { return String(n).padStart(2, '0'); }

export function periodLabel(days) {
    if (days === 1) return '24시간';
    return `${days}일`;
}

// ---------- 작은 컴포넌트 ----------

export function deltaEl(value, { partial = false, baselineAt = null, compact = true, invert = false, suffix = '' } = {}) {
    if (value === null || value === undefined) {
        return h('span', { class: 'delta none', title: '비교할 이전 기록이 없습니다. 다음 갱신부터 증감이 표시됩니다.' }, '기준 없음');
    }
    const v = Number(value);
    const positive = invert ? v < 0 : v > 0;
    const negative = invert ? v > 0 : v < 0;
    const cls = v === 0 ? 'flat' : positive ? 'up' : 'down';
    const el = h('span', { class: `delta ${cls}`, title: `${v > 0 ? '+' : ''}${fmt.int(v)}` });
    if (v !== 0) el.appendChild(svg(v > 0 ? 'arrowUp' : 'arrowDown'));
    el.appendChild(document.createTextNode(fmt.signed(v, compact) + suffix));
    if (partial) {
        el.appendChild(h('span', { class: 'partial', title: `${fmt.shortDate(baselineAt)} 첫 기록 이후 (선택한 기간보다 짧음)` }, '*'));
    }
    return el;
}

export function avatarEl(item, size = '') {
    const title = item.title || item.channel_title || '?';
    if (item.thumbnail_url || item.channel_thumbnail) {
        return h('img', { class: `avatar ${size}`, src: item.thumbnail_url || item.channel_thumbnail, alt: '', loading: 'lazy', referrerpolicy: 'no-referrer' });
    }
    return h('span', { class: `avatar ${size}`, 'aria-hidden': 'true' }, title.charAt(0).toUpperCase());
}

export function thumbEl(video, cls = 'thumb') {
    if (video.thumbnail_url) {
        return h('img', { class: cls, src: video.thumbnail_url, alt: '', loading: 'lazy', referrerpolicy: 'no-referrer' });
    }
    return h('span', { class: cls });
}

export function badge(text, kind = '', iconName = null) {
    const el = h('span', { class: `badge ${kind}` });
    if (iconName) el.appendChild(svg(iconName));
    el.appendChild(document.createTextNode(text));
    return el;
}

export function uploadStatus(daysSince, hasVideos = true, staleDays = 7) {
    if (!hasVideos || daysSince === null || daysSince === undefined) return { kind: '', icon: 'minus', label: '영상 없음' };
    if (daysSince < 1) return { kind: 'good', icon: 'zap', label: '24시간 내 업로드' };
    if (daysSince < staleDays) return { kind: '', icon: 'clock', label: `${Math.floor(daysSince)}일 전 업로드` };
    return { kind: 'warn', icon: 'alert', label: `${Math.floor(daysSince)}일째 업로드 없음` };
}

export function emptyState({ iconName = 'inbox', title, text, action }) {
    return h('div', { class: 'empty' }, svg(iconName), h('h4', {}, title), text ? h('p', {}, text) : null, action || null);
}

export function sparkline(points, key = 'subscriber_count', { width = 120, height = 32 } = {}) {
    const values = (points || []).map(p => (typeof p === 'number' ? p : p[key])).filter(v => v !== null && v !== undefined);
    if (values.length < 2) {
        return h('span', { class: 'spark-empty' }, values.length === 1 ? '추이 수집 중' : '추이 없음');
    }
    const pad = 4;
    const min = Math.min(...values), max = Math.max(...values), range = (max - min) || 1;
    const stepX = (width - pad * 2) / (values.length - 1);
    const coords = values.map((v, i) => [pad + i * stepX, height - pad - ((v - min) / range) * (height - pad * 2)]);
    const line = coords.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
    const area = `${line} L${coords[coords.length - 1][0].toFixed(1)},${height - pad} L${coords[0][0].toFixed(1)},${height - pad} Z`;
    const [lx, ly] = coords[coords.length - 1];
    const label = `${values.length}개 시점, 최소 ${fmt.int(min)}, 최대 ${fmt.int(max)}`;
    const wrapper = h('span', {
        title: label,
        html: `<svg class="spark" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" role="img" aria-label="${label}">
            <path class="spark-area" d="${area}"></path><path class="spark-line" d="${line}"></path>
            <circle class="spark-dot" cx="${lx.toFixed(1)}" cy="${ly.toFixed(1)}" r="3.5"></circle></svg>`,
    });
    return wrapper;
}

// ---------- 토스트 ----------

const TOAST_ICON = { success: 'checkCircle', error: 'xCircle', warn: 'alert', info: 'info' };

export function toast(message, type = 'info', { timeout = 4500 } = {}) {
    const stack = document.getElementById('toasts');
    const el = h('div', { class: `toast ${type}`, role: 'status' }, svg(TOAST_ICON[type] || 'info'),
        h('span', { class: 'toast-msg' }, message),
        h('button', { class: 'toast-close', type: 'button', 'aria-label': '닫기', onclick: () => el.remove() }, svg('x')));
    stack.appendChild(el);
    if (timeout) setTimeout(() => el.remove(), timeout);
    return el;
}

// ---------- 모달 ----------

export function openModal({ title, body, footer, wide = false, onClose } = {}) {
    const dialog = h('dialog', { class: `modal${wide ? ' wide' : ''}` });
    const closeBtn = h('button', { class: 'icon-btn', type: 'button', 'aria-label': '닫기', onclick: () => dialog.close() }, svg('x'));
    dialog.appendChild(h('div', { class: 'modal-header' }, h('h2', {}, title), closeBtn));
    const bodyEl = h('div', { class: 'modal-body' });
    append(bodyEl, [body]);
    dialog.appendChild(bodyEl);
    if (footer) {
        const footEl = h('div', { class: 'modal-footer' });
        append(footEl, [footer]);
        dialog.appendChild(footEl);
    }
    dialog.addEventListener('click', (event) => {
        if (event.target === dialog) dialog.close();
    });
    dialog.addEventListener('close', () => {
        dialog.remove();
        if (onClose) onClose();
    });
    document.body.appendChild(dialog);
    dialog.showModal();
    return dialog;
}

export function confirmDialog({ title, message, confirmText = '확인', danger = false }) {
    return new Promise((resolve) => {
        let result = false;
        const dialog = openModal({
            title,
            body: h('p', { style: { fontSize: '14px', color: 'var(--text-2)' } }, message),
            footer: [
                h('button', { class: 'btn btn-secondary', type: 'button', onclick: () => dialog.close() }, '취소'),
                h('button', { class: `btn ${danger ? 'btn-danger' : 'btn-primary'}`, type: 'button', onclick: () => { result = true; dialog.close(); } }, confirmText),
            ],
            onClose: () => resolve(result),
        });
    });
}

export function setBusy(button, busy) {
    if (!button) return;
    button.disabled = busy;
    button.classList.toggle('is-busy', busy);
}

export function youtubeChannelUrl(ch) {
    if (ch.handle) return `https://www.youtube.com/${encodeURIComponent(ch.handle)}`;
    return `https://www.youtube.com/channel/${encodeURIComponent(ch.youtube_id)}`;
}

export function youtubeVideoUrl(id) {
    return `https://www.youtube.com/watch?v=${encodeURIComponent(id)}`;
}

export function studioUrl(ch) {
    return `https://studio.youtube.com/channel/${encodeURIComponent(ch.youtube_id)}`;
}

export function externalLink(href, text, cls = '') {
    return h('a', { href, target: '_blank', rel: 'noopener', class: cls }, text);
}

// 로컬 저장 (실패해도 무시)
export const store = {
    get(key, fallback = null) {
        try {
            const raw = localStorage.getItem('cb:' + key);
            return raw === null ? fallback : JSON.parse(raw);
        } catch (e) { return fallback; }
    },
    set(key, value) {
        try { localStorage.setItem('cb:' + key, JSON.stringify(value)); } catch (e) { /* 무시 */ }
    },
};
