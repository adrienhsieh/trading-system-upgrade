/**
 * static/js/thsr_sniper.js — 高鐵自動搶票（Tab 2）
 * 結合 thsr-ticket-monitor（定期監控找到座位就通知）與 THSR-Sniper（指定時間自動狂送請求完成訂票）。
 * 沿用 Tab 1（thsr.js / trading/api/thsr.py）已經在用、真的能自動解驗證碼並連上高鐵官網的後端邏輯，
 * 這裡只負責蒐集使用者填的條件、呼叫 /api/thsr/monitor 系列 API，以及顯示任務列表。
 */

let sniperInitialized = false;
let sniperPollTimer = null;

function sniperSetMsg(msg, isError = true) {
    const el = document.getElementById('sniper-start-msg');
    if (el) {
        el.style.color = isError ? '#ef4444' : '#10b981';
        el.textContent = msg || '';
    }
}

function sniperCurrentUsername() {
    return localStorage.getItem('username') || localStorage.getItem('display_name') || 'default';
}

/** 模式切換：watch（只監控）vs auto_book（凌晨自動搶票）要顯示的欄位不同 */
function sniperOnModeChange() {
    const mode = document.getElementById('sniper-mode').value;
    const isAutoBook = mode === 'auto_book';
    document.getElementById('sniper-auto-book-fields').style.display = isAutoBook ? '' : 'none';
    document.getElementById('sniper-auto-book-fields-2').style.display = isAutoBook ? '' : 'none';
    document.getElementById('sniper-release-fields').style.display = isAutoBook ? '' : 'none';
    document.getElementById('sniper-duration-field').style.display = isAutoBook ? '' : 'none';
}

/** 「凌晨00:00自動開始」 vs 自訂日期時間 */
function sniperOnReleaseModeChange() {
    const useMidnight = document.getElementById('sniper-release-midnight').checked;
    document.getElementById('sniper-release-custom').style.display = useMidnight ? 'none' : '';
}

/** 分頁初始化：載入站名/車廂/座位偏好下拉選單，並抓一次任務列表 */
async function initSniperTab() {
    if (!sniperInitialized) {
        try {
            const data = await api('GET', '/api/thsr/stations');
            if (data && data.ok) {
                const fillSelect = (id, items, valueKey, nameKey) => {
                    const el = document.getElementById(id);
                    if (!el) return;
                    el.innerHTML = items.map(it => `<option value="${it[valueKey]}">${it[nameKey]}</option>`).join('');
                };
                fillSelect('sniper-start', data.stations, 'id', 'name');
                fillSelect('sniper-dest', data.stations, 'id', 'name');
                fillSelect('sniper-class', data.seat_classes, 'value', 'name');
                fillSelect('sniper-seat', data.seat_prefers, 'value', 'name');
                // 起訖站給不同預設值，避免使用者忘記改到達站
                if (data.stations && data.stations.length > 1) {
                    document.getElementById('sniper-dest').selectedIndex = 1;
                }
            }
        } catch (e) {
            console.error('❌ 載入高鐵站點資料失敗', e);
        }

        const dateInput = document.getElementById('sniper-date');
        if (dateInput && !dateInput.value) {
            const d = new Date();
            d.setDate(d.getDate() + 1);
            dateInput.value = d.toISOString().slice(0, 10);
        }

        sniperOnModeChange();
        sniperOnReleaseModeChange();
        sniperInitialized = true;
    }

    await sniperRefreshTasks();

    // 頁籤停留時每 15 秒自動刷新一次任務狀態（背景 worker 本身仍持續運作，這裡只是讓畫面即時更新）
    if (sniperPollTimer) clearInterval(sniperPollTimer);
    sniperPollTimer = setInterval(() => {
        const panel = document.getElementById('tab-thsr-sniper');
        if (panel && panel.style.display !== 'none') {
            sniperRefreshTasks();
        } else {
            clearInterval(sniperPollTimer);
            sniperPollTimer = null;
        }
    }, 15000);
}

/** 組出建立任務要送出的 body */
function sniperCollectFormData() {
    const mode = document.getElementById('sniper-mode').value;
    const date = document.getElementById('sniper-date').value; // yyyy-mm-dd
    const searchDateForThsr = date.replaceAll('-', '/');       // 高鐵欄位格式 yyyy/mm/dd

    let releaseAt = null;
    if (mode === 'auto_book') {
        const useMidnight = document.getElementById('sniper-release-midnight').checked;
        if (useMidnight) {
            if (date) releaseAt = `${date}T00:00:00`;
        } else {
            const custom = document.getElementById('sniper-release-custom').value; // yyyy-MM-ddTHH:mm
            if (custom) releaseAt = custom.length === 16 ? `${custom}:00` : custom;
        }
    }

    const timeStart = document.getElementById('sniper-time-start').value || '';
    // search_time 是「查詢用」的起始時間代碼；後端會依 time_window_start 自動換算成合法的高鐵時刻代碼，
    // 這裡先給一個保底值，真正的篩選仍是靠 time_window_start / time_window_end。
    const searchTime = timeStart ? timeStart.replace(':', '') + 'A' : '600A';

    return {
        start_station: document.getElementById('sniper-start').value,
        end_station: document.getElementById('sniper-dest').value,
        search_date: searchDateForThsr,
        search_time: searchTime,
        mode: mode,
        ticket_type_pref: document.getElementById('sniper-ticket-type').value,
        time_window_start: timeStart,
        time_window_end: document.getElementById('sniper-time-end').value || '',
        adult_num: parseInt(document.getElementById('sniper-adult').value || '0', 10),
        child_num: parseInt(document.getElementById('sniper-child').value || '0', 10),
        disabled_num: parseInt(document.getElementById('sniper-disabled').value || '0', 10),
        elder_num: parseInt(document.getElementById('sniper-elder').value || '0', 10),
        college_num: parseInt(document.getElementById('sniper-college').value || '0', 10),
        seat_class: document.getElementById('sniper-class').value,
        seat_prefer: document.getElementById('sniper-seat').value,
        connected_seats: document.getElementById('sniper-connected-seats').checked,
        personal_id: (document.getElementById('sniper-personal-id').value || '').trim().toUpperCase(),
        phone: (document.getElementById('sniper-phone').value || '').trim(),
        release_at: releaseAt,
        max_duration_minutes: parseInt(document.getElementById('sniper-max-duration').value || '20', 10),
        notification_email: (document.getElementById('sniper-notify-email').value || '').trim() || null,
        notification_line: document.getElementById('sniper-notify-line').checked,
    };
}

