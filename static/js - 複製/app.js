// ── Helpers ─────────────────────────────────────────────────
function getApiKey(){ return 'test-token'; }

async function api(method, path, body, signal){
  const opts = { 
    method, 
    headers:{
      'Content-Type':'application/json',
      'Authorization': `Bearer ${getApiKey()}`
    } 
  };
  if (body) opts.body = JSON.stringify(body);
  if (signal) opts.signal = signal;
  const r = await fetch(path, opts);
  if(r.status===401) throw new Error('Unauthorized');
  return r.json();

function getApiKey(){ 
  // 固定使用伺服器啟動時顯示的 API Key
  return 'test-token'; 
}

async function api(method, path, body, signal){
  const sentKey = getApiKey();
  const opts = { 
    method, 
    headers:{
      'Content-Type':'application/json',
      'Authorization': `Bearer ${sentKey}`   // 🔑 改成 Authorization header
    } 
  };
  if (body) opts.body = JSON.stringify(body);
  if (signal) opts.signal = signal;
  const r = await fetch(path, opts);
  if(r.status===401){
    throw new Error('Unauthorized - 請確認 API Key 是否正確');
  }
  return r.json();
}

function esc(s){ return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#x27;'); }
function toast(msg, type='ok'){
  const el = document.getElementById('toast');
  el.textContent = msg; el.className = `toast ${type} show`;
  setTimeout(()=>el.classList.remove('show'), 3000);
}
function fmtChg(pct){
  if(pct==null) return '<span class="chg">--</span>';
  const cls = pct>=0?'up':'dn';
  const sign = pct>=0?'+':'';
  return `<span class="chg ${cls}">${sign}${pct.toFixed(2)}%</span>`;
}

//function getApiKey(){ return localStorage.getItem('trading_api_key')||''; }
//
//async function api(method, path, body, signal){
//  const sentKey = getApiKey();
//  const opts = { method, headers:{'Content-Type':'application/json','X-API-Key':sentKey} };
//  if (body) opts.body = JSON.stringify(body);
//  if (signal) opts.signal = signal;
//  const r = await fetch(path, opts);
//  if(r.status===401){
//    if(getApiKey() !== sentKey && getApiKey() !== '') return api(method,path,body,signal);
//    const k = prompt('請輸入 API Key（從伺服器啟動訊息取得）：');
//    if(k){ localStorage.setItem('trading_api_key',k); return api(method,path,body,signal); }
//    throw new Error('Unauthorized');
//  }
//  return r.json();
//}
//function esc(s){ return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#x27;'); }
//function toast(msg, type='ok'){
//  const el = document.getElementById('toast');
//  el.textContent = msg; el.className = `toast ${type} show`;
//  setTimeout(()=>el.classList.remove('show'), 3000);
//}
//function fmtChg(pct){
//  if(pct==null) return '<span class="chg">--</span>';
//  const cls = pct>=0?'up':'dn';
//  const sign = pct>=0?'+':'';
//  return `<span class="chg ${cls}">${sign}${pct.toFixed(2)}%</span>`;
//}

// ── Clock ────────────────────────────────────────────────────
function tick(){
  const clockEl = document.getElementById('clock');
  if (clockEl) {
    clockEl.textContent = new Intl.DateTimeFormat('zh-TW',{
      timeZone:'Asia/Taipei',hour:'2-digit',minute:'2-digit',second:'2-digit',
      year:'numeric',month:'2-digit',day:'2-digit',hour12:false
    }).format(new Date()) + ' TST';
  }
}
setInterval(tick,1000); tick();

// ── Tabs（終極斷路解鎖・沙盒防禦整合版） ─────────────────────────
document.querySelectorAll('.tab').forEach(tab=>{
  tab.addEventListener('click',(e)=>{
    // 1. 最高權限穿透：阻止點擊事件在傳遞過程中被預測功能 (predict.js) 的全域事件捕獲鎖死
    if (e && typeof e.stopPropagation === 'function') {
      e.stopPropagation();
    }

    const targetId = 'tab-' + tab.dataset.tab;
    const targetPanel = document.getElementById(targetId);
    
    if (!targetPanel) {
      console.warn(`[導覽提示] 找不到對應的內容面板: #${targetId}`);
    }

    // 2. 還原所有頁簽按鈕的 active 高亮類名
    document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
    tab.classList.add('active');

    // 3. 🔴【核心破鎖關鍵】：全面清洗各面板上可能被強行蓋上的行內 display 樣式
    // 這樣可以瞬間瓦解 predict.js 等外掛腳本殘留的 display="none" 霸道鎖定
    document.querySelectorAll('.panel').forEach(p=>{
      p.classList.remove('active');
      p.style.setProperty('display', '', 'important');
    });

    // 4. 激活選中面板，強制拉開畫面
    if (targetPanel) {
      targetPanel.classList.add('active');
      targetPanel.style.setProperty('display', 'block', 'important');
    }
    
    // 5. 獨立非同步沙盒：各頁簽專屬生命週期 API 隔離觸發，一處崩潰決不卡死按鈕
    try {
      if(tab.dataset.tab==='holdings') {
        if (typeof loadMarket === 'function') loadMarket();
      }
      if(tab.dataset.tab==='watchlist') {
        if (typeof loadWatchlist === 'function') loadWatchlist();
      }
      if(tab.dataset.tab==='news') {
        if (typeof loadNews === 'function') loadNews();
      }
      if(tab.dataset.tab==='ai'){ 
        if (typeof loadXIntel === 'function') loadXIntel(); 
        if (typeof loadDailySummary === 'function') loadDailySummary(); 
      }
      if(tab.dataset.tab==='topic') {
        if (typeof loadCoverageKeywords === 'function') loadCoverageKeywords();
      }
      
      // 當點進台股預測分頁時，主動通知後端重刷 SQLite 歷史紀錄對帳單
      if(tab.dataset.tab==='predict') {
        console.log('進入台股預測分頁，啟動歷史紀錄同步機制...');
        if (typeof loadPredictionHistoryTable === 'function') {
          loadPredictionHistoryTable();
        }
      }
    } catch(error) {
      console.error("[安全熔斷] 頁簽內部組件載入異常，已自動沙盒隔離：", error);
    }
  });
});

function closeModal(id){ document.getElementById(id).classList.remove('open'); }

// ── Market ───────────────────────────────────────────────────
let _mktRetry = null;
async function loadMarket(){
  clearTimeout(_mktRetry);
  try{
    const r = await api('GET', '/api/market');
    const m = r.market||{};
    const setMkt=(id,chgId,d)=>{
      if(d?.price){
        document.getElementById(id).textContent=d.price.toLocaleString();
        document.getElementById(chgId).outerHTML=`<span id="${chgId}">${fmtChg(d.change_pct)}</span>`;
      }
    };
    setMkt('m-tw','m-tw-chg',m.taiex);
    setMkt('m-nd','m-nd-chg',m.nasdaq);
    setMkt('m-sp','m-sp-chg',m.sp500);
    if(m.usd_twd?.price) document.getElementById('m-fx').textContent=m.usd_twd.price.toFixed(2);
    if(m.market_above_ema20!=null){
      const el=document.getElementById('m-filter');
      if(el){ el.textContent=m.market_above_ema20?'✅ 站上 20EMA':'❌ 跌破 20EMA'; el.style.color=m.market_above_ema20?'var(--green)':'var(--red)'; }
      const sub=document.getElementById('m-filter-sub');
      if(sub){ sub.textContent=m.market_above_ema20?'✅ 站上 20EMA':'❌ 跌破 20EMA'; sub.style.color=m.market_above_ema20?'var(--green)':'var(--red)'; }
    }
    if(m.ema20_tw){
      const el=document.getElementById('m-ema'); if(el) el.textContent=m.ema20_tw.toLocaleString();
      const se=document.getElementById('summary-ema'); if(se) se.textContent='EMA20: '+m.ema20_tw.toLocaleString();
    }
    if(!r.cached) _mktRetry=setTimeout(loadMarket,10000);
  }catch(e){
    _mktRetry=setTimeout(loadMarket,15000);
  }
}

// ── 代號自動查名稱 ───────────────────────────────────────────
let _nameTimer = null;
function autoFetchName(code){
  code = (code||'').trim();
  const tag = document.getElementById('f-name-tag');
  const inp = document.getElementById('f-name');
  if(!code){ tag.textContent='輸入代號自動查詢'; tag.style.color='var(--text-tertiary)'; return; }
  if(code.length < 4){ tag.textContent='...'; tag.style.color='var(--text-tertiary)'; return; }
  clearTimeout(_nameTimer);
  _nameTimer = setTimeout(async ()=>{
    tag.textContent = '查詢中...'; tag.style.color='var(--text-secondary)';
    try{
      const d = await api('GET', `/api/stock_info/${encodeURIComponent(code)}`);
      if(d.ok && d.name){
        tag.textContent = d.name;
        tag.style.color = 'var(--green)';
        if(!inp.value) inp.value = d.name;
        if(d.group) tag.title = `${d.market} ｜ ${d.group}`;
      } else {
        tag.textContent = '找不到此代號';
        tag.style.color = 'var(--red)';
      }
    }catch(e){
      tag.textContent = '查詢失敗'; tag.style.color='var(--red)';
    }
  }, 400);
}
