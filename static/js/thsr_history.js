/**
 * static/js/thsr_history.js — 高鐵訂位查詢／取消（Tab 3）
 * 對應後端 trading/api/thsr_history.py。
 * 上半部列出「我在本系統訂過的票」（來自 thsr_ticket/records/booking_db.py），
 * 下半部是即時連線官網的查詢/取消流程（比照 Tab1 的驗證碼三圖併列 + AI 自動填入模式）。
 */

let historySessionId = null;
let historyInitialized = false;
let isHistoryStarting = false;
let isHistoryQuerying = false;
let isHistoryCancelling = false;

function historySetQueryMsg(msg, isError = true) {
    const el = document.getElementById('history-query-msg');
    if (el) { el.style.color = isError ? '#ef4444' : '#10b981'; el.textContent = msg || ''; }
}

function historySetCancelMsg(msg, isError = true) {
    const el = document.getElementById('history-cancel-msg');
    if (el) { el.style.color = isError ? '#ef4444' : '#10b981'; el.textContent = msg || ''; }
}

function historyRenderCaptchaImages(r) {
    const rawEl = document.getElementById('history-captcha-img');
    const cleanedEl = document.getElementById('history-captcha-cleaned-img');
    if (rawEl && r.captcha_image) rawEl.src = 'data:image/png;base64,' + r.captcha_image;
    if (cleanedEl && r.cleaned_image) cleanedEl.src = 'data:image/png;base64,' + r.cleaned_image;
    const inputEl = document.getElementById('history-captcha-val');
    if (inputEl) inputEl.value = r.captcha_guess || '';
}

async function initHistoryTab() {
    if (!historyInitialized) {
        historyInitialized = true;
    }
    await historyRefreshMyBookings();
}

function historySourceLabel(source) {
    return source === 'auto_book' ? '🎯 自動搶票' : '🖐️ 手動訂票';
}

function historyStatusLabel(status) {
    return status === 'cancelled' ? '❌ 已取消' : '✅ 已訂票';
}

