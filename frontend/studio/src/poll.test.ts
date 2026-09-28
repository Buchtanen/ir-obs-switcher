import { test } from 'node:test';
import assert from 'node:assert/strict';
import { startPolling, connectionLabel, parseStatus, parseActivity } from './poll.ts';

test('unavailable or stale evidence never claims a connection', () => {
  assert.equal(connectionLabel(true, false), 'Připojeno');
  assert.equal(connectionLabel(true, true), 'Neznámý stav');
  assert.equal(connectionLabel(undefined, false), 'Neznámý stav');
  assert.equal(connectionLabel(false, false), 'Odpojeno');
});

test('rejects incompatible payloads', () => {
  assert.throws(() => parseStatus({schemaVersion: 2}));
  assert.throws(() => parseActivity({schemaVersion: 1, items: 'wrong'}));
  assert.throws(() => parseStatus({schemaVersion: 1, runtime: {}, switcher: {connected_obs: 'true'}}));
  const base = {schemaVersion: 1, version: 'test', runtime: {overlay: true, switcher: true}, switcher: {connected_obs: true, connected_iracing: false, autoswitch: false}};
  assert.throws(() => parseStatus({...base, switcher: {...base.switcher, reason: {bad: true}}}));
  assert.throws(() => parseStatus({...base, extensions: {ble: {label: {bad: true}}}}));
  for(const running of [true,false,null])assert.equal(parseStatus({...base,iracingUi:{running}}).iracingUi?.running,running);
  assert.equal(parseStatus(base).iracingUi,undefined);
  const app={id:'dre',label:'DRE',running:true,required:true};
  assert.deepEqual(parseStatus({...base,companionApps:[app]}).companionApps,[app]);
  for(const companionApps of [null,{},[app,app],[{...app,running:'true'}],[{...app,required:null}]])assert.throws(()=>parseStatus({...base,companionApps}));
  for(const iracingUi of [null,{},[],{running:'true'}])assert.throws(()=>parseStatus({...base,iracingUi}));
});

test('retains last successful data after a failed refresh', async () => {
  let attempts = 0;
  const states: any[] = [];
  let stop = () => {};
  await new Promise<void>(resolve => {
    stop = startPolling(async () => {
      if (++attempts === 1) return {version: 'test'};
      throw new Error('offline');
    }, state => {
      states.push(state);
      if (state.stale) { stop(); resolve(); }
    }, 1, 100);
  });
  assert.equal(states.at(-1).data.version, 'test');
  assert.equal(states.at(-1).error, 'offline');
});

test('timeout cancels a request and stop prevents subsequent publication', async () => {
  let aborted = false;
  const states: any[] = [];
  const stop = startPolling(signal => new Promise((_resolve, reject) => {
    signal.addEventListener('abort', () => { aborted = true; reject(new Error('aborted')); });
  }), state => states.push(state), 100, 5);
  await new Promise(resolve => setTimeout(resolve, 25));
  stop();
  assert.equal(aborted, true);
  assert.equal(states.at(-1).stale, true);
  const count = states.length;
  await new Promise(resolve => setTimeout(resolve, 20));
  assert.equal(states.length, count);
});

test('polling never overlaps and cancellation aborts pending work', async () => {
  let calls = 0;
  let signal: AbortSignal;
  let finish: (value: number) => void;
  const stop = startPolling(s => {
    calls++; signal = s;
    return new Promise<number>(resolve => { finish = resolve; });
  }, () => {}, 1, 500);
  await new Promise(resolve => setTimeout(resolve, 10));
  assert.equal(calls, 1);
  stop();
  assert.equal(signal!.aborted, true);
  finish!(1);
  await new Promise(resolve => setTimeout(resolve, 10));
  assert.equal(calls, 1);
});
