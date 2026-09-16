// 서버 API 호출 래퍼
export class ApiError extends Error {
    constructor(message, status, payload) {
        super(message);
        this.status = status;
        this.payload = payload;
    }
}

function detailOf(payload, fallback) {
    if (!payload) return fallback;
    if (typeof payload.detail === 'string') return payload.detail;
    if (Array.isArray(payload.detail)) {
        return payload.detail.map(e => (e.loc ? e.loc.slice(1).join('.') + ': ' : '') + (e.msg || JSON.stringify(e))).join(', ');
    }
    if (payload.detail) return JSON.stringify(payload.detail);
    return fallback;
}

async function request(method, path, { params, body } = {}) {
    const url = new URL(path, window.location.origin);
    if (params) {
        Object.entries(params).forEach(([k, v]) => {
            if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, v);
        });
    }
    const init = { method, headers: {} };
    if (body !== undefined) {
        init.headers['Content-Type'] = 'application/json';
        init.body = JSON.stringify(body);
    }
    let response;
    try {
        response = await fetch(url, init);
    } catch (error) {
        throw new ApiError('서버에 연결할 수 없습니다. 서버가 실행 중인지 확인하세요.', 0, null);
    }
    let payload = null;
    const text = await response.text();
    if (text) {
        try { payload = JSON.parse(text); } catch (e) { payload = { detail: text.slice(0, 300) }; }
    }
    if (!response.ok) {
        throw new ApiError(detailOf(payload, `요청 실패 (HTTP ${response.status})`), response.status, payload);
    }
    return payload;
}

export const api = {
    get: (path, params) => request('GET', path, { params }),
    post: (path, body) => request('POST', path, { body }),
    put: (path, body) => request('PUT', path, { body }),
    patch: (path, body) => request('PATCH', path, { body }),
    delete: (path) => request('DELETE', path),
};
