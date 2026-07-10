/**
 * static/js/thsr.js — 台灣高鐵訂票流程全功能整合版 (1/3)
 * 涵蓋內容：全域變數、基礎 UI 狀態控制、下拉選單動態初始化與資料對齊。
 */

let thsrSessionId = null;
let thsrInitialized = false;

// ── 基礎訊息與狀態控制 ────────────────────────────────────────────────

/**
 * 設置指定步驟的提示訊息
 * @param {number|string} step 步驟編號或識別字
 * @param {string} msg 訊息內容
 * @param {boolean} isError 是否為錯誤訊息（預設為 true 顯示紅色；false 顯示綠色）
 */
function thsrSetMsg(step, msg, isError = true) {
    const el = document.getElementById(`thsr-step${step}-msg`) || document.getElementById(`thsr-msg-${step}`);
    if (el) {
        el.style.color = isError ? '#ef4444' : '#10b981';
        el.textContent = msg || '';
    }
}

/**
 * 切換顯示特定的步驟區塊（隱藏其他步驟）
 * @param {number} n 要顯示的步驟編號 (1~5)
 */
function thsrShowStep(n) {
    for (let i = 1; i <= 5; i++) {
        const el = document.getElementById(`thsr-step-${i}`);
        if (el) el.style.display = (i === n) ? '' : 'none';
    }
}

/**
 * 返回上一步。
 * 🛠️ 修正：先前 index.html 裡「修改條件」「重看驗證碼」「重選車次」都呼叫這個函式，
 * 但整支 thsr.js 從沒定義過它，點下去只會噴 ReferenceError、完全沒反應。
 * 上一步的畫面（驗證碼圖片、車次列表等）都還在 DOM 裡，不需要重新呼叫 API，
 * 單純把該步驟區塊切回顯示即可。
 * @param {number} n 要返回的步驟編號
 */
function thsrPrevStep(n) {
    thsrSetMsg(n, '');
    thsrShowStep(n);
}

/**
 * 初始化高鐵分頁功能（由外部頁簽切換事件或 DOMReady 觸發）
 */
async function initThsrTab() {
    if (thsrInitialized) return;
    thsrInitialized = true;
    await thsrLoadStations();
    
    // 自動預設出發日期為明天，並限制最小日期為今天
    const dateInput = document.getElementById('thsr-date');
    if (dateInput) {
        const today = new Date();
        const tomorrow = new Date(Date.now() + 24 * 3600 * 1000);
        dateInput.value = tomorrow.toISOString().slice(0, 10);
        dateInput.min = today.toISOString().slice(0, 10);
    }
}

/**
 * 自後端 API 載入車站、時間表、車廂、座位偏好等下拉選單資料
 */
