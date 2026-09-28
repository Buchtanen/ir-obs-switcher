export type Snapshot<T> = {data?: T; stale: boolean; error?: string; updatedAt?: number};
export type ComponentStatus = {label?: string; status?: string; available?: boolean; enabled?: boolean; active?: boolean; busy?: boolean; detail?: Record<string, unknown>; [key: string]: unknown};
export type CompanionApp = {id:string;label:string;running:boolean|null;required:boolean};
export type Status = {
  schemaVersion: 1; version: string; runtime: {overlay: boolean; switcher: boolean};
  companionApps?: CompanionApp[];
  iracingUi?: {running: boolean | null};
  switcher: null | {connected_obs: boolean; connected_iracing: boolean; autoswitch: boolean;
    mode?: string; current_scene?: string; target_scene?: string; reason?: string; session_type?: string};
  extensions?: Record<string, ComponentStatus>;
  features?: Record<string, ComponentStatus>;
};
export type Activity = {schemaVersion: 1; items: {dedupeKey: string; occurredAt: number; source: string; kind: string; message: string}[]};

const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);

export function parseStatus(v: unknown): Status {
  if (!object(v) || v.schemaVersion !== 1 || typeof v.version !== 'string' || !object(v.runtime)
    || typeof v.runtime.overlay !== 'boolean' || typeof v.runtime.switcher !== 'boolean'
    || !(v.switcher === null || (object(v.switcher) && ['connected_obs', 'connected_iracing', 'autoswitch'].every(k => typeof v.switcher === 'object' && v.switcher !== null && typeof (v.switcher as Record<string, unknown>)[k] === 'boolean')))) {
    throw new Error('Neplatná odpověď stavového API');
  }
  if (object(v.switcher) && ['mode', 'current_scene', 'target_scene', 'reason', 'session_type'].some(key =>
    v.switcher !== null && object(v.switcher) && v.switcher[key] != null && typeof v.switcher[key] !== 'string')) {
    throw new Error('Neplatná odpověď stavového API');
  }
  if(v.companionApps !== undefined && (!Array.isArray(v.companionApps) ||
    !v.companionApps.every(row=>object(row)&&typeof row.id==='string'&&typeof row.label==='string'&&
      typeof row.required==='boolean'&&(row.running===null||typeof row.running==='boolean')) ||
    new Set(v.companionApps.map(row=>row.id)).size!==v.companionApps.length)) {
    throw new Error('Neplatná odpověď doprovodných aplikací');
  }
  // Optional feature maps must remain safe to render even with a partial provider.
  if (v.iracingUi !== undefined && (!object(v.iracingUi) ||
    !(v.iracingUi.running === null || typeof v.iracingUi.running === 'boolean'))) {
    throw new Error('Neplatná odpověď stavu iRacing UI');
  }
  for (const key of ['extensions', 'features']) {
    if (v[key] !== undefined && (!object(v[key]) || !Object.values(v[key]).every(row => object(row)
      && ['label', 'status'].every(field => row[field] == null || typeof row[field] === 'string')))) {
      throw new Error('Neplatná odpověď stavového API');
    }
  }
  return v as Status;
}

export function parseActivity(v: unknown): Activity {
  if (!object(v) || v.schemaVersion !== 1 || !Array.isArray(v.items) || !v.items.every(row => object(row)
    && ['dedupeKey', 'source', 'kind', 'message'].every(key => typeof row[key] === 'string')
    && typeof row.occurredAt === 'number' && Number.isFinite(row.occurredAt))) {
    throw new Error('Neplatná odpověď historie API');
  }
  return v as Activity;
}

export function connectionLabel(connected: boolean | undefined, stale: boolean): string {
  return stale || connected === undefined ? 'Neznámý stav' : connected ? 'Připojeno' : 'Odpojeno';
}

export async function readJson<T>(url: string, signal: AbortSignal, parse: (data: unknown) => T): Promise<T> {
  const response = await fetch(url, {signal, cache: 'no-store'});
  if (!response.ok) throw new Error(`API HTTP ${response.status}`);
  return parse(await response.json());
}

export function startPolling<T>(read: (signal: AbortSignal) => Promise<T>, publish: (state: Snapshot<T>) => void,
  interval = 3000, timeout = 5000, subscribe?: (invalidate:()=>void)=>()=>void): () => void {
  let stopped = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let controller: AbortController;
  let state: Snapshot<T> = {stale: false};
  let inFlight = false;
  let invalidated = false;
  async function refresh() {
    if(stopped||inFlight)return;
    inFlight=true;
    invalidated=false;
    controller = new AbortController();
    let deadline: ReturnType<typeof setTimeout> | undefined;
    try {
      const data = await Promise.race([read(controller.signal), new Promise<never>((_resolve, reject) => {
        deadline = setTimeout(() => { controller.abort(); reject(new Error('Vypršel čas API')); }, timeout);
      })]);
      state = {data, stale: false, updatedAt: Date.now()};
    } catch (error) {
      state = {...state, stale: true, error: error instanceof Error ? error.message : 'API není dostupné'};
    } finally { clearTimeout(deadline); inFlight=false; }
    if (!stopped) { publish(state); timer = setTimeout(refresh, invalidated ? 0 : interval); }
  }
  void refresh();
  const unsubscribe=subscribe?.(()=>{if(stopped)return;if(inFlight){invalidated=true;return;}clearTimeout(timer);void refresh();});
  return () => { stopped = true; unsubscribe?.(); clearTimeout(timer); controller.abort(); };
}
