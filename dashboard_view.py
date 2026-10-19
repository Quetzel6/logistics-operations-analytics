"""Offline presentation layer. All business calculations stay in project.py."""
from html import escape

CSS='''
:root{--navy:#142d3b;--muted:#60737b;--teal:#087c78;--line:#dce5e5;--paper:#f5f7f5}*{box-sizing:border-box}body{font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:0;max-width:none;padding:0;background:var(--paper);color:var(--navy);font-size:15px}header{padding:38px 44px 30px;background:var(--navy);color:white}header h1{font-size:clamp(28px,4vw,42px);letter-spacing:-1.5px;margin:12px 0}header p{margin:6px 0;color:#c4d7db}header .tag{color:#a7e4cc;font-size:11px;font-weight:700;letter-spacing:2px}#app-nav{background:#fff;border-bottom:1px solid var(--line);padding:0 44px;display:flex;gap:20px;position:sticky;top:0;z-index:10}#app-nav button{padding:18px 6px;background:none;border:0;border-bottom:3px solid transparent;font:inherit;color:var(--muted);cursor:pointer}#app-nav button[aria-selected=true]{color:var(--teal);border-color:var(--teal);font-weight:700}.cards{padding:28px 44px 0;display:grid;grid-template-columns:repeat(4,1fr);gap:16px}.cards article{background:white;min-width:0;padding:22px;border:1px solid var(--line);border-radius:10px}.cards small{display:block;font-size:12px;color:var(--muted)}.cards strong{display:block;font-size:34px;letter-spacing:-1px;margin-top:10px}.cards article:last-child strong{color:#a95a20}section{margin:22px 44px;background:white;padding:26px 28px;border:1px solid var(--line);border-radius:12px;overflow:auto}h2{font-size:21px;letter-spacing:-.4px;margin:0 0 12px}h3{font-size:17px;margin:26px 0 10px}p{line-height:1.65;color:#526771;max-width:100ch}td,th{padding:13px 12px;border-bottom:1px solid #e6eded;text-align:left;font-size:13px}th{background:#f4f7f7;color:#536d75;font-size:11px;letter-spacing:.4px}table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}tbody tr:hover{background:#f1f8f6}label{display:inline-flex;flex-direction:column;gap:7px;margin:10px 18px 12px 0;font-size:12px;font-weight:600}select{font:inherit;background:#fff;border:1px solid #b9cdcc;border-radius:7px;padding:10px;min-width:150px;color:var(--navy)}#scope{padding:12px 16px;background:#edf6f3;border-radius:6px;color:#225c50;font-size:13px}.eyebrow{color:var(--teal);font-size:11px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase}.bar-row{display:grid;grid-template-columns:130px 1fr 65px;align-items:center;gap:18px;padding:12px 0;font-size:13px}.bar-track{height:12px;border-radius:8px;background:#edf1f0}.bar-fill{height:12px;border-radius:8px;background:#139a8e}.bar-fill.warning{background:#ce824c}.bar-value{font-weight:700;text-align:right}.figure-note{font-size:12px;color:var(--muted)}.chart-grid{display:grid;grid-template-columns:1fr 1fr;gap:32px}.insight-box{background:#f3f7f5;border-radius:10px;padding:20px}.insight-box b{display:block;margin:8px 0;font-size:20px}#trend-chart{width:100%;height:auto;max-height:250px}.table-scroll{max-height:420px;overflow:auto}a{color:var(--teal)}[hidden]{display:none!important}button:focus-visible,select:focus-visible,a:focus-visible{outline:3px solid #e9ab43;outline-offset:3px}#app-footer{padding:20px 44px 36px;color:var(--muted);font-size:12px}@media(max-width:720px){header{padding:26px 20px}.cards{padding:20px;grid-template-columns:1fr 1fr}.cards strong{display:block;font-size:28px}section{margin:16px;padding:20px}.chart-grid{grid-template-columns:1fr}#app-nav{padding:0 16px;gap:12px;overflow:auto}#app-nav button{white-space:nowrap;font-size:13px}.bar-row{grid-template-columns:100px 1fr 50px;gap:10px}.table-scroll{max-height:360px}#app-footer{padding:20px}}@media print{#app-nav{display:none}section[hidden],.cards[hidden]{display:block!important}section{break-inside:avoid}header{background:white;color:#142d3b}header p,header .tag{color:#526771}.table-scroll{max-height:none}}
'''
SCRIPT='''
(function(){
 const sections=[...document.querySelectorAll('body > section')];
 for(const s of sections){
  const title=s.querySelector('h2').textContent;
  s.dataset.pane=title.startsWith('Daily')?'exceptions':title.startsWith('Capacity')||title.startsWith('What does')||title.startsWith('How sensitive')?'scenarios':title.startsWith('Definitions')?'methods':'overview';
  if(title.startsWith('Warehouse')){const d=document.createElement('details');const sum=document.createElement('summary');sum.textContent='Show exact cohort metrics';d.append(sum);const table=s.querySelector('table');d.append(table);s.append(d);}
  for(const table of s.querySelectorAll('table')){const wrap=document.createElement('div');wrap.className='table-scroll';table.replaceWith(wrap);wrap.append(table);}
 }
 const nav=document.createElement('nav');nav.id='app-nav';nav.setAttribute('aria-label','Dashboard sections');nav.setAttribute('role','tablist');
 const choices=[['overview','01 Overview'],['exceptions','02 Exceptions'],['scenarios','03 Scenarios'],['methods','04 Definitions']];
 function show(pane){sections.forEach(s=>s.hidden=s.dataset.pane!==pane);document.querySelector('.cards').hidden=pane!=='overview';[...nav.children].forEach(b=>b.setAttribute('aria-selected',String(b.dataset.pane===pane)));}
 for(const [id,label] of choices){const b=document.createElement('button');b.textContent=label;b.dataset.pane=id;b.setAttribute('role','tab');b.addEventListener('click',()=>show(id));nav.append(b);}
 document.querySelector('header').after(nav);show('overview');
 const dailyBody=document.getElementById('daily');
 const chart=document.createElementNS('http://www.w3.org/2000/svg','svg');chart.id='trend-chart';chart.setAttribute('viewBox','0 0 720 240');chart.setAttribute('role','img');chart.setAttribute('aria-label','Daily OTIF percentage by promised delivery date, snapshot outcomes');dailyBody.closest('.table-scroll').before(chart);
 function draw(){
  const data=JSON.parse(document.getElementById('detail-data').textContent);
  const selected=selectDetails(data,document.getElementById('warehouse').value,document.getElementById('route').value,'').daily;
  chart.replaceChildren();
  function el(tag,attrs,text){const e=document.createElementNS(chart.namespaceURI,tag);Object.entries(attrs).forEach(([k,v])=>e.setAttribute(k,v));if(text!==undefined)e.textContent=text;chart.append(e);return e;}
  for(const rate of [0,0.5,1]){const y=200-rate*170;el('line',{x1:48,x2:700,y1:y,y2:y,stroke:'#dce5e5'});el('text',{x:5,y:y+4,fill:'#60737b','font-size':12},(rate*100)+'%');}
  if(!selected.length){el('text',{x:230,y:110,fill:'#60737b'},'No matching daily records');return;}
  const points=selected.map((d,i)=>[48+(selected.length===1?320:i*652/(selected.length-1)),200-170*d.otif_orders/d.due_orders]);
  el('polyline',{points:points.map(p=>p.join(',')).join(' '),fill:'none',stroke:'#087c78','stroke-width':3});
  selected.forEach((d,i)=>{const dot=el('circle',{cx:points[i][0],cy:points[i][1],r:3,fill:'#087c78'});const title=document.createElementNS(chart.namespaceURI,'title');title.textContent=`${d.due_date}: ${(100*d.otif_orders/d.due_orders).toFixed(1)}% (${d.otif_orders}/${d.due_orders})`;dot.append(title);});
  el('text',{x:48,y:225,fill:'#60737b','font-size':12},selected[0].due_date);el('text',{x:700,y:225,fill:'#60737b','font-size':12,'text-anchor':'end'},selected[selected.length-1].due_date);
 }
 ['warehouse','route'].forEach(id=>document.getElementById(id).addEventListener('change',draw));draw();
})();
'''

