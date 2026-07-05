// ── News (RSS) ───────────────────────────────────────────────
//async function loadNews(){
//  document.getElementById('news-list').innerHTML=`<div class="loader"><div class="spinner"></div>讀取 RSS 財經新聞...</div>`;
//  try{
//    const r=await api('GET','/api/news');
//    renderNews(r.news||[]);
//  }catch(e){ document.getElementById('news-list').innerHTML=`<div class="empty" style="color:var(--red)">RSS 讀取失敗</div>`; }
//}

async function loadNews(){
  try {
    const r = await api('GET', '/api/news');
    const news = r.news || [];
    const list = document.getElementById('news-list');
    if (!list) return;

    list.innerHTML = '';
    news.forEach(n=>{
      const item = document.createElement('li');
      item.textContent = `${esc(n.title)} (${esc(n.source)})`;
      list.appendChild(item);
    });
  } catch(e){
    console.error('載入新聞失敗:', e);
  }
}


function fmtNewsDate(n){
  if(n.pub_iso){
    const d=new Date(n.pub_iso);
    const mm=String(d.getMonth()+1).padStart(2,'0');
    const dd=String(d.getDate()).padStart(2,'0');
    const hh=String(d.getHours()).padStart(2,'0');
    const mi=String(d.getMinutes()).padStart(2,'0');
    return `${mm}-${dd} ${hh}:${mi}`;
  }
  return n.time||'--:--';
}

function renderNews(news){
  const tagMap={tw:'tag-tw',intl:'tag-intl',macro:'tag-macro',geo:'tag-macro',asia:'tag-intl'};
  const tagTxt={tw:'台股',intl:'國際',macro:'總經',geo:'地緣',asia:'亞洲'};
  document.getElementById('news-list').innerHTML=news.map(n=>`
    <div class="nitem">
      <div class="ntime">${fmtNewsDate(n)}</div>
      <div>
        <span class="ntag ${tagMap[n.tag]||'tag-tw'}">${tagTxt[n.tag]||n.tag}</span>
        <div class="ntitle">${n.link?`<a href="${esc(n.link)}" target="_blank" rel="noopener">${esc(n.title)}</a>`:esc(n.title)}</div>
        <div class="nsrc">${esc(n.source||'')}</div>
      </div>
    </div>`).join('');
}
