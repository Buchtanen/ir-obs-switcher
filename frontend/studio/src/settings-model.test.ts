import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseConfig, makeDraft, analyseDraft, parseSave, requestConfig, ConfigRequestError, reconcileDraft } from './settings-model.ts';

const field = (key: string, type = 'float', extra = {}) => ({key, type, default: 2, live: true, section: 'sampling', help: 'Sample rate', min: 1, max: 20, optional: false, choices: null, secret: false, ...extra});
const payload = () => ({schema: [field('sampling.hz'), field('overlay.enabled', 'bool', {default: true, min: null, max: null}), field('overlay.theme', 'str', {default: 'dark', min: null, max: null, choices: ['dark', 'light']}), field('sampling.optional', 'int', {optional: true, default: null})], overlay: {'sampling.hz': 2, 'overlay.enabled': true, 'overlay.theme': 'dark', 'sampling.optional': null}, switcher: {'obs.password': '<redacted>'}});

test('schema projects only editable fields and never imports switcher or secret values', () => {
  const data = payload();
  data.schema.push(field('secret', 'str', {secret: true, default: 'hidden'}));
  const config = parseConfig({...data, overlay: {...data.overlay, secret: 'hidden', unexpected: 'ignored'}});
  assert.equal(config.schema.length, 4);
  assert.equal(JSON.stringify(config).includes('hidden'), false);
  assert.equal(Object.keys(makeDraft(config)).length, 4);
  assert.deepEqual(analyseDraft(config, makeDraft(config)).changes, []);
});

test('malformed schema/value fails closed rather than replacing missing data with defaults', () => {
  assert.throws(() => parseConfig({schema: [], overlay: {}}));
  assert.throws(() => parseConfig({...payload(), overlay: {}}));
  assert.throws(() => parseConfig({...payload(), schema: [field('sampling.hz'), field('sampling.hz')]}));
  assert.throws(() => parseConfig({...payload(), schema: [field('sampling.hz', 'object')]}));
  assert.throws(() => parseConfig({...payload(), overlay: {...payload().overlay, 'sampling.hz': {bad: true}}}));
});

test('changed-only patch canonicalizes numbers, booleans, choices and optional removal', () => {
  const config = parseConfig(payload());
  const draft = {...makeDraft(config), 'sampling.hz': '2.0', 'overlay.enabled': false, 'overlay.theme': 'light', 'sampling.optional': '3'};
  const result = analyseDraft(config, draft);
  assert.deepEqual(result.values, {'overlay.enabled': false, 'overlay.theme': 'light', 'sampling.optional': 3});
  assert.deepEqual(result.errors, {});
  const withOptional = parseConfig({...payload(), overlay: {...payload().overlay, 'sampling.optional': 4}});
  assert.deepEqual(analyseDraft(withOptional, {...makeDraft(withOptional), 'sampling.optional': null}).values, {'sampling.optional': null});
});

test('invalid numbers, bounds, choices and traversal block save while remaining dirty', () => {
  const config = parseConfig(payload());
  for (const bad of ['NaN', 'Infinity', '0x10', '21', '0', '2oops']) {
    const result = analyseDraft(config, {...makeDraft(config), 'sampling.hz': bad});
    assert.ok(result.errors['sampling.hz'], bad);
    assert.equal(result.changes.length, 1);
  }
  assert.ok(analyseDraft(config, {...makeDraft(config), 'sampling.optional': '1.5'}).errors['sampling.optional']);
  assert.ok(analyseDraft(config, {...makeDraft(config), 'overlay.theme': 'bogus'}).errors['overlay.theme']);
  const paths = parseConfig({schema:[field('system_info.lhm_dll_path','str',{default:'', optional:true, min:null,max:null})], overlay:{'system_info.lhm_dll_path':null}});
  assert.ok(analyseDraft(paths, {'system_info.lhm_dll_path':'../unsafe'}).errors['system_info.lhm_dll_path']);
});

