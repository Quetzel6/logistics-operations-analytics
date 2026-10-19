function selectDetails(data, warehouse, route, issue) {
  const inScope=r=>(!warehouse||r.warehouse===warehouse)&&(!route||r.route===route);
  const exceptions=data.exceptions.filter(r=>inScope(r)&&(!issue||r.flags.includes(issue)));
  const dates=new Map();
  data.daily.filter(inScope).forEach(r=>{
    if(!dates.has(r.due_date)) dates.set(r.due_date,{due_date:r.due_date,due_orders:0,on_time_orders:0,otif_orders:0,overdue_open:0});
    const d=dates.get(r.due_date);
    for(const k of ['due_orders','on_time_orders','otif_orders','overdue_open'])d[k]+=r[k];
  });
  return {exceptions,daily:[...dates.values()].sort((a,b)=>a.due_date.localeCompare(b.due_date))};
}
if(typeof module!=='undefined')module.exports={selectDetails};
if(typeof document!=='undefined') {
 const data=JSON.parse(document.getElementById('detail-data').textContent);
 const ids=['warehouse','route','issue'];
 const cell=v=>{const td=document.createElement('td');td.textContent=String(v);return td;};
 function rows(id, data) {
  const body=document.getElementById(id);body.replaceChildren();
  if(!data.length){const tr=document.createElement('tr');const td=cell('No matching records');td.colSpan=6;tr.append(td);body.append(tr);return;}
  data.forEach(vals=>{const tr=document.createElement('tr');vals.forEach(v=>tr.append(cell(v)));body.append(tr);});
 }
 function update(){
  const [w,r,i]=ids.map(id=>document.getElementById(id).value);
  const selected=selectDetails(data,w,r,i);
  document.getElementById('scope').textContent=`Selected: ${w||'All warehouses'} / ${r||'All routes'}; ${selected.exceptions.length} exception orders. Total due orders: ${selected.daily.reduce((n,d)=>n+d.due_orders,0)}.`;
  rows('daily',selected.daily.map(d=>[d.due_date,d.due_orders,(100*d.on_time_orders/d.due_orders).toFixed(1)+'%',(100*d.otif_orders/d.due_orders).toFixed(1)+'%',d.overdue_open]));
  rows('exceptions',selected.exceptions.map(o=>[o.order_id,o.warehouse+' / '+o.route,o.due_date+' / '+(o.delivered_date||'Not delivered'),o.flags.join('; '),o.late_days,o.short_units]));
 }
 ids.forEach(id=>document.getElementById(id).addEventListener('change',update));update();
}
