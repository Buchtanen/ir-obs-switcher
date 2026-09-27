import { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { parseStatus, parseActivity, readJson, startPolling } from './poll';
import type { Snapshot, Status, Activity } from './poll';
import { Settings } from './Settings';
import { Replay } from './Replay';
import { Definitions } from './Definitions';
import { Catalog, Episodes } from './Catalog';
import { Operations } from './Operations';
import './style.css';
import {socketInvalidations} from './socket';
import {StatusBoard, StatusSignal} from './StatusBoard';
import {connectionSignal} from './status-model';

const pages = [
  ['overview', 'Přehled'], ['events', 'Eventy'], ['scenarios', 'Scénáře'], ['episodes', 'Epizody'], ['replay', 'Replay'],
  ['overlay', 'Overlay'], ['commentary', 'Komentář'], ['obs', 'OBS scény'], ['diagnostics', 'Diagnostika'], ['settings', 'Nastavení'],
] as const;
type Page = typeof pages[number][0];
function route(): Page {
  const id = location.hash.replace(/^#\/?/, '').split('?')[0];
  return pages.find(([key]) => key === id)?.[0] ?? 'overview';
}
function useApi<T>(url: string, parse: (v: unknown) => T) {
  const [state, setState] = useState<Snapshot<T>>({stale: false});
  useEffect(() => startPolling(signal => readJson(url, signal, parse), setState,3000,5000,socketInvalidations('/ws')), [url, parse]);
  return state;
}
function Freshness({state}: {state: Snapshot<unknown>}) {
  return <div className={state.stale ? 'notice warning' : 'notice'} role="status">
    {state.stale ? `Data nejsou aktuální · ${state.error}` : state.updatedAt ? 'Aktuální odpověď API' : 'Načítání API…'}
    {state.updatedAt && <span>Poslední úspěch {new Date(state.updatedAt).toLocaleTimeString('cs-CZ')}</span>}
  </div>;
}
function ActivityList({state}: {state: Snapshot<Activity>}) {
  return <section className="panel"><h2>Poslední události</h2><Freshness state={state}/>
    {state.data?.items.length ? <ul className="activity">{state.data.items.map((item, index) => <li key={`${item.dedupeKey}:${index}`}>
      <time>{new Date(item.occurredAt * 1000).toLocaleTimeString('cs-CZ')}</time><div><small>{item.source} · {item.kind}</small><p>{item.message}</p></div>
    </li>)}</ul> : <p className="muted">{state.data ? 'API nevrátilo žádné události.' : 'Historie zatím není dostupná.'}</p>}
  </section>;
}
function App() {
  const [page, setPage] = useState<Page>(route);
  const [dirtySettings, setDirtySettings] = useState(0);
  const status = useApi('/api/admin/status', parseStatus);
  const activity = useApi('/api/admin/activity?limit=30', parseActivity);
  useEffect(() => { const update = () => setPage(route()); window.addEventListener('hashchange', update); return () => window.removeEventListener('hashchange', update); }, []);
  const sw = status.data?.runtime.switcher ? status.data.switcher : null;
  const unknown = status.stale || !status.data;
  const connected = (key: 'connected_obs' | 'connected_iracing') => connectionSignal(sw?.[key], unknown);
  return <div className="studio"><a className="skip" href="#main" onClick={event => { event.preventDefault(); document.getElementById('main')?.focus(); }}>Přejít na obsah</a><aside>
    <a className="brand" href="#/overview"><span className="logo">ir</span><span>irswitch <b>Studio</b></span></a>
    <p className="nav-label">PRACOVNÍ PROSTOR</p><nav aria-label="Hlavní navigace">{pages.map(([id, label]) => <a key={id} href={`#/${id}`} aria-current={page === id ? 'page' : undefined}><span className="nav-dot"/>{label}{id === 'settings' && dirtySettings > 0 && <span className="draft-badge" aria-label={`${dirtySettings} neuložených změn`}>{dirtySettings}</span>}</a>)}</nav>
    <div className="sidebar-foot">LOKÁLNÍ STUDIO<small>Pozorování provozu</small><a href="/admin">Současná administrace ↗</a></div>
  </aside><div className="workspace"><header><span className="pill">{page === 'replay' ? 'IZOLOVANÝ REPLAY' : page === 'scenarios' ? 'DEFINICE' : 'ŽIVÝ PŘEHLED'}</span><div className="connections"><span>OBS <StatusSignal signal={connected('connected_obs')}/></span><span>iRacing <StatusSignal signal={connected('connected_iracing')}/></span></div></header>
    <main id="main" tabIndex={-1}><div className="page-title"><div><p className="eyebrow">IRSWITCH / STUDIO</p><h1>{pages.find(([id]) => id === page)?.[1]}</h1></div><span className="version">Engine {status.data?.version ?? '—'}</span></div>
      {(page === 'overview' || page === 'diagnostics') && <><Freshness state={status}/><StatusBoard state={status}/><div className="columns"><ActivityList state={activity}/><div>
        <section className="panel"><h2>Stav switcheru</h2><dl><dt>Režim</dt><dd>{sw?.mode ?? '—'}</dd><dt>Session</dt><dd>{sw?.session_type ?? '—'}</dd><dt>Důvod rozhodnutí</dt><dd>{sw?.reason ?? '—'}</dd></dl><a className="button" href="/gr-status">Ovládání switcheru ↗</a></section>

      </div></div></>}
      <Replay active={page === 'replay'}/><Catalog page={page}/><Definitions active={page === 'scenarios'}/><Episodes active={page === 'episodes'}/><Operations page={page}/>
      <Settings active={page === 'settings'} onDirtyChange={setDirtySettings}/>
    </main><footer>Zdroj: {page === 'settings' ? '/api/config' : '/api/admin/status · /api/admin/activity'} <span>Studio</span></footer>
  </div></div>;
}

createRoot(document.getElementById('root')!).render(<App/>);
