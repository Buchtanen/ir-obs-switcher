import {test} from 'node:test';
import assert from 'node:assert/strict';
import {componentSignal,connectionSignal,iracingSignal} from './status-model.ts';
test('launcher is an amber hint only while SDK is explicitly disconnected',()=>{
  assert.deepEqual(iracingSignal(false,true,false),{tone:'warn',label:'iRacing UI'});
  assert.equal(iracingSignal(true,true,false).tone,'good');
  assert.equal(iracingSignal(false,false,false).tone,'bad');
  assert.equal(iracingSignal(false,null,false).tone,'bad');
  assert.equal(iracingSignal(false,undefined,false).tone,'bad');
  assert.equal(iracingSignal(false,true,true).tone,'unknown');
  assert.equal(iracingSignal(undefined,true,false).tone,'unknown');
});
test('missing or stale connection is never green',()=>{
  assert.equal(connectionSignal(true,false).tone,'good');
  assert.equal(connectionSignal(false,false).tone,'bad');
  assert.equal(connectionSignal(true,true).tone,'unknown');
  assert.equal(connectionSignal(undefined,false).tone,'unknown');
});
test('component failures, waiting and intentionally disabled modules differ',()=>{
  assert.equal(componentSignal({status:'connected',available:true},false).tone,'good');
  assert.equal(componentSignal({status:'connected',available:false},false).tone,'warn');
  assert.equal(componentSignal({status:'error'},false).tone,'bad');
  assert.equal(componentSignal({status:'connecting'},false).tone,'warn');
  assert.equal(componentSignal({enabled:false,available:false},false).tone,'off');
  assert.equal(componentSignal({status:'idle'},false).tone,'off');
});
test('stale provider and stale API cannot falsely signal healthy operation',()=>{
  assert.equal(componentSignal({status:'connected',detail:{stale:true}},false).tone,'warn');
  assert.equal(componentSignal({status:'running'},true).tone,'unknown');
  assert.equal(componentSignal({enabled:false},true).tone,'unknown');
});
test('configuration flags and unknown statuses do not imply live runtime',()=>{
  assert.equal(componentSignal({practice:true,v2Payload:true},false).tone,'unknown');
  assert.equal(componentSignal({status:'future_status'},false).tone,'unknown');
  assert.equal(componentSignal(undefined,false).tone,'unknown');
  for(const status of ['__proto__','constructor','toString'])assert.deepEqual(componentSignal({status},false),{tone:'unknown',label:status});
});
