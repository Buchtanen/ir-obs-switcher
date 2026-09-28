import {test} from 'node:test';
import assert from 'node:assert/strict';
import {companionSignal,readinessSignal} from './companion-model.ts';
const all=['dre','maira','simhub','cammus','trading_paints','virtual_desktop'].map(id=>({id,label:id,running:true as boolean|null,required:true}));
test('readiness reflects only requested app processes',()=>{
  assert.equal(readinessSignal(all,false).tone,'good');
  assert.equal(readinessSignal(all.map((r,i)=>i? r:{...r,running:false}),false).tone,'warn');
  assert.equal(readinessSignal(all.map((r,i)=>i? r:{...r,running:false,required:false}),false).tone,'good');
  assert.equal(readinessSignal(all.map(r=>({...r,required:false})),false).tone,'off');
});
test('stale, absent, partial and unknown readings never promise readiness',()=>{
  assert.equal(readinessSignal(all,true).tone,'unknown');
  assert.equal(readinessSignal(undefined,false).tone,'unknown');
  assert.equal(readinessSignal(all.slice(1),false).tone,'unknown');
  assert.equal(readinessSignal(all.map((r,i)=>i? r:{...r,running:null}),false).tone,'unknown');
  assert.equal(companionSignal({...all[0],running:false,required:false},false).tone,'off');
  assert.equal(companionSignal(all[0],true).tone,'unknown');
  assert.equal(companionSignal({...all[0],running:null},false).tone,'unknown');
});
