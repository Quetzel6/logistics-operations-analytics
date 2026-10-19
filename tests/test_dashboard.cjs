const assert=require('node:assert/strict');
const {selectDetails}=require('../dashboard.js');
const data=require('../output/report.json');
const all=selectDetails(data,'','','');
assert.equal(all.daily.reduce((n,r)=>n+r.due_orders,0),data.totals.due_orders);
assert.equal(all.daily.reduce((n,r)=>n+r.otif_orders,0),data.totals.otif_orders);
for(const cohort of data.cohorts){
 const result=selectDetails(data,cohort.warehouse,cohort.route,'');
 assert.equal(result.daily.reduce((n,r)=>n+r.due_orders,0),cohort.due_orders);
 assert.equal(result.daily.reduce((n,r)=>n+r.otif_orders,0),cohort.otif_orders);
 const open=selectDetails(data,cohort.warehouse,cohort.route,'Overdue open');
 assert.equal(open.exceptions.length,cohort.overdue_open);
 assert.deepEqual(open.daily,result.daily);
}
assert.equal(new Set(all.exceptions.map(o=>o.order_id)).size,all.exceptions.length);
assert.deepEqual(selectDetails(data,'missing','',''),{exceptions:[],daily:[]});
console.log('PASS: filters, daily/cohort reconciliation, stable denominators, unique exception orders, empty scope');
