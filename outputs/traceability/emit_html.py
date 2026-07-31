# -*- coding: utf-8 -*-
"""Emit the standalone traceability explorer HTML (zero external requests)."""
import json, os, base64

ROOT = "/Users/vedha/Repo/FULL_WORKFLOW"
OUT  = os.path.join(ROOT, "outputs", "traceability")
G    = json.load(open(os.path.join(OUT, "graph.json")))

# embed the KM figure as a data: URI so the page stays self-contained
for n in G["nodes"]:
    fp = (n.get("meta") or {}).get("figurePng")
    if fp:
        p = os.path.join(ROOT, fp)
        if os.path.exists(p):
            n["meta"]["figureData"] = "data:image/png;base64," + \
                base64.b64encode(open(p, "rb").read()).decode()

DATA = json.dumps(G, ensure_ascii=False).replace("</", "<\\/")

CSS = r"""
:root{
  --bg:#f7f8fa; --surface:#fff; --surface2:#f0f2f5; --ink:#11151c; --ink2:#4a5361;
  --ink3:#6b7480; --line:#d9dde4; --line2:#eceff3; --accent:#2a78d6;
  --t-obj:#2a78d6; --t-end:#1baf7a; --t-tlf:#eda100; --t-adam:#008300; --t-sdtm:#4a3aa7; --t-reg:#64748b;
  --s-ok:#0f7b4f; --s-ok-bg:#e4f4ec; --s-blk:#b3261e; --s-blk-bg:#fbe9e7;
  --s-clr:#8a5a00; --s-clr-bg:#fdf1dc; --s-gap:#5b21b6; --s-gap-bg:#efe9fd;
  --s-info:#33506b; --s-info-bg:#e9eef4;
  --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;
}
@media (prefers-color-scheme:dark){:root{
  --bg:#0e1116; --surface:#161b22; --surface2:#1d2430; --ink:#e8ecf2; --ink2:#aab4c2;
  --ink3:#7f8b9c; --line:#2b3441; --line2:#222b36; --accent:#3987e5;
  --t-obj:#3987e5; --t-end:#199e70; --t-tlf:#e0a836; --t-adam:#3ca63c; --t-sdtm:#9085e9; --t-reg:#8b98ad;
  --s-ok:#4bc38a; --s-ok-bg:#12301f; --s-blk:#ff8a80; --s-blk-bg:#3a1613;
  --s-clr:#e3b341; --s-clr-bg:#33270a; --s-gap:#c4b5fd; --s-gap-bg:#241a3d;
  --s-info:#a8c0d8; --s-info-bg:#18222e;}}
:root[data-theme="light"]{
  --bg:#f7f8fa; --surface:#fff; --surface2:#f0f2f5; --ink:#11151c; --ink2:#4a5361;
  --ink3:#6b7480; --line:#d9dde4; --line2:#eceff3; --accent:#2a78d6;
  --t-obj:#2a78d6; --t-end:#1baf7a; --t-tlf:#eda100; --t-adam:#008300; --t-sdtm:#4a3aa7; --t-reg:#64748b;
  --s-ok:#0f7b4f; --s-ok-bg:#e4f4ec; --s-blk:#b3261e; --s-blk-bg:#fbe9e7;
  --s-clr:#8a5a00; --s-clr-bg:#fdf1dc; --s-gap:#5b21b6; --s-gap-bg:#efe9fd;
  --s-info:#33506b; --s-info-bg:#e9eef4;}
:root[data-theme="dark"]{
  --bg:#0e1116; --surface:#161b22; --surface2:#1d2430; --ink:#e8ecf2; --ink2:#aab4c2;
  --ink3:#7f8b9c; --line:#2b3441; --line2:#222b36; --accent:#3987e5;
  --t-obj:#3987e5; --t-end:#199e70; --t-tlf:#e0a836; --t-adam:#3ca63c; --t-sdtm:#9085e9; --t-reg:#8b98ad;
  --s-ok:#4bc38a; --s-ok-bg:#12301f; --s-blk:#ff8a80; --s-blk-bg:#3a1613;
  --s-clr:#e3b341; --s-clr-bg:#33270a; --s-gap:#c4b5fd; --s-gap-bg:#241a3d;
  --s-info:#a8c0d8; --s-info-bg:#18222e;}

*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font-family:system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  font-size:14px;line-height:1.5;overflow-x:hidden}
header{padding:14px 18px 12px;border-bottom:1px solid var(--line);background:var(--surface)}
h1{margin:0 0 2px;font-size:17px;font-weight:650;letter-spacing:-.01em}
.sub{color:var(--ink2);font-size:12.5px}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px;align-items:center}
.chip{display:inline-flex;align-items:center;gap:5px;padding:3px 9px;border:1px solid var(--line);
  border-radius:999px;background:var(--surface2);font-size:11.5px;color:var(--ink2);white-space:nowrap}
.chip b{color:var(--ink);font-variant-numeric:tabular-nums}
.rail{width:9px;height:9px;border-radius:2px;flex:none}
.badge{display:inline-flex;align-items:center;gap:4px;padding:2px 7px;border-radius:5px;
  font-size:11px;font-weight:600;white-space:nowrap}
.b-ok{background:var(--s-ok-bg);color:var(--s-ok)} .b-blk{background:var(--s-blk-bg);color:var(--s-blk)}
.b-clr{background:var(--s-clr-bg);color:var(--s-clr)} .b-gap{background:var(--s-gap-bg);color:var(--s-gap)}
.b-info{background:var(--s-info-bg);color:var(--s-info)}
button,select,input{font:inherit;color:inherit}
.btn{padding:4px 10px;border:1px solid var(--line);border-radius:7px;background:var(--surface);
  cursor:pointer}
.btn:hover{border-color:var(--accent)} .btn[aria-pressed="true"]{background:var(--accent);color:#fff;border-color:var(--accent)}
input[type=search]{padding:4px 10px;border:1px solid var(--line);border-radius:7px;
  background:var(--surface);min-width:190px}
main{display:grid;grid-template-columns:1fr 400px;height:calc(100vh - 132px);min-height:460px}
@media(max-width:1000px){main{grid-template-columns:1fr;height:auto}
  #graphwrap{height:62vh} #side{height:auto;max-height:none;border-left:none;border-top:1px solid var(--line)}}
#graphwrap{position:relative;overflow:hidden;background:var(--bg)}
#svg{width:100%;height:100%;display:block;cursor:grab;touch-action:none}
#svg.drag{cursor:grabbing}
.tierlab{fill:var(--ink3);font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase}
.nd{cursor:pointer}
.nd rect.body{fill:var(--surface);stroke:var(--line);stroke-width:1}
.nd:hover rect.body{stroke:var(--accent)}
.nd.sel rect.body{stroke:var(--accent);stroke-width:2.5}
.nd .lbl{fill:var(--ink);font-size:11px;font-weight:650;font-family:var(--mono)}
.nd .sl{fill:var(--ink2);font-size:10px}
.nd .tag{fill:var(--ink3);font-size:9px;letter-spacing:.05em}
.nd.dim{opacity:.13}
.ed{stroke:var(--line);stroke-width:1.4;fill:none}
.ed.dim{opacity:.06} .ed.hot{stroke:var(--accent);stroke-width:2.2;opacity:1}
.zoombar{position:absolute;left:12px;bottom:12px;display:flex;gap:5px}
.zoombar .btn{padding:3px 9px;background:var(--surface)}
.legend{position:absolute;right:12px;top:12px;background:var(--surface);border:1px solid var(--line);
  border-radius:9px;padding:8px 10px;font-size:11px;max-width:190px}
.legend div{display:flex;align-items:center;gap:6px;margin:3px 0;cursor:pointer;user-select:none}
.legend div.off{opacity:.35}
#side{border-left:1px solid var(--line);background:var(--surface);overflow-y:auto;overflow-x:hidden}
.tabs{display:flex;border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--surface);z-index:5}
.tabs button{flex:1;padding:9px 6px;border:0;background:transparent;cursor:pointer;font-size:12.5px;
  font-weight:600;color:var(--ink3);border-bottom:2px solid transparent}
.tabs button[aria-selected="true"]{color:var(--ink);border-bottom-color:var(--accent)}
.pane{padding:14px 16px 40px}
.pane h2{font-size:14px;margin:0 0 4px}
.pane h3{font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--ink3);
  margin:18px 0 6px;font-weight:700}
.kv{display:grid;grid-template-columns:104px 1fr;gap:4px 10px;font-size:12.5px;margin:8px 0}
.kv dt{color:var(--ink3)} .kv dd{margin:0;color:var(--ink);word-break:break-word}
code,.mono{font-family:var(--mono);font-size:11.5px;background:var(--surface2);padding:1px 5px;border-radius:4px}
.crumb{display:flex;flex-wrap:wrap;gap:4px;align-items:center;font-size:11px;margin:8px 0 2px}
.crumb span{padding:2px 7px;border-radius:5px;background:var(--surface2);border:1px solid var(--line);
  cursor:pointer;font-family:var(--mono)}
.crumb span:hover{border-color:var(--accent)}
.crumb i{color:var(--ink3);font-style:normal}
details{border:1px solid var(--line);border-radius:8px;margin:8px 0;background:var(--surface2)}
details>summary{padding:7px 11px;cursor:pointer;font-size:12px;font-weight:600;list-style:none}
details>summary::-webkit-details-marker{display:none}
details>summary::before{content:"▸ ";color:var(--ink3)}
details[open]>summary::before{content:"▾ "}
.dbody{padding:0 11px 11px;overflow:auto;max-height:440px}
pre{margin:0;font-family:var(--mono);font-size:11px;white-space:pre;overflow-x:auto;
  background:var(--surface);padding:9px;border-radius:6px;border:1px solid var(--line)}
.md{font-size:12px;overflow-x:auto}
.md table{border-collapse:collapse;width:max-content;min-width:100%;font-size:11px}
.md th,.md td{border:1px solid var(--line);padding:3px 7px;text-align:left;vertical-align:top}
.md th{background:var(--surface2);font-weight:650}
.md h1{font-size:13px;margin:2px 0 6px} .md h4{font-size:12px;margin:10px 0 4px}
.md blockquote{margin:8px 0;padding:6px 10px;border-left:3px solid var(--s-clr);
  background:var(--s-clr-bg);color:var(--ink2);font-size:11.5px}
.md img{max-width:100%;height:auto;border:1px solid var(--line);border-radius:6px}
.md ul{padding-left:18px;margin:6px 0} .md li{margin:2px 0;font-size:11.5px;color:var(--ink2)}
table.vt{border-collapse:collapse;width:100%;font-size:11px}
table.vt th,table.vt td{border-bottom:1px solid var(--line2);padding:3px 6px;text-align:left;vertical-align:top}
table.vt th{color:var(--ink3);font-weight:650;text-transform:uppercase;font-size:9.5px;letter-spacing:.05em}
table.vt td.m{font-family:var(--mono)}
.iss{border:1px solid var(--line);border-radius:8px;padding:8px 10px;margin:6px 0;cursor:pointer;
  background:var(--surface2);font-size:12px}
.iss:hover{border-color:var(--accent)}
.iss .m{color:var(--ink2);margin-top:4px;font-size:11.5px}
.iss .who{font-family:var(--mono);font-size:10.5px;color:var(--ink3)}
.warn{fill:var(--s-blk)}
.note{font-size:11.5px;color:var(--ink2);background:var(--surface2);border:1px solid var(--line);
  border-radius:8px;padding:9px 11px;margin:10px 0}
.filters{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-top:8px}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
"""

