import type {ComponentStatus, Snapshot, Status} from './poll';
import {componentSignal, connectionSignal, iracingSignal} from './status-model';
import type {Signal} from './status-model';
import {JsonDetails} from './Operations';
import './status-board.css';
import {companionSignal,readinessSignal} from './companion-model';

export function StatusSignal({signal}:{signal:Signal}) {
  return <span className={`status-signal signal-${signal.tone}`}><i className="status-light" aria-hidden="true"/>{signal.label}</span>;
}
const value = (v:unknown, suffix='') => typeof v === 'number' && Number.isFinite(v) ? `${Math.round(v*10)/10}${suffix}` : typeof v === 'string' && v ? v : '—';
function facts(key:string,row:ComponentStatus):[string,string][] {
  const d=row.detail??{};
  switch(key) {
    case 'ble':return [['Tep',value(d.bpm,' bpm')],['Zdroj',value(d.source)]];
    case 'lhm':return [['Senzory',value(d.sensorRows)],['Využití',row.required===true?'CPU telemetrie':row.required===false?'Volitelné':'—']];
    case 'sysinfo':return [['CPU',value(d.cpuLoad,' %')],['GPU',value(d.gpuLoad,' %')],['Teplota CPU',value(d.cpuTemp,' °C')],['Teplota GPU',value(d.gpuTemp,' °C')]];
    case 'overlay':return [['Widgety',value(row.activeWidgets)],['Režim',value(row.mode)],['Vzhled',value(row.theme)]];
    case 'commentary':return [['Runtime',row.available===true?'Dostupný':row.available===false?'Nedostupný':'—'],['Řeč',row.busy===true?'Právě mluví':row.busy===false?'Bez řeči':'—']];
    case 'tape':return [['Zápis',row.active===true?'Aktivní':row.active===false?'Neaktivní':'—'],['Provider',row.available===true?'Dostupný':row.available===false?'Nedostupný':'—']];
    case 'eventEngine':return [['Zapnuté volby',`${Object.values(row).filter(v=>v===true).length}`],['Údaj','Konfigurace, ne aktivita']];
    default:return [['Provider',row.available===true?'Dostupný':row.available===false?'Nedostupný':'—']];
  }
}
const labels:Record<string,string>={ble:'Tepová frekvence',lhm:'Hardware monitor',sysinfo:'Systémová telemetrie',overlay:'Overlay',commentary:'Komentář',tape:'Záznam událostí',eventEngine:'Event engine'};
export function StatusBoard({state}:{state:Snapshot<Status>}) {
  const data=state.data, stale=state.stale||!data;
  const sw=data?.runtime.switcher?data.switcher:null;
  const api:Signal=stale?{tone:'unknown',label:'Bez čerstvých dat'}:data?.runtime.switcher?{tone:'good',label:'Runtime dostupný'}:{tone:'warn',label:'Runtime není připojen'};
  const auto:Signal=stale||!sw?{tone:'unknown',label:'Neznámý stav'}:sw.autoswitch?{tone:'good',label:'Zapnuta'}:{tone:'off',label:'Vypnuta'};
  const uiWaiting=!stale&&sw?.connected_iracing===false&&data?.iracingUi?.running===true;
  const components=Object.entries({...data?.extensions,...data?.features});
  return <>
    <div className="status-cards">
      <section className="status-card"><div className="card-heading"><h2>OBS Studio</h2><StatusSignal signal={connectionSignal(sw?.connected_obs,stale)}/></div><strong className="card-value">{value(sw?.current_scene)}</strong><span className="card-caption">Aktuální scéna{stale?' · poslední známá':''}</span><div className="card-bottom"><span>Cílová scéna</span><b>{value(sw?.target_scene)}</b></div></section>
      <section className="status-card"><div className="card-heading"><h2>iRacing</h2><StatusSignal signal={iracingSignal(sw?.connected_iracing,data?.iracingUi?.running,stale)}/></div><strong className="card-value">{uiWaiting?'iRacing UI':sw?.session_type||'Bez session'}</strong><span className="card-caption">{stale?'Čekám na čerstvá data':uiWaiting?'Čeká na session simulátoru':sw?.connected_iracing===false?'Čekám na simulátor':'Aktuální session'}</span><div className="card-bottom"><span>Stav řízení</span><b>{value(sw?.mode)}</b></div></section>
      <section className="status-card"><div className="card-heading"><h2>Automatika</h2><StatusSignal signal={auto}/></div><strong className="card-value">{stale||!sw?'—':sw.autoswitch?'Automatické scény':'Ruční režim'}</strong><span className="card-caption">Řízení přepínání scén</span><div className="card-bottom"><span>Důvod</span><b>{value(sw?.reason)}</b></div></section>
      <section className="status-card"><div className="card-heading"><h2>Služba a API</h2><StatusSignal signal={api}/></div><strong className="card-value">{stale?'Nedostupná data':data?.runtime.switcher?'Runtime běží':'Pouze API'}</strong><span className="card-caption">Engine {data?.version??'—'}</span><div className="card-bottom"><span>Poslední odpověď</span><b>{state.updatedAt?new Date(state.updatedAt).toLocaleTimeString('cs-CZ'):'—'}</b></div></section>
    </div>
    <section className="components-panel companion-panel" aria-label="Připravenost doprovodných aplikací">
      <div className="section-heading"><h2>Doprovodné aplikace</h2><a href="#/settings?search=companion_apps">Nastavit požadované aplikace</a></div>
      <div className="readiness-summary" role="status"><StatusSignal signal={readinessSignal(data?.companionApps,stale)}/></div>
      <p className="muted companion-note">Kontrola spuštění aplikací. Připojení zařízení, účtů a VR ani funkčnost aplikací tím není ověřena.</p>
      <div className="component-grid">{data?.companionApps?.map(row=><article key={row.id} className="component-card"><div className="card-heading"><h3>{row.label}</h3><StatusSignal signal={companionSignal(row,stale)}/></div><span className="card-caption">{row.required?'Požadovaná pro připravenost':'Volitelná'}{stale?' · poslední známé nastavení':''}</span></article>)}</div>
    </section>
    <section className="components-panel" aria-label="Stav komponent"><div className="section-heading"><h2>Komponenty</h2><p>{state.stale?'Poslední známé údaje · aktuální stav není dostupný':'Stav z běžící služby'}</p></div>
      <div className="component-grid">{components.map(([key,row])=><article key={key} className="component-card"><div className="card-heading"><h3>{Object.hasOwn(labels,key)?labels[key]:row.label??key}</h3><StatusSignal signal={componentSignal(row,stale)}/></div><dl className="component-facts">{facts(key,row).map(([label,v])=><div key={label}><dt>{label}</dt><dd>{v}</dd></div>)}</dl></article>)}</div>
      {!components.length&&<p className="muted">Čekám na stavové API komponent.</p>}
      <div className="signal-legend" aria-label="Význam stavových diod">{([{tone:'good',label:'V provozu'},{tone:'warn',label:'Čeká / omezeno'},{tone:'bad',label:'Chyba / odpojeno'},{tone:'off',label:'Vypnuto / neaktivní'},{tone:'unknown',label:'Neznámé'}] as Signal[]).map(s=><StatusSignal key={s.tone} signal={s}/>)}</div>
      <JsonDetails title="Připravenost, parametry modulů a důvody" value={data}/>
    </section>
  </>;
}