def enhance(source, report):
    bars=''.join('<div class="bar-row"><span>'+escape(r['warehouse']+' / '+r['route'])+'</span><div class="bar-track"><div class="bar-fill '+('warning' if r['otif_rate']<.8 else '')+'" style="width:'+str(100*r['otif_rate'])+'%"></div></div><span class="bar-value">'+format(r['otif_rate'],'.1%')+'</span></div>' for r in report['cohorts'])
    chart='<section><p class="eyebrow">Network health / where to look</p><h2>Service reliability by warehouse &amp; route</h2><div class="chart-grid"><div>'+bars+'</div><div class="insight-box"><p class="eyebrow">Interpretation</p><b>Separate late delivery from capacity shortage.</b><p>Use the exception worklist to inspect individual orders. Use scenario replay to investigate capacity independently. Neither proves a root cause.</p><p class="figure-note">Bars use a common 0–100% scale. Orange marks OTIF below an illustrative 80% review threshold, not an agreed company target.</p></div></div></section>'
    start=source.index('<style>');end=source.index('</style>',start)+len('</style>')
    source=source[:start]+'<style>'+CSS+'</style>'+source[end:]
    summary=next(r for r in report['capacity_scenarios'] if r['scope']=='All network' and r['capacity_increment_pct']==10)
    brief='<section><p class="eyebrow">Capacity replay / at a glance</p><h2>What does +10% network capacity absorb?</h2><div class="chart-grid"><div class="insight-box"><span>Added homogeneous capacity units</span><b>'+format(summary['added_capacity_units'],',')+'</b></div><div class="insight-box"><span>Additional recoverable units · upper bound</span><b>'+format(summary['incremental_recoverable_units'],',')+'</b></div></div><p>'+format(summary['remaining_short_units'],',')+' short units remain in this replay. Capacity units are not vehicle counts; recovery assumes stock, labor and loading are unconstrained. No cost savings or improvement in delivery time is estimated.</p></section>'
    source=source.replace('<section><h2>How sensitive',brief+'<section><h2>How sensitive',1)
    anchor='<section><h2>Where should operations investigate first?'
    source=source.replace(anchor,chart+anchor)
    source=source.replace('</html>','<footer id="app-footer">Synthetic portfolio • End-of-day snapshot • Offline, no external dependencies • Built for evidence-led discussion</footer><script>'+SCRIPT+'</script></html>')
    return source