async function thsrLoadStations() {
    try {
        const r = await api('GET', '/api/thsr/stations');
        if (!r || !r.ok) {
            console.error('🔴 加載站點資料失敗:', r?.error);
            return;
        }

        const startSel = document.getElementById('thsr-start');
        const destSel = document.getElementById('thsr-dest');
        const timeSel = document.getElementById('thsr-time');
        const classSel = document.getElementById('thsr-class');
        const preferSel = document.getElementById('thsr-seat-prefer') || document.getElementById('thsr-seat');

        // 1️⃣ 填入起訖車站
        if (startSel && destSel && r.stations) {
            const stationOptions = r.stations.map(s => `<option value="${s.id}">${s.name}</option>`).join('');
            startSel.innerHTML = stationOptions;
            destSel.innerHTML = stationOptions;
            if (destSel.options.length > 1) {
                destSel.selectedIndex = 1; // 預設終點站為第二個選項
            }
        }

        // 2️⃣ 填入出發時間 (對齊高鐵原生之 t.value，如 "1030a")
        if (timeSel && r.time_table) {
            timeSel.innerHTML = r.time_table.map(t => `<option value="${t.value}">${t.time}</option>`).join('');
        }

        // 3️⃣ 填入車廂別 (標準/商務)
        if (classSel && r.seat_classes) {
            classSel.innerHTML = r.seat_classes.map(c => `<option value="${c.value}">${c.name}</option>`).join('');
        }
        
        // 4️⃣ 填入座位偏好 (靠窗/靠走道)
        if (preferSel && r.seat_prefers) {
            preferSel.innerHTML = r.seat_prefers.map(p => `<option value="${p.value}">${p.name}</option>`).join('');
        }
        
        console.log('✅ 高鐵初始化下拉選單與正確 Value 綁定完成');
    } catch (e) {
        console.error('❌ 讀取高鐵站點資料失敗', e);
    }
}
// ── Step 1 → 2：送出表單參數並初始化訂票 Session ───────────────────────
async function thsrStart() {
    const dateVal = document.getElementById('thsr-date').value;
    if (!dateVal) {
        thsrSetMsg(1, '請選擇出發日期');
        return;
    }
    
    const adultNum = document.getElementById('thsr-adult')?.value || document.getElementById('thsr-tickets')?.value || '1';
    const childNum = document.getElementById('thsr-child')?.value || '0';
    const disabledNum = document.getElementById('thsr-disabled')?.value || '0';
    const elderNum = document.getElementById('thsr-elder')?.value || '0';
    const collegeNum = document.getElementById('thsr-college')?.value || '0';
    
    const totalTickets = [adultNum, childNum, disabledNum, elderNum, collegeNum]
        .reduce((sum, v) => sum + (parseInt(v, 10) || 0), 0);
        
    if (totalTickets < 1) {
        thsrSetMsg(1, '請至少選擇 1 張票');
        return;
    }

    const preferSel = document.getElementById('thsr-seat-prefer') || document.getElementById('thsr-seat');
    const timeEl = document.getElementById('thsr-time');

    const payload = {
        start_station: document.getElementById('thsr-start').value,
        dest_station: document.getElementById('thsr-dest').value,
        date: dateVal.replaceAll('-', '/'),
        time: timeEl ? timeEl.value : "",
        adult_num: adultNum,
        child_num: childNum,
        disabled_num: disabledNum,
        elder_num: elderNum,
        college_num: collegeNum,
        class_type: document.getElementById('thsr-class').value,
        seat_prefer: preferSel ? preferSel.value : "0", // 🛠️ 修正：保底值改用高鐵真實合法值，radio17 已是過期代碼
    };

    if (payload.start_station === payload.dest_station) {
        alert('出發站與到達站不可相同');
        return;
    }

    thsrSetMsg(1, '正在經由多項式回歸清洗並辨識驗證碼中...', false);
    
    try {
        const r = await api('POST', '/api/thsr/start', payload);
        
        if (!r.ok) {
            thsrSetMsg(1, r.error || '發生錯誤');
            return;
        }
        
        thsrSessionId = r.session_id;

        // 統一獲取所有 DOM 元素
        const imgMap = {
            'thsr-captcha-img': r.captcha_image,
            'thsr-captcha-cleaned-img': r.cleaned_image,
            'thsr-captcha-ocr-img': r.ocr_image
        };

        // 循環更新所有圖片，如果後端沒有回傳對應欄位，則不更新
        for (const [id, base64Data] of Object.entries(imgMap)) {
            const el = document.getElementById(id);
            if (el && base64Data) {
                el.src = 'data:image/png;base64,' + base64Data;
            } else if (el) {
                console.warn(`圖片元素 ${id} 未能更新，資料可能為空`);
            }
        }
        
        // 自動填入辨識結果
        const inputEl = document.getElementById('thsr-captcha-input') || document.getElementById('thsr-captcha-val');
        if (inputEl) inputEl.value = r.captcha_guess || '';
        
        // 顯示提示文字
        if (r.captcha_guess) {
            thsrSetMsg(2, `🤖 AI 已自動移除干擾線並辨識填入：[ ${r.captcha_guess} ]`, false);
        } else {
            thsrSetMsg(2, '請輸入圖片中的文字');
        }
        
        thsrSetMsg(1, '');
        thsrShowStep(2);
    } catch (e) {
        thsrSetMsg(1, '連線失敗，請檢查後端是否正常運行');
        console.error(e);
    }
}