JS = r"""
const G = JSON.parse(document.getElementById('graph-data').textContent);
const NS = 'http://www.w3.org/2000/svg';
const TCOL = {Objective:'--t-obj',Endpoint:'--t-end',TLF:'--t-tlf',ADaM:'--t-adam',SDTM:'--t-sdtm',Regulatory:'--t-reg'};
const TIERS = ['Objective','Endpoint / Regulatory','Deliverable (TLF)','ADaM dataset','SDTM domain'];
const NW=186, NH=40, COLGAP=252, ROWGAP=9, MX=64, MY=50;
const SUBGAP=206;              // horizontal gap between sub-columns inside one tier
const MAXROWS=18;              // wrap a tier into sub-columns beyond this many nodes

const byId = {}; G.nodes.forEach(n=>byId[n.id]=n);
const issueByNode = {};
G.issues.forEach(i=>{ if(i.nodeId){ (issueByNode[i.nodeId]=issueByNode[i.nodeId]||[]).push(i);} });

// ---- layout: layered columns; a tier taller than MAXROWS wraps into
// sub-columns so the deliverable tier (50 nodes) stays legible at fit -------
const tiers = [[],[],[],[],[]];
G.nodes.forEach(n=>tiers[n.tier].push(n));
tiers[1].sort((a,b)=> (a.type==='Regulatory'?-1:0)-(b.type==='Regulatory'?-1:0));
// deliverables read in section order; unnumbered candidates last
const secKey=n=>{ const f=n.meta&&n.meta.final_id;
  if(!f) return 'zz~'+n.label; const m=f.match(/^([TLF])-14-(\d+)(?:\.(\d+))?$/);
  return m? (m[2].padStart(2,'0')+({T:'0',L:'1',F:'2'}[m[1]])+String(m[3]||'0').padStart(2,'0')) : 'zy'+f; };
tiers[2].sort((a,b)=> secKey(a).localeCompare(secKey(b)));
const cols=[];                       // one entry per rendered sub-column
tiers.forEach((t,ti)=>{
  const ncol = Math.max(1, Math.ceil(t.length/MAXROWS));
  const per  = Math.ceil(t.length/ncol);
  cols.push({tier:ti, ncol, per, rows:per, nodes:t});
});
const tallest = Math.max(...cols.map(c=>c.rows));
let xcur = MX;
cols.forEach(c=>{
  const TH = tallest*(NH+ROWGAP);
  for(let k=0;k<c.ncol;k++){
    const slice = c.nodes.slice(k*c.per,(k+1)*c.per);
    const HH = slice.length*(NH+ROWGAP);
    slice.forEach((n,i)=>{ n.x = xcur + k*SUBGAP; n.y = MY + (TH-HH)/2 + i*(NH+ROWGAP); });
  }
  c.x0 = xcur;
  xcur += (c.ncol-1)*SUBGAP + COLGAP;
});
const W = xcur - COLGAP + NW + MX, H = MY*2 + tallest*(NH+ROWGAP);

// adjacency
const out={}, inn={};
G.edges.forEach(e=>{ (out[e.source]=out[e.source]||[]).push(e.target);
                     (inn[e.target]=inn[e.target]||[]).push(e.source); });
function lineage(id){
  const S=new Set([id]);
  (function up(x){ (inn[x]||[]).forEach(p=>{ if(!S.has(p)){S.add(p);up(p);} }); })(id);
  (function dn(x){ (out[x]||[]).forEach(c=>{ if(!S.has(c)){S.add(c);dn(c);} }); })(id);
  return S;
}

const svg=document.getElementById('svg'), root=document.createElementNS(NS,'g');
svg.appendChild(root);
const eLayer=document.createElementNS(NS,'g'), nLayer=document.createElementNS(NS,'g');
root.appendChild(eLayer); root.appendChild(nLayer);

TIERS.forEach((t,i)=>{ const x=document.createElementNS(NS,'text');
  x.setAttribute('x',cols[i].x0); x.setAttribute('y',26); x.setAttribute('class','tierlab');
  x.textContent=t; root.appendChild(x); });

const edgeEls=[];
G.edges.forEach(e=>{
  const a=byId[e.source], b=byId[e.target]; if(!a||!b) return;
  const p=document.createElementNS(NS,'path'); const x1=a.x+NW, y1=a.y+NH/2, x2=b.x, y2=b.y+NH/2;
  const mx=(x1+x2)/2;
  p.setAttribute('d',`M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`);
  p.setAttribute('class','ed'); if(e.dashed) p.setAttribute('stroke-dasharray','5 4');
  p.dataset.s=e.source; p.dataset.t=e.target; eLayer.appendChild(p); edgeEls.push(p);
});

const nodeEls={};
function esc(s){return (s==null?'':String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
G.nodes.forEach(n=>{
  const g=document.createElementNS(NS,'g'); g.setAttribute('class','nd');
  g.setAttribute('transform',`translate(${n.x},${n.y})`); g.dataset.id=n.id;
  const r=document.createElementNS(NS,'rect'); r.setAttribute('class','body');
  r.setAttribute('width',NW); r.setAttribute('height',NH); r.setAttribute('rx',8); g.appendChild(r);
  const rail=document.createElementNS(NS,'rect'); rail.setAttribute('width',4);
  rail.setAttribute('height',NH); rail.setAttribute('rx',2);
  rail.setAttribute('fill',`var(${TCOL[n.type]})`); g.appendChild(rail);
  const t1=document.createElementNS(NS,'text'); t1.setAttribute('class','lbl');
  t1.setAttribute('x',12); t1.setAttribute('y',17); t1.textContent=n.label; g.appendChild(t1);
  const t2=document.createElementNS(NS,'text'); t2.setAttribute('class','sl');
  t2.setAttribute('x',12); t2.setAttribute('y',31); t2.textContent=n.sublabel||''; g.appendChild(t2);
  const tag = n.status? ({generated:'✅',blocked:'⛔','needs-clarification':'❓'}[n.status])
            : (n.absent? '⛔' : (n.unresolved? '❓' : ((n.meta&&n.meta.level)? n.meta.level.slice(0,4).toUpperCase():'')));
  if(tag){ const t3=document.createElementNS(NS,'text'); t3.setAttribute('class','tag');
    t3.setAttribute('x',NW-8); t3.setAttribute('y',17); t3.setAttribute('text-anchor','end');
    t3.textContent=tag; g.appendChild(t3); }
  if(issueByNode[n.id]){ const w=document.createElementNS(NS,'text'); w.setAttribute('class','warn');
    w.setAttribute('x',NW-8); w.setAttribute('y',32); w.setAttribute('text-anchor','end');
    w.setAttribute('font-size','10'); w.setAttribute('font-weight','700');
    w.textContent='⚠ '+issueByNode[n.id].length; g.appendChild(w); }
  const ti=document.createElementNS(NS,'title'); ti.textContent=(n.title||n.label);
  g.appendChild(ti);
  g.addEventListener('click',ev=>{ev.stopPropagation();select(n.id);});
  nLayer.appendChild(g); nodeEls[n.id]=g;
});

// ---- pan / zoom ------------------------------------------------------------
let tx=0,ty=0,sc=1;
function apply(){ root.setAttribute('transform',`translate(${tx},${ty}) scale(${sc})`); }
function fit(){ const r=svg.getBoundingClientRect();
  sc=Math.min(r.width/(W+40), r.height/(H+40), 1.1); if(!isFinite(sc)||sc<=0) sc=.5;
  tx=(r.width-W*sc)/2; ty=(r.height-H*sc)/2; apply(); }
svg.addEventListener('wheel',e=>{e.preventDefault();
  const r=svg.getBoundingClientRect(), mx=e.clientX-r.left, my=e.clientY-r.top;
  const k=Math.exp(-e.deltaY*0.0016), ns=Math.min(3,Math.max(.15,sc*k));
  tx=mx-(mx-tx)*(ns/sc); ty=my-(my-ty)*(ns/sc); sc=ns; apply();},{passive:false});
let pan=null;
svg.addEventListener('pointerdown',e=>{ if(e.target.closest('.nd'))return;
  pan={x:e.clientX-tx,y:e.clientY-ty}; svg.classList.add('drag'); svg.setPointerCapture(e.pointerId);});
svg.addEventListener('pointermove',e=>{ if(!pan)return; tx=e.clientX-pan.x; ty=e.clientY-pan.y; apply();});
['pointerup','pointercancel'].forEach(t=>svg.addEventListener(t,()=>{pan=null;svg.classList.remove('drag');}));
svg.addEventListener('click',()=>select(null));
document.getElementById('zin').onclick=()=>{sc=Math.min(3,sc*1.25);apply();};
document.getElementById('zout').onclick=()=>{sc=Math.max(.15,sc/1.25);apply();};
document.getElementById('zfit').onclick=fit;

// ---- filters + selection ---------------------------------------------------
const typeOff=new Set(), statusOff=new Set(); let q='', sel=null;
function visible(n){
  if(typeOff.has(n.type)) return false;
  if(n.type==='TLF' && statusOff.has(n.status)) return false;
  if(q){ const s=(n.label+' '+(n.sublabel||'')+' '+(n.title||'')).toLowerCase();
         if(!s.includes(q)) return false; }
  return true;
}
function render(){
  const lin = sel? lineage(sel) : null;
  G.nodes.forEach(n=>{
    const el=nodeEls[n.id]; const vis=visible(n);
    el.style.display = vis? '' : 'none';
    el.classList.toggle('dim', !!(lin && !lin.has(n.id)));
    el.classList.toggle('sel', n.id===sel);
  });
  edgeEls.forEach(p=>{
    const a=byId[p.dataset.s], b=byId[p.dataset.t];
    const vis=visible(a)&&visible(b);
    p.style.display=vis?'':'none';
    const hot = lin && lin.has(p.dataset.s) && lin.has(p.dataset.t);
    p.classList.toggle('hot', !!hot);
    p.classList.toggle('dim', !!(lin && !hot));
  });
}
function select(id){ sel=id; render(); if(id){ showTab('detail'); detail(byId[id]); } else { detail(null); } }

// ---- tiny markdown renderer (tables, headings, quotes, lists, images) ------
function md2html(md, figData){
  if(!md) return '';
  const lines=md.split('\n'); let out=[], i=0;
  const inline=s=>esc(s).replace(/`([^`]+)`/g,'<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>')
    .replace(/&amp;nbsp;/g,'&nbsp;');
  while(i<lines.length){
    let L=lines[i];
    if(/^!\[[^\]]*\]\(.*\.png\)/.test(L)){
      if(figData) out.push(`<img src="${figData}" alt="figure">`);
      else out.push('<p class="who">[figure]</p>'); i++; continue; }
    if(/^\|/.test(L) && i+1<lines.length && /^\|[\s\-|:]+\|$/.test(lines[i+1].trim())){
      const hd=L.split('|').slice(1,-1).map(c=>c.trim());
      out.push('<table><thead><tr>'+hd.map(c=>`<th>${inline(c)}</th>`).join('')+'</tr></thead><tbody>');
      i+=2;
      while(i<lines.length && /^\|/.test(lines[i])){
        const cs=lines[i].split('|').slice(1,-1).map(c=>c.trim());
        out.push('<tr>'+cs.map(c=>`<td>${inline(c)}</td>`).join('')+'</tr>'); i++; }
      out.push('</tbody></table>'); continue; }
    if(/^####\s/.test(L)){ out.push(`<h4>${inline(L.slice(5))}</h4>`); i++; continue; }
    if(/^###\s/.test(L)){ out.push(`<h4>${inline(L.slice(4))}</h4>`); i++; continue; }
    if(/^#\s/.test(L)){ out.push(`<h1>${inline(L.slice(2))}</h1>`); i++; continue; }
    if(/^>/.test(L)){ const buf=[];
      while(i<lines.length && /^>/.test(lines[i])){ buf.push(lines[i].replace(/^>\s?/,'')); i++; }
      out.push(`<blockquote>${inline(buf.join(' '))}</blockquote>`); continue; }
    if(/^-\s/.test(L)){ const buf=[];
      while(i<lines.length && /^-\s/.test(lines[i])){ buf.push(lines[i].slice(2)); i++; }
      out.push('<ul>'+buf.map(b=>`<li>${inline(b)}</li>`).join('')+'</ul>'); continue; }
    if(/^---+$/.test(L.trim())){ i++; continue; }
    if(L.trim()===''){ i++; continue; }
    out.push(`<p>${inline(L)}</p>`); i++;
  }
  return out.join('');
}

// ---- detail panel ----------------------------------------------------------
const side=document.getElementById('pane-detail');
function kv(o){ return '<dl class="kv">'+Object.entries(o).filter(([k,v])=>v!=null&&v!=='')
  .map(([k,v])=>`<dt>${esc(k)}</dt><dd>${v}</dd>`).join('')+'</dl>'; }
function crumb(id){
  const lin=[...lineage(id)].map(x=>byId[x]);
  const ord={Objective:0,Endpoint:1,Regulatory:1,TLF:2,ADaM:3,SDTM:4};
  lin.sort((a,b)=>ord[a.type]-ord[b.type]||a.label.localeCompare(b.label));
  return '<div class="crumb">'+lin.map((n,i)=>
    (i?'<i>▸</i>':'')+`<span data-go="${esc(n.id)}" title="${esc(n.title||'')}">${esc(n.label)}</span>`
  ).join('')+'</div>';
}
function detail(n){
  if(!n){ side.innerHTML='<div class="note">Click any node to trace its full lineage — ancestors and '+
    'descendants across every tier — and inspect it here. Use the legend to filter by type, the '+
    'status buttons to filter deliverables, and the Issues tab to jump straight to a problem.</div>'; return; }
  const m=n.meta||{}; let h='';
  const st=n.status? `<span class="badge ${ {generated:'b-ok',blocked:'b-blk','needs-clarification':'b-clr'}[n.status] }">`+
    `${ {generated:'✅ generated',blocked:'⛔ blocked','needs-clarification':'❓ needs clarification'}[n.status] }</span>`:'';
  h+=`<h2>${esc(n.label)} — ${esc(n.sublabel||'')}</h2><div class="sub">${esc(n.type)} ${st}</div>`;
  h+=crumb(n.id);
  if(n.title && n.title!==n.sublabel) h+=`<div class="note">${esc(n.title)}</div>`;
  const iss=issueByNode[n.id]||[];
  if(iss.length) h+='<h3>Issues on this node</h3>'+iss.map(i=>
    `<div class="iss"><span class="badge ${sevCls(i.severity)}">${sevIcon(i.severity)}</span>`+
    `<div class="m">${esc(i.message)}</div></div>`).join('');

  if(n.type==='Objective') h+=kv({Level:esc(m.level),Source:esc(m.source),
    Description:esc(m.description||''),Endpoints:(m.endpoints||[]).map(e=>`<code>${esc(e)}</code>`).join(' ')});
  if(n.type==='Endpoint') h+=kv({Level:esc(m.level),Source:esc(m.source),Resolved:m.resolved?'yes':'<b>no</b>',
    Measure:esc(m.measure||'—'),Type:esc(m.measure_type||'—'),
    Timepoints:(m.timepoints||[]).map(t=>`<code>${esc(t)}</code>`).join(' ')||'—',
    Domain:esc(m.domain_hint||'—')});
  if(n.type==='Regulatory') h+=`<div class="note">${esc(m.note)}</div>`;
  if(n.type==='TLF'){
    h+=kv({'Final id':`<code>${esc(m.final_id||'—')}</code>`,'Candidate':`<code>${esc(m.candidate_id)}</code>`,
      Type:esc(m.type),Section:esc(m.cat_label),Priority:esc(m.priority),Method:`<code>${esc(m.method)}</code>`,
      Population:esc(m.analysisSet||m.population||'—'),Timepoint:esc(m.timepoint||'—'),
      Imputation:esc(m.imputation||'—'),Subgroup:esc(m.subgroup||'—'),
      'Analysis set':m.analysisSetCond?`<code>${esc(m.analysisSetCond)}</code>`:null,
      'Data subset':m.dataSubset?`<code>${esc(m.dataSubset)}</code>`:null,
      'Traces to':[...(m.objectives||[]),...(m.endpoints||[])].map(x=>`<code>${esc(x)}</code>`).join(' ')
        || (m.regulatory_rule?esc(m.regulatory_rule):'—'),
      ADaM:(m.adam||[]).map(x=>`<code>${esc(x)}</code>`).join(' '),
      SDTM:(m.sdtm||[]).map(x=>`<code>${esc(x)}</code>`).join(' '),
      'Produced by':esc(m.produced_by)});
    if(m.status_reason) h+=`<div class="note"><b>Status reason.</b> ${esc(m.status_reason)}</div>`;
    if(m.generatedMd) h+=`<details open><summary>Rendered display</summary><div class="dbody md">`+
      md2html(m.generatedMd, m.figureData)+`</div></details>`;
    if(m.ardJson){ let rows=[]; try{rows=JSON.parse(m.ardJson);}catch(e){}
      h+=`<details><summary>Analysis Results Data — ${rows.length} statistic${rows.length===1?'':'s'}</summary>`+
      `<div class="dbody"><table class="vt"><thead><tr><th>group</th><th>variable</th><th>level</th>`+
      `<th>context</th><th>stat</th><th>value</th></tr></thead><tbody>`+
      rows.map(r=>`<tr><td>${esc(r.group1||'')}</td><td class="m">${esc(r.variable||'')}</td>`+
        `<td>${esc(r.variable_level||'')}</td><td>${esc(r.context||'')}</td>`+
        `<td class="m">${esc(r.stat_name||'')}</td><td class="m">${esc(r.stat)}</td></tr>`).join('')+
      `</tbody></table></div></details>`; }
    if(m.generateR) h+=`<details><summary>Generation code — <code>${esc(m.generateRPath||'generate.R')}</code></summary>`+
      `<div class="dbody"><pre>${esc(m.generateR)}</pre></div></details>`;
    if((m.notes||[]).length) h+='<h3>Plan notes</h3><ul class="md">'+
      m.notes.map(x=>`<li>${esc(x)}</li>`).join('')+'</ul>';
  }
  if(n.type==='ADaM'){
    h+=kv({Class:esc(m.klass),'SDTM source':(m.sdtm_source||[]).map(x=>`<code>${esc(x)}</code>`).join(' '),
      'Used by':(m.used_by_tables||[]).map(x=>`<code>${esc(x)}</code>`).join(' ')||'—',
      'Mandatory rules':(m.derivation_requirements||[]).join('; ')||'—'});
    if((m.parameters||[]).length) h+=`<details open><summary>Parameters (${m.parameters.length})</summary>`+
      `<div class="dbody"><table class="vt"><thead><tr><th>PARAMCD</th><th>PARAM</th><th>note</th></tr></thead><tbody>`+
      m.parameters.map(p=>`<tr><td class="m">${esc(p.paramcd)}</td><td>${esc(p.param)}</td>`+
        `<td>${esc(p.note||'')}</td></tr>`).join('')+`</tbody></table></div></details>`;
    if((m.variables||[]).length) h+=`<details><summary>Variables (${m.variables.length})</summary>`+
      `<div class="dbody"><table class="vt"><thead><tr><th>name</th><th>role</th><th>source</th></tr></thead><tbody>`+
      m.variables.map(v=>`<tr><td class="m">${esc(v.name)}</td><td>${esc(v.role)}</td>`+
        `<td class="m">${esc(v.source||(v.source_domains||[]).join(', '))}</td></tr>`).join('')+
      `</tbody></table></div></details>`;
    if((m.notes||[]).length) h+='<h3>Derivation notes</h3><ul class="md">'+
      m.notes.map(x=>`<li>${esc(x)}</li>`).join('')+'</ul>';
  }
  if(n.type==='SDTM'){
    const cons=G.nodes.filter(x=>x.type==='ADaM'&&(x.meta.sdtm_source||[]).includes(m.domain));
    h+=kv({Domain:`<code>${esc(m.domain)}</code>`,Label:esc(m.label),
      'In inventory':m.present_in_inventory?'yes':'<b>NO — absent</b>'});
    h+='<h3>Consumed by</h3>';
    h+= cons.length? `<table class="vt"><thead><tr><th>ADaM</th><th>variables drawing on ${esc(m.domain)}</th>`+
      `</tr></thead><tbody>`+cons.map(c=>{
        const vs=(c.meta.variables||[]).filter(v=>(v.source_domains||[]).includes(m.domain));
        return `<tr><td class="m">${esc(c.label)}</td><td class="m">`+
          (vs.length? vs.map(v=>esc(v.name)).join(', ') : '<span class="who">(dataset-level)</span>')+
          `</td></tr>`;}).join('')+`</tbody></table>`
      : '<div class="note">No derived ADaM dataset consumes this domain.</div>';
  }
  side.innerHTML=h;
  side.querySelectorAll('[data-go]').forEach(el=>el.onclick=()=>select(el.dataset.go));
}

// ---- issues panel ----------------------------------------------------------
function sevCls(s){return {blocked:'b-blk',clarification:'b-clr',gap:'b-gap',info:'b-info'}[s]||'b-info';}
function sevIcon(s){return {blocked:'⛔ blocked',clarification:'❓ clarification',gap:'▲ coverage gap',info:'ℹ info'}[s]||s;}
function issuesPane(){
  const el=document.getElementById('pane-issues');
  const tally={}; G.issues.forEach(i=>tally[i.severity]=(tally[i.severity]||0)+1);
  let h='<div class="chips">'+Object.entries(tally).map(([k,v])=>
    `<span class="badge ${sevCls(k)}">${sevIcon(k)} ${v}</span>`).join('')+'</div>';
  h+='<div class="filters">'+['blocked','clarification','gap','info'].map(s=>
    `<button class="btn" data-sev="${s}" aria-pressed="true">${s}</button>`).join('')+'</div>';
  h+='<div id="isslist">'+G.issues.map((i,ix)=>
    `<div class="iss" data-ix="${ix}" data-sev="${i.severity}">`+
    `<span class="badge ${sevCls(i.severity)}">${sevIcon(i.severity)}</span> `+
    (i.nodeId?`<span class="who">${esc(byId[i.nodeId]?byId[i.nodeId].label:i.nodeId)}</span>`:'')+
    `<div class="m">${esc(i.message)}</div></div>`).join('')+'</div>';
  el.innerHTML=h;
  el.querySelectorAll('[data-ix]').forEach(d=>d.onclick=()=>{
    const i=G.issues[+d.dataset.ix];
    if(i.nodeId){ select(i.nodeId); focusNode(i.nodeId); } });
  el.querySelectorAll('[data-sev]').forEach(b=>b.onclick=()=>{
    const on=b.getAttribute('aria-pressed')==='true'; b.setAttribute('aria-pressed',String(!on));
    el.querySelectorAll(`#isslist [data-sev="${b.dataset.sev}"]`).forEach(r=>r.style.display=on?'none':'');});
}
function focusNode(id){ const n=byId[id]; if(!n) return; const r=svg.getBoundingClientRect();
  sc=Math.max(sc,.75); tx=r.width/2-(n.x+NW/2)*sc; ty=r.height/2-(n.y+NH/2)*sc; apply(); }

// ---- tabs / controls -------------------------------------------------------
function showTab(t){ ['detail','issues'].forEach(k=>{
  document.getElementById('pane-'+k).style.display = k===t?'':'none';
  document.getElementById('tab-'+k).setAttribute('aria-selected',String(k===t)); }); }
document.getElementById('tab-detail').onclick=()=>showTab('detail');
document.getElementById('tab-issues').onclick=()=>showTab('issues');
document.querySelectorAll('.legend div').forEach(d=>d.onclick=()=>{
  const t=d.dataset.type; if(typeOff.has(t)){typeOff.delete(t);d.classList.remove('off');}
  else{typeOff.add(t);d.classList.add('off');} render(); });
document.querySelectorAll('[data-status]').forEach(b=>b.onclick=()=>{
  const s=b.dataset.status; const on=b.getAttribute('aria-pressed')==='true';
  b.setAttribute('aria-pressed',String(!on)); if(on) statusOff.add(s); else statusOff.delete(s); render(); });
document.getElementById('q').addEventListener('input',e=>{q=e.target.value.trim().toLowerCase();render();});
const tb=document.getElementById('theme');
tb.onclick=()=>{ const cur=document.documentElement.getAttribute('data-theme')
  || (matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light');
  document.documentElement.setAttribute('data-theme', cur==='dark'?'light':'dark'); };

issuesPane(); detail(null); showTab('detail'); render();
window.addEventListener('resize',()=>{});
fit();
"""

