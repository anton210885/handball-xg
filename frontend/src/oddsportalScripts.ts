// Code, der auf der oddsportal-Seite im Browser des Nutzers läuft – als Lesezeichen (Klick) oder als
// Tampermonkey-Skript (von selbst beim Öffnen einer Spielseite). Beide lesen nur die eine offene Seite:
// 1X2, Over/Under und Asian Handicap („Full Time“) werden durchgeklickt und jede Tabelle als Text mitgenommen.
// Kein „//“-Kommentar im gemeinsamen Teil: das Lesezeichen ist eine einzige Zeile.

const POPUP = "window.open(O+'/oddsportal','handballxg','width=640,height=760')";

// Gemeinsam: Kästchen oben rechts, Reiter durchklicken (collect) und Übergabe an das Tool-Fenster (handshake)
const CORE = `let box=null;
const hide=()=>{if(box){box.remove();box=null}};
const show=(t,c)=>{if(!box){box=document.createElement('div');box.style.cssText='position:fixed;top:12px;right:12px;z-index:2147483647;color:#fff;padding:10px 14px;border-radius:8px;font:13px/1.4 sans-serif;max-width:380px;box-shadow:0 4px 20px rgba(0,0,0,.35);white-space:pre-line;cursor:pointer';document.body.appendChild(box)}box.style.background=c||'#1f2937';box.textContent=t;box.onclick=hide;return box};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const txt=()=>{const m=document.querySelector('main');return m&&m.innerText.length>200?m.innerText:document.body.innerText};
const el=n=>[...document.querySelectorAll('span,a,button,div,li')].find(x=>x.children.length===0&&x.textContent.trim()===n);
const mk=()=>{const h=location.hash.toLowerCase();return h.includes('o/u;')||h.includes('over-under;')?'O/U':h.includes('ah;')?'AH':(h.includes('1x2;')||!h.includes(';'))?'1X2':'?'};
const per=()=>{const m=location.hash.match(/;(\\d+)/);return m?m[1]:'2'};
const loaded={'1X2':t=>t.includes('Payout')&&!/(Over\\/Under|Asian Handicap) [+-]?\\d/.test(t),'O/U':t=>/Over\\/Under [+-]?\\d/.test(t),'AH':t=>/Asian Handicap [+-]?\\d/.test(t)};
const collect=async()=>{const pages=[];
for(const [code,label] of [['1X2','1X2'],['O/U','Over/Under'],['AH','Asian Handicap']]){
show('Handball xG: lese '+label+' …');
if(mk()!==code){const t=el(label);if(t)t.click()}
let ok=false;
for(let i=0;i<48;i++){await sleep(250);
if(mk()!==code)continue;
if(per()!=='2'){const f=el('Full Time');if(f)f.click();continue}
if(loaded[code](txt())){ok=true;break}}
if(ok){await sleep(300);pages.push({url:location.href,text:txt()})}else pages.push({url:location.href,text:'',missing:label})}
return {type:'handball-xg-odds',pages,title:document.title,tz_offset:new Date().getTimezoneOffset()}};
const handshake=(w,data,res)=>{let sent=false;
const off=()=>removeEventListener('message',on);
const on=e=>{if(e.origin!==O)return;
if(e.data==='handball-xg-ready'&&!sent){sent=true;w.postMessage(data,O)}
else if(e.data&&e.data.type==='handball-xg-result'){res(e.data.ok,e.data.text);if(e.data.ok)off()}};
addEventListener('message',on);setTimeout(off,300000)};
`;

export function bookmarkletCode(origin: string) {
  // Das Fenster sofort öffnen: nach dem Durchklicken wäre es kein Klick mehr und würde blockiert
  const js = `(async()=>{const O=${JSON.stringify(origin)};
if(window.__hxRun)return;window.__hxRun=1;
const w=${POPUP};
if(!w){alert('Handball xG: Popup wurde blockiert. Bitte Popups für diese Seite erlauben.');window.__hxRun=0;return}
${CORE}
const data=await collect();
show('Handball xG: speichere …');setTimeout(()=>window.__hxRun=0,300000);
handshake(w,data,(ok,t)=>{show(t,ok?'#166534':'#92400e');if(ok){window.__hxRun=0;setTimeout(hide,7000)}})})()`;
  return "javascript:" + encodeURIComponent(js.replace(/\n/g, ""));
}