/**
 * 手動換一張驗證碼（點擊看敲清楚按鈕）
 */
async function thsrRefreshCaptcha() {
    if (!thsrSessionId) return;
    thsrSetMsg(2, '更換中...', false);
    try {
        const r = await api('POST', '/api/thsr/refresh-captcha', { session_id: thsrSessionId });
        if (r.ok) {
            const imgEl = document.getElementById('thsr-captcha-img') || document.getElementById('thsr-captcha-image');
            const inputEl = document.getElementById('thsr-captcha-input') || document.getElementById('thsr-captcha-val');
            
            if (imgEl) imgEl.src = 'data:image/png;base64,' + r.captcha_image;
            if (inputEl) inputEl.value = r.captcha_guess || ''; // 自動填入下一張
            
            if (r.captcha_guess) {
                thsrSetMsg(2, `🤖 AI 已自動辨識新驗證碼：[ ${r.captcha_guess} ]`, false);
            } else {
                thsrSetMsg(2, '');
            }
        } else {
            thsrSetMsg(2, r.error || '換一張驗證碼失敗');
        }
    } catch (e) {
        console.error(e);
    }
}

//async function thsrStart() {
//    const dateVal = document.getElementById('thsr-date').value;
//    if (!dateVal) {
//        thsrSetMsg(1, '請選擇出發日期');
//        return;
//    }
//    
//    // 兼容不同 UI 設計的票數計算
//    const adultNum = document.getElementById('thsr-adult')?.value || document.getElementById('thsr-tickets')?.value || '1';
//    const childNum = document.getElementById('thsr-child')?.value || '0';
//    const disabledNum = document.getElementById('thsr-disabled')?.value || '0';
//    const elderNum = document.getElementById('thsr-elder')?.value || '0';
//    const collegeNum = document.getElementById('thsr-college')?.value || '0';
//    
//    const totalTickets = [adultNum, childNum, disabledNum, elderNum, collegeNum]
//        .reduce((sum, v) => sum + (parseInt(v, 10) || 0), 0);
//        
//    if (totalTickets < 1) {
//        thsrSetMsg(1, '請至少選擇 1 張票');
//        return;
//    }
//
//    const preferSel = document.getElementById('thsr-seat-prefer') || document.getElementById('thsr-seat');
//    const timeEl = document.getElementById('thsr-time');
//    const selectedTimeValue = timeEl ? timeEl.value : "";
//
//    // 封裝 Payload (自動將日期格式 YYYY-MM-DD 轉為高鐵所需的 YYYY/MM/DD)
//    const payload = {
//        start_station: document.getElementById('thsr-start').value,
//        dest_station: document.getElementById('thsr-dest').value,
//        date: dateVal.replaceAll('-', '/'),
//        time: selectedTimeValue,
//        adult_num: adultNum,
//        child_num: childNum,
//        disabled_num: disabledNum,
//        elder_num: elderNum,
//        college_num: collegeNum,
//        class_type: document.getElementById('thsr-class').value,
//        seat_prefer: preferSel ? preferSel.value : "radio17",
//    };
//
//    console.log("🚀 [Debug] 準備發送至後端的完整 Payload:", payload);
//
//    if (payload.start_station === payload.dest_station) {
//        alert('出發站與到達站不可相同');
//        return;
//    }
//
//    thsrSetMsg(1, '取得驗證碼中...', false);
//    const timeoutCtrl = new AbortController();
//    const timeoutId = setTimeout(() => timeoutCtrl.abort(), 40000); // 40秒超時防止掛起
//    
//    try {
//        const r = await api('POST', '/api/thsr/start', payload, timeoutCtrl.signal);
//        clearTimeout(timeoutId);
//        
//        if (!r.ok) {
//            thsrSetMsg(1, r.error || '發生錯誤');
//            return;
//        }
//        
//        thsrSessionId = r.session_id;
//        
//        // 渲染驗證碼圖片
//        const imgEl = document.getElementById('thsr-captcha-img') || document.getElementById('thsr-captcha-image');
//        if (imgEl) imgEl.src = 'data:image/png;base64,' + r.captcha_image;
//        
//        // 清空驗證碼欄位
//        //const inputEl = document.getElementById('thsr-captcha-input') || document.getElementById('thsr-captcha-val');
//        //if (inputEl) inputEl.value = '';
//		
//		// ── 2️⃣ 🌟 自動填入核心：直接將後端 OCR 辨識出的 4 碼代入輸入框 ──────────────
//        const inputEl = document.getElementById('thsr-captcha-input') || document.getElementById('thsr-captcha-val');
//        if (inputEl) {
//            // 後端辨識成功則自動填入；若失敗或解析不順則帶入空字串讓使用者手動輸入
//            inputEl.value = r.captcha_guess || ''; 
//        }
//        
//        // ── 3️⃣ 動態狀態訊息提示 ───────────────────────────────────────────────
//        if (r.captcha_guess) {
//            thsrSetMsg(2, `🤖 多項式回歸除噪完成！AI 預測驗證碼：[ ${r.captcha_guess} ] (不正確請手動微調)`, false);
//        } else {
//            thsrSetMsg(2, '圖片已清洗完畢，請輸入圖中的英數字。');
//        }
//        
//        //thsrSetMsg(1, '');
//        //thsrSetMsg(2, '');
//        thsrShowStep(2);
//    } catch (e) {
//        clearTimeout(timeoutId);
//        if (e.name === 'AbortError') {
//            thsrSetMsg(1, '連線逾時，高鐵官方伺服器無回應，請稍後再試');
//        } else {
//            thsrSetMsg(1, '連線失敗，請稍後再試');
//        }
//        console.error(e);
//    }
//}
//
///**
// * 手動重新整理驗證碼
// */
//async function thsrRefreshCaptcha() {
//    if (!thsrSessionId) return;
//    try {
//        const r = await api('POST', '/api/thsr/refresh-captcha', { session_id: thsrSessionId });
//        if (r.ok) {
//            const imgEl = document.getElementById('thsr-captcha-img') || document.getElementById('thsr-captcha-image');
//            const inputEl = document.getElementById('thsr-captcha-input') || document.getElementById('thsr-captcha-val');
//            if (imgEl) imgEl.src = 'data:image/png;base64,' + r.captcha_image;
//            if (inputEl) inputEl.value = '';
//            thsrSetMsg(2, '');
//        } else {
//            thsrSetMsg(2, r.error || '換一張驗證碼失敗');
//        }
//    } catch (e) {
//        console.error(e);
//    }
//}