async function historyRefreshMyBookings() {
    const tbody = document.getElementById('history-my-bookings-body');
    if (!tbody) return;
    try {
        const data = await api('GET', '/api/thsr/history/my-bookings');
        const bookings = (data && data.bookings) || [];
        if (bookings.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" style="color:#8b949e;">目前還沒有透過本系統訂過票</td></tr>`;
            return;
        }
        tbody.innerHTML = bookings.map(b => `
            <tr>
                <td>${b.booking_id}</td>
                <td>${b.start_station || ''} → ${b.dest_station || ''}</td>
                <td>${b.travel_date || ''} ${b.train_id || ''} ${b.depart_time || ''}</td>
                <td>${b.seat || ''}</td>
                <td>${historySourceLabel(b.source)}</td>
                <td>${historyStatusLabel(b.status)}</td>
                <td style="white-space:nowrap;">
                    <button class="btn btn-sm" onclick="historyPrefill('${b.personal_id}','${b.booking_id}')">查詢/取消</button>
                    <button class="btn btn-sm" onclick="historyShowDetail('${b.booking_id}')">詳情</button>
                    <button class="btn btn-sm btn-danger" onclick="historyDeleteBooking('${b.booking_id}')">刪除</button>
                </td>
            </tr>
        `).join('');
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="7" style="color:#ef4444;">載入失敗：${e.message || e}</td></tr>`;
    }
}

/** 從「我的訂票」列表點「查詢/取消」時，自動開新一輪查詢流程並帶入證件號碼/訂位代號 */
async function historyPrefill(personalId, orderId) {
    await historyStart();
    const idInput = document.getElementById('history-roc-id');
    const orderInput = document.getElementById('history-order-id');
    if (idInput) idInput.value = personalId || '';
    if (orderInput) orderInput.value = orderId || '';
    const step2 = document.getElementById('history-step-2');
    if (step2) step2.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ── 本地訂票紀錄維護：詳情／編輯／刪除 ────────────────────────────
let _bookingDetailCache = null;

const _bookingDetailRows = [
    ['booking_id', '訂位代號'], ['status', '狀態'], ['source', '來源'],
    ['personal_id', '取票識別碼/身分證字號'], ['phone', '聯絡電話'],
    ['start_station', '出發站'], ['dest_station', '到達站'], ['travel_date', '乘車日期'],
    ['train_id', '車次'], ['depart_time', '出發時刻'], ['arrival_time', '到達時刻'],
    ['seat', '座位'], ['seat_class', '車廂'], ['ticket_num_info', '票種'],
    ['price', '票價'], ['payment_deadline', '付款期限'],
    ['created_at', '建立時間'], ['cancelled_at', '取消時間'],
];

async function historyShowDetail(bookingId) {
    try {
        const r = await api('GET', `/api/thsr/history/records/${bookingId}`);
        if (!r || !r.ok) { alert('查詢紀錄失敗：' + (r && r.error || '未知錯誤')); return; }
        _bookingDetailCache = r.booking;
        const b = r.booking;
        const body = document.getElementById('booking-detail-body');
        if (body) {
            body.innerHTML = _bookingDetailRows.map(([key, label]) => {
                let val = b[key];
                if (key === 'source') val = historySourceLabel(val);
                if (key === 'status') val = historyStatusLabel(val);
                return `<div style="display:flex;justify-content:space-between;border-bottom:1px solid var(--border,#2a2f3a);"><span style="color:#8b949e;">${label}</span><span>${val ?? '－'}</span></div>`;
            }).join('');
        }
        document.getElementById('booking-detail-modal').classList.add('open');
    } catch (e) {
        alert('查詢紀錄失敗：' + (e.message || e));
    }
}

function historyOpenEditFromDetail() {
    if (!_bookingDetailCache) return;
    const b = _bookingDetailCache;
    document.getElementById('booking-edit-personal-id').value = b.personal_id || '';
    document.getElementById('booking-edit-phone').value = b.phone || '';
    document.getElementById('booking-edit-status').value = b.status || 'booked';
    closeModal('booking-detail-modal');
    document.getElementById('booking-edit-modal').classList.add('open');
}

async function historySaveBookingEdit() {
    if (!_bookingDetailCache) return;
    const bookingId = _bookingDetailCache.booking_id;
    const payload = {
        personal_id: document.getElementById('booking-edit-personal-id').value.trim(),
        phone: document.getElementById('booking-edit-phone').value.trim(),
        status: document.getElementById('booking-edit-status').value,
    };
    try {
        const r = await api('PATCH', `/api/thsr/history/records/${bookingId}`, payload);
        if (!r || !r.ok) { alert('更新失敗：' + (r && r.error || '未知錯誤')); return; }
        closeModal('booking-edit-modal');
        await historyRefreshMyBookings();
    } catch (e) {
        alert('更新失敗：' + (e.message || e));
    }
}

async function historyDeleteBooking(bookingId) {
    if (!confirm(`確定要刪除這筆本地訂票紀錄（${bookingId}）嗎？\n⚠️ 這只會刪除本地備忘紀錄，不會連線去高鐵官網取消訂位。\n如果票還沒真的取消，請先用「查詢/取消」完成官方取消，再刪除本地紀錄。`)) return;
    try {
        const r = await api('DELETE', `/api/thsr/history/records/${bookingId}`);
        if (!r || !r.ok) { alert('刪除失敗：' + (r && r.error || '未知錯誤')); return; }
        if (r.warning) alert('⚠️ ' + r.warning);
        await historyRefreshMyBookings();
    } catch (e) {
        alert('刪除失敗：' + (e.message || e));
    }
}

function historyDeleteFromDetail() {
    if (!_bookingDetailCache) return;
    closeModal('booking-detail-modal');
    historyDeleteBooking(_bookingDetailCache.booking_id);
}

async function historyStart() {
    if (isHistoryStarting) return;
    historySetQueryMsg('正在連線高鐵「訂位查詢」頁面並取得驗證碼...', false);
    isHistoryStarting = true;
    try {
        const r = await api('POST', '/api/thsr/history/start', {});
        if (!r.ok) {
            historySetQueryMsg(r.error || '連線失敗');
            return;
        }
        historySessionId = r.session_id;
        historyRenderCaptchaImages(r);
        document.getElementById('history-step-2').style.display = '';
        document.getElementById('history-result').style.display = 'none';
        historySetQueryMsg('');
    } catch (e) {
        historySetQueryMsg('連線失敗，請稍後再試：' + (e.message || e));
    } finally {
        isHistoryStarting = false;
    }
}

async function historyRefreshCaptcha() {
    if (!historySessionId) return;
    try {
        const r = await api('POST', '/api/thsr/history/refresh-captcha', { session_id: historySessionId });
        if (r.ok) historyRenderCaptchaImages(r);
    } catch (e) {
        console.error('刷新驗證碼失敗', e);
    }
}

async function historyQuery() {
    if (isHistoryQuerying) return;
    if (!historySessionId) {
        historySetQueryMsg('請先點「開始查詢」取得驗證碼');
        return;
    }
    const idType = document.getElementById('history-id-type').value;
    const rocId = (document.getElementById('history-roc-id').value || '').trim().toUpperCase();
    const orderId = (document.getElementById('history-order-id').value || '').trim().toUpperCase();
    const code = (document.getElementById('history-captcha-val').value || '').trim();

    if (!rocId || !orderId) {
        historySetQueryMsg('請輸入證件號碼與訂位代號');
        return;
    }
    if (!code) {
        historySetQueryMsg('請輸入驗證碼');
        return;
    }

    historySetQueryMsg('查詢中...', false);
    isHistoryQuerying = true;
    try {
        const r = await api('POST', '/api/thsr/history/query', {
            session_id: historySessionId, id_type: idType, roc_id: rocId, order_id: orderId, security_code: code,
        });
        if (!r.ok) {
            const errMsg = (Array.isArray(r.errors) ? r.errors.join('；') : null) || r.error || '查詢失敗';
            historySetQueryMsg(errMsg);
            if (r.captcha_image) historyRenderCaptchaImages(r);
            return;
        }
        historySetQueryMsg('');
        historyRenderResult(r.booking);
    } catch (e) {
        historySetQueryMsg('連線失敗，請稍後再試：' + (e.message || e));
    } finally {
        isHistoryQuerying = false;
    }
}

function historyRenderResult(b) {
    const box = document.getElementById('history-result');
    const body = document.getElementById('history-result-body');
    const cancelBtn = document.getElementById('history-cancel-btn');
    box.style.display = '';
    historySetCancelMsg('');
    body.innerHTML = `
        <tr><td style="color:#8b949e;">訂位代號</td><td><b>${b.booking_id}</b></td></tr>
        <tr><td style="color:#8b949e;">路線</td><td>${b.start_station} → ${b.dest_station}</td></tr>
        <tr><td style="color:#8b949e;">日期/車次</td><td>${b.date} ${b.train_id} (${b.depart_time} → ${b.arrival_time})</td></tr>
        <tr><td style="color:#8b949e;">座位</td><td>${b.seat}</td></tr>
        <tr><td style="color:#8b949e;">票價</td><td>${b.price || '--'}</td></tr>
        <tr><td style="color:#8b949e;">付款狀態</td><td>${b.payment_status || '--'}</td></tr>
    `;
    cancelBtn.style.display = b.cancellable ? '' : 'none';
    if (!b.cancellable) {
        historySetCancelMsg('此筆訂位目前無法取消（可能已取消、已搭乘或已超過可取消時限）', false);
    }
}

async function historyCancel() {
    if (isHistoryCancelling) return;
    if (!historySessionId) return;
    if (!confirm('確定要取消這筆訂位嗎？此操作無法復原。')) return;

    historySetCancelMsg('送出取消請求中...', false);
    isHistoryCancelling = true;
    try {
        const r = await api('POST', '/api/thsr/history/cancel', { session_id: historySessionId });
        if (!r.ok) {
            const errMsg = (Array.isArray(r.errors) ? r.errors.join('；') : null) || r.error || '取消失敗';
            historySetCancelMsg(errMsg);
            return;
        }
        historySetCancelMsg(r.message || '取消成功', false);
        document.getElementById('history-cancel-btn').style.display = 'none';
        await historyRefreshMyBookings();
    } catch (e) {
        historySetCancelMsg('連線失敗，請稍後再試：' + (e.message || e));
    } finally {
        isHistoryCancelling = false;
    }
}

window.initHistoryTab = initHistoryTab;
window.historyRefreshMyBookings = historyRefreshMyBookings;
window.historyPrefill = historyPrefill;
window.historyStart = historyStart;
window.historyRefreshCaptcha = historyRefreshCaptcha;
window.historyQuery = historyQuery;
window.historyCancel = historyCancel;