test('empty input follows API defaults and optional inheritance; reset to baseline clears dirty state', () => {
  const config = parseConfig(payload());
  assert.deepEqual(analyseDraft(config, {...makeDraft(config), 'sampling.hz':''}).changes, []);
  assert.deepEqual(analyseDraft(config, {...makeDraft(config), 'sampling.optional':''}).changes, []);
  assert.equal(analyseDraft(config, {...makeDraft(config), 'sampling.hz':'4'}).changes.length, 1);
  assert.equal(analyseDraft(config, makeDraft(config)).changes.length, 0);
});

test('save acknowledgement requires all submitted keys and validates server classification lists', () => {
  const saved = {status:'ok', applied:['sampling.hz'], applied_live:['sampling.hz'], needs_restart:['overlay.session_tape_dir']};
  assert.deepEqual(parseSave(saved, ['sampling.hz']), saved);
  assert.throws(() => parseSave({...saved, applied:[]}, ['sampling.hz']));
  assert.throws(() => parseSave({...saved, applied_live:[{}]}, ['sampling.hz']));
  assert.throws(() => parseSave({...saved, status:'failed'}, ['sampling.hz']));
});

test('explicit reread keeps edits, picks up unrelated changes and clears already persisted changes', () => {
  const previous = parseConfig(payload());
  const draft = {...makeDraft(previous), 'sampling.hz':'4'};
  const current = parseConfig({...payload(), overlay:{...payload().overlay, 'overlay.enabled':false}});
  const reconciled = reconcileDraft(previous, draft, current);
  assert.equal(reconciled['overlay.enabled'], false);
  assert.deepEqual(analyseDraft(current, reconciled).values, {'sampling.hz':4});
  const persisted = parseConfig({...payload(), overlay:{...payload().overlay, 'sampling.hz':4}});
  assert.equal(analyseDraft(persisted, reconcileDraft(previous, draft, persisted)).changes.length, 0);
  const changedSchema = parseConfig({...payload(), schema:payload().schema.slice(1)});
  assert.throws(() => reconcileDraft(previous, draft, changedSchema));
});

test('PUT uses CSRF header and only provided changed values', async () => {
  let captured: RequestInit | undefined;
  const mockFetch = async (url: string, options: RequestInit) => {
    assert.equal(url, '/api/config'); captured = options;
    return new Response(JSON.stringify({status:'ok',applied:['sampling.hz'],applied_live:['sampling.hz'],needs_restart:[]}));
  };
  await requestConfig('PUT', new AbortController().signal, {'sampling.hz':3}, mockFetch);
  assert.equal(captured?.method, 'PUT');
  assert.deepEqual(captured?.headers, {'Content-Type':'application/json','X-Requested-With':'irswitch'});
  assert.deepEqual(JSON.parse(captured!.body as string), {values:{'sampling.hz':3}});
});

test('rejected PUT is distinct from uncertain network or server failure', async () => {
  for (const status of [400,403,500]) {
    await assert.rejects(requestConfig('PUT', new AbortController().signal, {'sampling.hz':3}, async () => new Response(JSON.stringify({error:'rejected'}), {status})),
      error => error instanceof ConfigRequestError && error.uncertain === (status !== 403));
  }
  await assert.rejects(requestConfig('PUT', new AbortController().signal, {}, async () => {throw new Error('offline');}),
    error => error instanceof ConfigRequestError && error.uncertain);
});

test('timeout aborts in-flight requests without treating save as confirmed failure', async () => {
  let aborted = false;
  await assert.rejects(requestConfig('PUT', new AbortController().signal, {}, async (_url, options) => new Promise((_resolve,reject) => {
    options.signal!.addEventListener('abort', () => {aborted=true;reject(new Error('aborted'));});
  }), 5), error => error instanceof ConfigRequestError && error.uncertain);
  assert.equal(aborted,true);
});