// ── Step 2 → 3：提交驗證碼並查詢可用車次 ───────────────────────────────

async function thsrSubmitCaptcha() {
    const inputEl = document.getElementById('thsr-captcha-input') || document.getElementById('thsr-captcha-val');
    const code = inputEl ? inputEl.value.trim() : '';
    if (!code) {
        thsrSetMsg(2, '請輸入驗證碼');
        return;
    }
    
    thsrSetMsg(2, '送出驗證碼查詢中...', false);
    try {
        // 修正：移除多餘的 /api 路徑，正確對齊後端路由
        const r = await api('POST', '/api/thsr/submit-captcha', { session_id: thsrSessionId, security_code: code });
        
        if (!r.ok) {
            const errorMsg = (Array.isArray(r.errors) ? r.errors.join('；') : null) || r.error || '驗證碼錯誤，請重新輸入';
            thsrSetMsg(2, errorMsg);
            
            // 若高鐵後端在錯誤發生時有隨附刷新驗證碼，同步更新前端
            if (r.captcha_image) {
                const imgEl = document.getElementById('thsr-captcha-img') || document.getElementById('thsr-captcha-image');
                if (imgEl) imgEl.src = 'data:image/png;base64,' + r.captcha_image;
                if (inputEl) inputEl.value = '';
            }
            return;
        }
        
        thsrRenderTrains(r.trains || []);
        thsrSetMsg(2, '');
        thsrSetMsg(3, '');
        thsrShowStep(3);
    } catch (e) {
        thsrSetMsg(2, '連線失敗，請稍後再試');
        console.error(e);
    }
}
// ── Step 3：動態渲染車次列表 ──────────────────────────────────────────