async function sniperStart() {
    sniperSetMsg('');
    const body = sniperCollectFormData();

    if (!body.start_station || !body.end_station) {
        sniperSetMsg('請選擇出發站與到達站'); return;
    }
    if (body.start_station === body.end_station) {
        sniperSetMsg('出發站與到達站不能相同'); return;
    }
    if (!body.search_date) {
        sniperSetMsg('請選擇出發日期'); return;
    }
    if (body.mode === 'auto_book') {
        if (!/^[A-Z][0-9]{9}$/.test(body.personal_id)) {
            sniperSetMsg('自動搶票模式需要正確格式的身分證字號（例如 A123456789）'); return;
        }
        if (body.phone && !/^09\d{8}$/.test(body.phone)) {
            sniperSetMsg('手機格式錯誤，應為 09 開頭的10碼數字'); return;
        }
        if (!body.release_at) {
            sniperSetMsg('請設定自動搶票的開始時間'); return;
        }
    }

    try {
        const data = await api('POST', '/api/thsr/monitor', body);
        if (data && data.ok) {
            sniperSetMsg(data.message || '任務已建立', false);
            await sniperRefreshTasks();
        } else {
            sniperSetMsg((data && data.error) || '建立任務失敗');
        }
    } catch (e) {
        sniperSetMsg('建立任務失敗：' + (e.message || e));
    }
}

function sniperStatusLabel(status) {
    const map = {
        idle: '⚪ 待啟動', running: '🟢 執行中', paused: '⏸️ 已暫停',
        completed: '✅ 已完成', failed: '❌ 失敗',
    };
    return map[status] || status;
}

function sniperFormatResult(task) {
    if (!task.result_data) return '';
    try {
        const r = JSON.parse(task.result_data);
        if (r.booking_id) {
            return `訂位代號 ${r.booking_id}｜座位 ${r.seat || '-'}｜${r.price || ''}`;
        }
        if (r.matched_train) {
            return `找到車次 ${r.matched_train.id || ''}（${r.matched_train.depart || ''}）`;
        }
        return '';
    } catch (e) {
        return '';
    }
}

async function sniperRefreshTasks() {
    const tbody = document.getElementById('sniper-tasks-body');
    if (!tbody) return;
    try {
        const username = sniperCurrentUsername();
        const data = await api('GET', `/api/thsr/monitor/user/${encodeURIComponent(username)}`);
        if (!data || !data.ok) {
            tbody.innerHTML = `<tr><td colspan="7" style="color:#8b949e;">尚無任務</td></tr>`;
            return;
        }
        const tasks = data.tasks || [];
        if (tasks.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" style="color:#8b949e;">尚無任務</td></tr>`;
            return;
        }
        tbody.innerHTML = tasks.map(t => `
            <tr>
                <td>${t.start_station} → ${t.end_station}</td>
                <td>${t.search_date}${t.time_window_start ? ` ${t.time_window_start}~${t.time_window_end || ''}` : ''}</td>
                <td>${t.mode === 'auto_book' ? '🎯 自動搶票' : '👀 監控通知'}</td>
                <td>${sniperStatusLabel(t.status)}</td>
                <td style="font-size:11px;color:#8b949e;">${(t.last_check || t.updated_at || '').replace('T', ' ').slice(0, 19)}</td>
                <td style="font-size:11px;">${sniperFormatResult(t) || (t.error_msg || '')}</td>
                <td><button class="btn btn-sm" style="background:#d63939;color:#fff;" onclick="sniperDeleteTask('${t.task_id}')">刪除</button></td>
            </tr>
        `).join('');
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="7" style="color:#ef4444;">載入任務失敗：${e.message || e}</td></tr>`;
    }
}

async function sniperDeleteTask(taskId) {
    try {
        const data = await api('DELETE', `/api/thsr/monitor/${encodeURIComponent(taskId)}`);
        if (data && data.ok) {
            await sniperRefreshTasks();
        } else {
            alert((data && data.error) || '刪除失敗');
        }
    } catch (e) {
        alert('刪除失敗：' + (e.message || e));
    }
}

window.initSniperTab = initSniperTab;
window.sniperOnModeChange = sniperOnModeChange;
window.sniperOnReleaseModeChange = sniperOnReleaseModeChange;
window.sniperStart = sniperStart;
window.sniperRefreshTasks = sniperRefreshTasks;
window.sniperDeleteTask = sniperDeleteTask;