// Tampermonkey-Skript: läuft auf jeder Handball-Spielseite von oddsportal einmal je Spiel und schickt die Seite
// direkt ans Tool (GM_xmlhttpRequest, kein Fenster). Nur bei unsicherer Zuordnung öffnet ein Klick das Tool-Fenster.
export function userscriptCode(origin: string, version: string) {
  const hosts = [...new Set([new URL(origin).hostname, "localhost", "127.0.0.1"])];
  return `// ==UserScript==
// @name         Handball xG – Quoten von oddsportal
// @namespace    handball-xg
// @version      ${version}
// @description  Liest auf einer geöffneten Handball-Spielseite 1X2, Over/Under und Asian Handicap und speichert sie in Handball xG.
// @match        https://*.oddsportal.com/*
// @grant        GM_xmlhttpRequest
${hosts.map((h) => `// @connect      ${h}`).join("\n")}
// @run-at       document-idle
// @noframes
// @updateURL    ${origin}/handball-xg.user.js
// @downloadURL  ${origin}/handball-xg.user.js
// ==/UserScript==
(function () {
'use strict';
const O = ${JSON.stringify(origin)};
${CORE}
// oddsportal-Spiel-ID: h2h-Seite „#GtS5vtTh:1X2;2“ oder Spielseite „…/kaustik-uor-GtS5vtTh/“
const eid = () => {
  if (!location.pathname.startsWith('/handball/')) return null;
  const m = location.hash.match(/^#([A-Za-z0-9]{8})(?::|$)/) || location.pathname.match(/-([A-Za-z0-9]{8})\\/?$/);
  return m ? m[1] : null;
};
const post = (path, data) => new Promise((res, rej) => GM_xmlhttpRequest({
  method: 'POST', url: O + path, headers: { 'Content-Type': 'application/json' },
  data: JSON.stringify(data), timeout: 30000,
  onload: (r) => r.status === 200 ? res(JSON.parse(r.responseText)) : rej(new Error(r.status + ' ' + String(r.responseText || '').slice(0, 200))),
  onerror: () => rej(new Error('Tool nicht erreichbar – läuft Handball xG (start.vbs)?')),
  ontimeout: () => rej(new Error('keine Antwort vom Tool')),
}));
const n = (v) => v == null ? '–' : String(v);
const rest = (m) => {
  if (!m) return '';
  const parts = [m.line && m.line + ' Torlinien', m.hdp && m.hdp + ' Handicaps', m.x12 && m.x12 + '× 1X2'].filter(Boolean);
  return parts.length ? 'Im Wettbewerb fehlen noch: ' + parts.join(', ') : 'Wettbewerb vollständig ✓';
};
const finish = (b, ms) => setTimeout(() => { if (box === b) hide(); }, ms);

// Reihenfolge der noch fehlenden Spiele aus der zuletzt markierten Liste (nur in diesem Tab)
const loadNext = () => { try { return JSON.parse(sessionStorage.getItem('hx-next') || '[]'); } catch (e) { return []; } };
const saveNext = (list) => { try { sessionStorage.setItem('hx-next', JSON.stringify(list)); } catch (e) { /* egal */ } };
// Nach einem Spiel: aus der Liste streichen und per Klick auf das Kästchen zum nächsten
const offerNext = (b, id, ms) => {
  const next = loadNext().filter((x) => x.id !== id);
  saveNext(next);
  if (next.length) {
    b.textContent += '\\n▶ Klick: nächstes fehlendes Spiel (' + next.length + ' übrig)';
    b.onclick = () => { location.href = next[0].href; };
  }
  finish(b, next.length ? 15000 : ms);
};

// Ergebnisliste: Zeilen mit Spieladresse finden und markieren, was im Tool noch fehlt
// Spielseite „…/heim-gast-<id>/“ oder – so verlinken die Ergebnislisten – h2h-Seite „/handball/h2h/…/#<id>“
const ROW = /^\\/handball\\/(?!h2h\\/).*-([A-Za-z0-9]{8})\\/?$/;
const linkId = (a) => {
  if (a.pathname.startsWith('/handball/h2h/')) { const h = a.hash.match(/^#([A-Za-z0-9]{8})(?::|$)/); return h ? h[1] : null; }
  const m = a.pathname.match(ROW); return m ? m[1] : null;
};
const listIds = () => [...new Set([...document.querySelectorAll('a[href]')].map(linkId).filter(Boolean))];
const rowsOnPage = () => {
  const first = new Map();
  for (const a of document.querySelectorAll('a[href]')) { const id = linkId(a); if (id && !first.has(id)) first.set(id, a); }
  return [...first].map(([id, a]) => {
    // Zeile = höchster Vorfahr, der nur Links auf dieses eine Spiel enthält
    let el = a;
    while (el.parentElement && el.parentElement !== document.body &&
      ![...el.parentElement.querySelectorAll('a[href]')].some((x) => { const o = linkId(x); return o && o !== id; })) el = el.parentElement;
    return { id, href: a.href, el };
  });
};
let lastSig = null, placed = 0, marked = [];
const clearMarks = () => {
  document.querySelectorAll('.hx-badge').forEach((b) => b.remove());
  marked.forEach((el) => { el.style.background = ''; });
  marked = []; placed = 0;
};
const badge = (el, text, bg, title) => {
  const s = document.createElement('span');
  s.className = 'hx-badge'; s.textContent = text; s.title = title;
  s.style.cssText = 'display:inline-block;margin:0 6px;padding:1px 6px;border-radius:4px;font:600 11px/1.5 sans-serif;color:#fff;white-space:nowrap;background:' + bg;
  el.prepend(s); placed++;
};
const markList = async (sig) => {
  lastSig = sig;
  clearMarks();
  const rows = rowsOnPage();
  const r = await post('/api/oddsportal/list', { rows: rows.map((x) => ({ id: x.id, href: x.href, text: x.el.innerText.slice(0, 400) })) });
  if (lastSig !== sig) return;
  const st = new Map(r.rows.map((x) => [x.id, x]));
  // Kein beendetes Spiel bekannt: fremde Liga oder nur kommende Spiele – dann nichts markieren
  if (!r.rows.some((x) => x.status === 'missing' || x.status === 'ok')) return saveNext([]);
  const miss = [], unknown = [];
  for (const row of rows) {
    const s = st.get(row.id);
    if (!s) continue;
    if (s.status === 'missing') {
      miss.push({ id: row.id, href: row.href });
      badge(row.el, 'fehlt: ' + s.missing.join(', '), '#dc2626', 'Handball xG: Spiel öffnen, die Quoten werden übernommen');
      row.el.style.background = 'rgba(220,38,38,.08)'; marked.push(row.el);
    } else if (s.status === 'ok') {
      badge(row.el, '✓', '#16a34a', 'Handball xG: Quoten vollständig');
    } else if (s.status === 'unknown') {
      unknown.push({ id: row.id, href: row.href });
      badge(row.el, '?', '#6b7280', 'Handball xG: nicht zugeordnet – Spiel öffnen, danach kennt das Tool es');
    }
  }
  const next = [...miss, ...unknown];
  saveNext(next);
  const b = show('Handball xG: ' + (miss.length ? miss.length + ' Spiele auf dieser Seite brauchen noch Quoten' : 'alle zugeordneten Spiele vollständig ✓') +
    (unknown.length ? ', ' + unknown.length + ' nicht zugeordnet (?)' : '') + (next.length ? '\\n▶ Klick: erstes öffnen' : ''), miss.length ? '#92400e' : '#166534');
  if (next.length) b.onclick = () => { location.href = next[0].href; };
  finish(b, 15000);
};

let last = null, busy = false;
const run = async (id) => {
  busy = true;
  try {
    // Erst warten, bis die Quotentabelle da ist (Seite lädt nach)
    for (let i = 0; i < 80 && !/Payout|Over\\/Under [+-]?\\d|Asian Handicap [+-]?\\d/.test(txt()); i++) await sleep(250);
    const data = await collect();
    if (eid() !== id) return hide();
    show('Handball xG: speichere …');
    const r = await post('/api/oddsportal/import', data);
    lastSig = null;  // zurück auf der Liste neu markieren
    if (r.saved && r.game) {
      const l = r.game.line || {};
      offerNext(show(['✓ ' + r.game.home.name + ' – ' + r.game.away.name,
        'Linie ' + n(l.over_line) + ' (' + n(l.odds_over) + '/' + n(l.odds_under) + ') · HC ' + n(l.hdp_line) +
        ' · 1X2 ' + n(l.odds_home) + '/' + n(l.odds_draw) + '/' + n(l.odds_away),
        ...r.warnings, rest(r.remaining)].filter(Boolean).join('\\n'), '#166534'), id, 9000);
    } else if (!r.candidates || !r.candidates.length) {
      offerNext(show('Handball xG: kein passendes Spiel im Tool (' + n(r.home) + ' – ' + n(r.away) + ').', '#374151'), id, 6000);
    } else {
      const b = show('Handball xG: Spiel nicht sicher erkannt – hier klicken und im Tool auswählen.', '#92400e');
      b.onclick = () => {
        const w = ${POPUP};
        if (!w) return show('Handball xG: Popup wurde blockiert. Bitte Popups für diese Seite erlauben.', '#991b1b');
        show('Handball xG: bitte im Tool-Fenster auswählen …');
        handshake(w, data, (ok, t) => { const b2 = show(t, ok ? '#166534' : '#92400e'); if (ok) finish(b2, 7000); });
      };
    }
  } catch (e) {
    show('Handball xG: ' + e.message, '#991b1b');
  } finally {
    busy = false;
  }
};
// oddsportal wechselt Seiten ohne neues Laden – daher regelmäßig nachsehen: Spielseite lesen oder Liste markieren
setInterval(() => {
  if (busy) return;
  const id = eid();
  if (id) { if (id !== last) { last = id; run(id); } return; }
  last = null;
  if (!location.pathname.startsWith('/handball/')) return;
  const ids = listIds();
  const sig = ids.join(',');
  // neu markieren bei anderer Liste oder wenn oddsportal die Zeilen neu gezeichnet hat (Markierungen weg)
  if (ids.length >= 2 && (sig !== lastSig || (placed && !document.querySelector('.hx-badge')))) {
    busy = true;
    markList(sig).catch((e) => show('Handball xG: ' + e.message, '#991b1b')).finally(() => { busy = false; });
  }
}, 1000);
})();
`;
}