function thsrRenderTrains(trains) {
    const tbody = document.getElementById('thsr-trains-body');
    const container = document.getElementById('thsr-train-list');
    
    // 方案 A: 渲染至現有的 Table Body 節點
    if (tbody) {
        if (trains.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-muted py-3">查無可選車次</td></tr>';
            return;
        }
        tbody.innerHTML = trains.map(t => `
          <tr>
            <td><input type="radio" name="thsr-train-radio" value="${t.index}" ${t.index === 1 ? 'checked' : ''}></td>
            <td><b>${t.id}</b></td>
            <td>${t.depart}</td>
            <td>${t.arrive}</td>
            <td>${t.travel_time}</td>
            <td>${Object.values(t.discount || {}).join('、') || '--'}</td>
          </tr>`).join('');
          
    // 方案 B: 渲染至通用容器節點（自動動態組裝整張 Table）
    } else if (container) {
        if (trains.length === 0) {
            container.innerHTML = '<p style="color: #ff4d4f; font-weight: bold;">❌ 沒有符合當前查詢條件的座位車次</p>';
            return;
        }
        let html = '<table style="width:100%; border-collapse:collapse; margin-top:10px;">';
        html += '<thead><tr style="background:#fafafa; text-align:left; border-bottom:2px solid #e8e8e8;"><th style="padding:10px 0;">選擇</th><th>車次</th><th>出發</th><th>抵達</th><th>時間</th></tr></thead><tbody>';
        trains.forEach((t, idx) => {
            html += `
            <tr style="border-bottom: 1px solid #f0f0f0;">
                <td style="padding:10px 0;"><input type="radio" name="thsr-train-radio" value="${t.index}" ${idx === 0 ? 'checked' : ''}></td>
                <td><b>${t.id}</b></td>
                <td>${t.depart}</td>
                <td>${t.arrive}</td>
                <td>${t.travel_time}</td>
            </tr>`;
        });
        html += '</tbody></table>';
        container.innerHTML = html;
    }
}


// ── Step 3 → 4：選擇指定車次並執行後端鎖位 ──────────────────────────────

async function thsrSelectTrain() {
    const checked = document.querySelector('input[name="thsr-train-radio"]:checked');
    if (!checked) {
        thsrSetMsg(3, '請選擇一個車次');
        return;
    }
    
    thsrSetMsg(3, '車次鎖位中...', false);
    try {
        const r = await api('POST', '/api/thsr/select-train', { session_id: thsrSessionId, index: checked.value });
        if (!r.ok) {
            thsrSetMsg(3, (r.errors && r.errors.join('；')) || r.error || '選擇車次失敗');
            return;
        }
        thsrSetMsg(3, '');
        thsrSetMsg(4, '');
        thsrShowStep(4);
    } catch (e) {
        thsrSetMsg(3, '連線失敗，請稍後再試');
        console.error(e);
    }
}


// ── Step 4 → 5：填寫聯絡資料，送出最終劃位扣票 ────────────────────────────

