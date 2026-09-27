export type Value = string | number | boolean | null;
export type Field = {
  key: string; type: 'str' | 'int' | 'float' | 'bool'; default: Value;
  live: boolean; section: string; help: string; min: number | null; max: number | null;
  optional: boolean; choices: string[] | null; secret: boolean;
};
export type Config = {schema: Field[]; values: Record<string, Value>};
export type Draft = Record<string, string | boolean | null>;
export type SaveResult = {status: 'ok'; applied: string[]; applied_live: string[]; needs_restart: string[]};
export type Change = {field: Field; before: Value; after: Value; error?: string};
const object = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value);
const strings = (value: unknown): value is string[] => Array.isArray(value) && value.every(v => typeof v === 'string');
const nullableNumber = (value: unknown) => value === null || (typeof value === 'number' && Number.isFinite(value));

function matches(field: Field, value: unknown): value is Value {
  if (value === null) return field.optional;
  if (field.type === 'str') return typeof value === 'string';
  if (field.type === 'bool') return typeof value === 'boolean';
  return typeof value === 'number' && Number.isFinite(value) && (field.type !== 'int' || Number.isSafeInteger(value));
}

export function parseConfig(data: unknown): Config {
  if (!object(data) || !Array.isArray(data.schema) || !data.schema.length || !object(data.overlay)) {
    throw new Error('Konfigurační API vrátilo neplatné schéma.');
  }
  const schema: Field[] = [];
  const entries: [string, Value][] = [];
  const seen = new Set<string>();
  for (const raw of data.schema) {
    if (!object(raw) || typeof raw.secret !== 'boolean') throw new Error('Neplatný popis pole.');
    if (raw.secret) continue; // Secret data never enters editor state, drafts or summaries.
    if (typeof raw.key !== 'string' || !raw.key || seen.has(raw.key)
      || !['str', 'int', 'float', 'bool'].includes(String(raw.type))
      || typeof raw.live !== 'boolean' || typeof raw.optional !== 'boolean'
      || typeof raw.section !== 'string' || typeof raw.help !== 'string'
      || !nullableNumber(raw.min) || !nullableNumber(raw.max)
      || (typeof raw.min === 'number' && typeof raw.max === 'number' && raw.min > raw.max)
      || !(raw.choices === null || (strings(raw.choices) && raw.choices.length > 0 && raw.type === 'str'))) {
      throw new Error('Neplatný popis pole.');
    }
    const field = raw as Field;
    if (!matches(field, field.default) || !Object.hasOwn(data.overlay, field.key) || !matches(field, data.overlay[field.key])) {
      throw new Error(`Konfigurace neobsahuje platnou hodnotu pro ${field.key}.`);
    }
    seen.add(field.key);
    schema.push(field);
    entries.push([field.key, data.overlay[field.key] as Value]);
  }
  if (!schema.length) throw new Error('Schéma neobsahuje upravitelná pole.');
  return {schema, values: Object.fromEntries(entries)};
}

export const draftValue = (value: Value): string | boolean | null => typeof value === 'number' ? String(value) : value;
export function makeDraft(config: Config): Draft {
  return Object.fromEntries(config.schema.map(field => [field.key, draftValue(config.values[field.key])]));
}

function normalize(field: Field, raw: Draft[string]): Value {
  if (raw === null || raw === '') return field.optional ? null : field.default;
  if (field.type === 'bool') {
    if (typeof raw !== 'boolean') throw new Error('Zvolte zapnuto nebo vypnuto.');
    return raw;
  }
  if (field.type === 'int' || field.type === 'float') {
    if (typeof raw !== 'string' || !/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(raw.trim())) throw new Error('Zadejte platné číslo.');
    const number = Number(raw);
    if (!Number.isFinite(number)) throw new Error('Zadejte konečné číslo.');
    if (field.type === 'int' && !Number.isSafeInteger(number)) throw new Error('Zadejte celé číslo.');
    if (field.min !== null && number < field.min) throw new Error(`Minimum je ${field.min}.`);
    if (field.max !== null && number > field.max) throw new Error(`Maximum je ${field.max}.`);
    return number;
  }
  if (typeof raw !== 'string') throw new Error('Zadejte text.');
  const text = raw.trim();
  if (field.choices && !field.choices.includes(text)) throw new Error('Vyberte hodnotu ze seznamu.');
  if ((field.key.endsWith('lhm_dll_path') || field.key.endsWith('theme')) && text.replaceAll('\\', '/').split('/').includes('..')) {
    throw new Error('Cesta nesmí obsahovat nadřazenou složku (..).');
  }
  return text;
}