def chips(G):
    c = G["counts"]; s = G["status"]
    items = [("Objectives", c["objectives"], "--t-obj"), ("Endpoints", c["endpoints"], "--t-end"),
             ("Deliverables", c["tlf"], "--t-tlf"), ("ADaM", c["adam"], "--t-adam"),
             ("SDTM", c["sdtm"], "--t-sdtm")]
    h = "".join('<span class="chip"><i class="rail" style="background:var(%s)"></i>%s <b>%d</b></span>'
                % (v, k, n) for k, n, v in items)
    h += ('<span class="badge b-ok">✅ generated %d</span>'
          '<span class="badge b-blk">⛔ blocked %d</span>'
          '<span class="badge b-clr">❓ clarification %d</span>'
          % (s.get("generated", 0), s.get("blocked", 0), s.get("needs-clarification", 0)))
    h += ('<span class="badge b-gap">▲ unresolved endpoints %d</span>'
          '<span class="badge b-blk">⛔ absent SDTM %d</span>'
          % (c["endpoints_unresolved"], c["sdtm_absent"]))
    return h

LEG = "".join('<div data-type="%s"><i class="rail" style="background:var(%s)"></i>%s</div>'
              % (t, v, t) for t, v in [("Objective","--t-obj"),("Endpoint","--t-end"),
              ("Regulatory","--t-reg"),("TLF","--t-tlf"),("ADaM","--t-adam"),("SDTM","--t-sdtm")])