async function thsrConfirm() {
    const personalIdInput = document.getElementById('thsr-personal-id');
    const phoneInput = document.getElementById('thsr-phone');
    
    // 自動將首碼英文轉為大寫並去除前後空白
    const personalId = personalIdInput ? personalIdInput.value.trim().toUpperCase() : '';
    const phone = phoneInput ? phoneInput.value.trim() : '';

    // 1️⃣ 中華民國身分證格式強效 Regex 驗證 (首碼大寫英文字母 + 9位數字)
    const idRegex = /^[A-Z]\d{9}$/;
    if (!idRegex.test(personalId)) {
        thsrSetMsg(4, '請輸入有效的中華民國身分證字號 (格式如: A123456789)');
        if (personalIdInput) personalIdInput.focus();
        return;
    }

    // 2️⃣ 台灣手機號碼基本格式驗證 (09開頭且總共10碼數字)
    const phoneRegex = /^09\d{8}$/;
    if (!phoneRegex.test(phone)) {
        thsrSetMsg(4, '請輸入有效的台灣手機號碼 (共 10 碼數字，例如: 0912345678)');
        if (phoneInput) phoneInput.focus();
        return;
    }

    thsrSetMsg(4, '提交訂單與最終劃位中，請勿重新整理...', false);
    try {
        const r = await api('POST', '/api/thsr/confirm', { 
            session_id: thsrSessionId, 
            personal_id: personalId, 
            phone 
        });
        
        if (!r.ok) {
            thsrSetMsg(4, (r.errors && r.errors.join('；')) || r.error || '送出訂票失敗');
            return;
        }
        
        // 成功取得訂位代號，執行渲染與跳轉
        thsrRenderResult(r.ticket, r.message);
        thsrShowStep(5);
    } catch (e) {
        thsrSetMsg(4, '連線逾時或後端處理異常，系統可能已扣票成功，請至高鐵官網確認訂位狀態');
        console.error(e);
    }
}


// ── Step 5：顯示最終訂票成功結果頁 ─────────────────────────────────────

/**
 * 將高鐵回傳的訂單明細渲染至結果元件中
 * @param {Object} ticket 包含訂位代號、座位、價格等結構物件
 * @param {string} message 來自後端的提示訊息（例如付款提醒）
 */
function thsrRenderResult(ticket, message) {
    const el = document.getElementById('thsr-result-detail');
    if (!el) return;
    el.innerHTML = `
      <div style="background: #fffbe6; border: 1px solid #ffe58f; padding: 14px; border-radius: 6px; margin-bottom: 14px;">
        <span style="color: #595959; font-size: 14px;">您的訂位代號：</span><br>
        <b style="font-size:26px; color:#f5222d; letter-spacing: 1px; display: inline-block; margin: 4px 0;">${ticket.booking_id}</b><br>
        <span style="color: #262626;">繳費期限：</span><span style="color:#cf1322; font-weight:bold;">${ticket.payment_deadline}</span>
      </div>
      <div style="line-height: 1.8; color: #262626;">
        <b>車次資訊：</b>${ticket.train_id} 次列車（${ticket.start_station} → ${ticket.dest_station}）<br>
        <b>乘車日期：</b>${ticket.date}<br>
        <b>出發抵達：</b><span style="color: #d46b08; font-weight: bold;">${ticket.depart_time}</span> ➔ <span style="color: #096dd9; font-weight: bold;">${ticket.arrival_time}</span><br>
        <b>車廂座位：</b>${ticket.seat_class} ｜ <span style="color:#096dd9; font-weight:bold;">${ticket.seat || '系統已自動劃位'}</span><br>
        <b>票種與票價：</b>${ticket.ticket_num_info || ''} ｜ 共計 <b style="color: #389e0d; font-size: 16px;">${ticket.price || '--'}</b> 元
      </div>
      <hr style="border: 0; border-top: 1px dashed #d9d9d9; margin: 12px 0;">
      <span style="color:#fa8c16; font-weight:bold; display:block; line-height: 1.4;">⚠️ ${message || ''}</span>
    `;
}

/**
 * 重設狀態並返回第一步（用於取消、重試或再訂一張）
 */
function thsrRestart() {
    thsrSessionId = null;
    const pid = document.getElementById('thsr-personal-id');
    const ph = document.getElementById('thsr-phone');
    if (pid) pid.value = '';
    if (ph) ph.value = '';
    
    // 清除全域所有步驟的殘留訊息
    thsrSetMsg(1, ''); thsrSetMsg(2, ''); thsrSetMsg(3, ''); thsrSetMsg(4, '');
    thsrShowStep(1);
}

/**
 * 在流程進行到一半時（步驟2~4）點「重新訂票」，先跟使用者確認會放棄目前進度，
 * 避免不小心點到就整個重來。
 */
function thsrRestartConfirm() {
    if (!confirm('確定要放棄目前的訂票進度，重新開始嗎？')) return;
    thsrRestart();
}