export function analyseDraft(config: Config, draft: Draft) {
  const changes: Change[] = [];
  const errors: Record<string, string> = {};
  const entries: [string, Value][] = [];
  for (const field of config.schema) {
    const before = config.values[field.key];
    const raw = draft[field.key];
    if (raw === draftValue(before)) continue;
    try {
      const after = normalize(field, raw);
      if (after !== before) { changes.push({field, before, after}); entries.push([field.key, after]); }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Neplatná hodnota.';
      errors[field.key] = message;
      changes.push({field, before, after: raw, error: message});
    }
  }
  return {changes, errors, values: Object.fromEntries(entries)};
}

export function reconcileDraft(previous: Config, draft: Draft, current: Config): Draft {
  const next = makeDraft(current);
  for (const {field} of analyseDraft(previous, draft).changes) {
    const updated = current.schema.find(item => item.key === field.key);
    if (!updated || updated.type !== field.type) throw new Error('Schéma se změnilo. Rozepsané změny zůstávají zachovány; před pokračováním je zkontrolujte.');
    next[field.key] = draft[field.key];
  }
  return next;
}

export function parseSave(data: unknown, submitted: string[]): SaveResult {
  if (!object(data) || data.status !== 'ok' || !strings(data.applied) || !strings(data.applied_live) || !strings(data.needs_restart)
    || data.applied.length !== submitted.length || !submitted.every(key => (data.applied as string[]).includes(key))) {
    throw new Error('Server nepotvrdil všechny odeslané změny.');
  }
  return data as SaveResult;
}

export class ConfigRequestError extends Error {
  uncertain: boolean;
  constructor(message: string, uncertain: boolean) { super(message); this.uncertain = uncertain; }
}
type Fetcher = (url: string, options: RequestInit) => Promise<Response>;

export async function requestConfig(method: 'GET' | 'PUT', signal: AbortSignal, values?: Record<string, Value>, fetcher: Fetcher = fetch, timeout = 8000): Promise<unknown> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  signal.addEventListener('abort', abort, {once: true});
  if (signal.aborted) abort();
  const timer = setTimeout(abort, timeout);
  try {
    if (controller.signal.aborted) throw new Error('Požadavek byl přerušen.');
    const aborted = new Promise<never>((_resolve, reject) => controller.signal.addEventListener('abort', () => reject(new Error('Požadavek byl přerušen nebo vypršel jeho čas.')), {once: true}));
    return await Promise.race([aborted, (async () => {
      const response = await fetcher('/api/config', {method, signal: controller.signal, cache: 'no-store',
        ...(method === 'PUT' ? {headers: {'Content-Type':'application/json','X-Requested-With':'irswitch'}, body: JSON.stringify({values})} : {})});
      const data: unknown = await response.json();
      // The legacy API may return 400 while reloading after the INI was written.
      // Only its CSRF/locality rejection is guaranteed to precede any mutation.
      if (!response.ok) throw new ConfigRequestError(object(data) && typeof data.error === 'string' ? data.error : `API HTTP ${response.status}`, method === 'PUT' && response.status !== 403);
      return data;
    })()]);
  } catch (error) {
    if (error instanceof ConfigRequestError) throw error;
    throw new ConfigRequestError(error instanceof Error ? error.message : 'Konfigurační API není dostupné.', method === 'PUT');
  } finally { clearTimeout(timer); signal.removeEventListener('abort', abort); }
}