HTML = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Traceability Explorer — {G['study']['id']}</title>
<style>{CSS}</style></head><body>
<header>
  <h1>Traceability Explorer — {G['study']['id']}</h1>
  <div class="sub">{G['study']['title']} · {G['study']['phase']} ·
    Objective → Endpoint → Deliverable → ADaM → SDTM, with the ARD as the connective layer</div>
  <div class="chips">{chips(G)}</div>
  <div class="filters">
    <input type="search" id="q" placeholder="Search id, title, measure…" aria-label="Search">
    <span class="chip" style="border:0;background:transparent">status:</span>
    <button class="btn" data-status="generated" aria-pressed="true">generated</button>
    <button class="btn" data-status="blocked" aria-pressed="true">blocked</button>
    <button class="btn" data-status="needs-clarification" aria-pressed="true">clarification</button>
    <button class="btn" id="theme" style="margin-left:auto">◐ theme</button>
  </div>
</header>
<main>
  <div id="graphwrap">
    <svg id="svg" role="img" aria-label="Traceability graph"></svg>
    <div class="legend">{LEG}</div>
    <div class="zoombar">
      <button class="btn" id="zout" aria-label="Zoom out">−</button>
      <button class="btn" id="zfit">fit</button>
      <button class="btn" id="zin" aria-label="Zoom in">+</button>
    </div>
  </div>
  <aside id="side">
    <div class="tabs" role="tablist">
      <button id="tab-detail" role="tab" aria-selected="true">Detail</button>
      <button id="tab-issues" role="tab" aria-selected="false">Issues ({len(G['issues'])})</button>
    </div>
    <div class="pane" id="pane-detail"></div>
    <div class="pane" id="pane-issues" style="display:none"></div>
  </aside>
</main>
<script id="graph-data" type="application/json">{DATA}</script>
<script>{JS}</script>
</body></html>
"""
p = os.path.join(OUT, "traceability.html")
open(p, "w").write(HTML)
print("wrote", p, "%.1f MB" % (len(HTML)/1e6))
