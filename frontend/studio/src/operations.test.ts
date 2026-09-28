import {test} from 'node:test';
import assert from 'node:assert/strict';
import {postAction, overrideBody, speakBody, parseObject} from './operations-api.ts';

test('override and speech validation preserve existing contracts',()=>{
  assert.deepEqual(overrideBody('  Race  ','120'),{scene:'Race',seconds:120});
  for(const seconds of ['0','-1','1.5','NaN']) assert.throws(()=>overrideBody('Race',seconds));
  assert.throws(()=>overrideBody('','10'));
  assert.deepEqual(speakBody(' Hello   world. '),{schemaVersion:'commentary-runtime/2',language:'en',text:'Hello world.'});
  assert.throws(()=>speakBody('x'.repeat(401)));
  assert.throws(()=>parseObject([]));
});
test('actions never retry, include transport headers and propagate structured errors',async()=>{
  let calls=0;
  await assert.rejects(postAction('/api/commentary/speak',{},new AbortController().signal,async(_url,options)=>{
    calls++;assert.equal(options.method,'POST');assert.equal(options.headers['X-Requested-With'],'irswitch');
    return new Response(JSON.stringify({error:{code:'speech_busy'}}),{status:409});
  }),/speech_busy/);
  assert.equal(calls,1);
});
test('timeout cancels action and does not retry',async()=>{
  let calls=0,aborted=false;
  await assert.rejects(postAction('/autoswitch/toggle',{},new AbortController().signal,async(_url,options)=>{
    calls++;return new Promise((_resolve,reject)=>options.signal.addEventListener('abort',()=>{aborted=true;reject(new Error('aborted'));}));
  },5));
  assert.equal(calls,1);assert.equal(aborted,true);
});
