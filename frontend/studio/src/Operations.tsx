import {useEffect,useRef,useState} from 'react';
import {parseObject,postAction,readAction,overrideBody,speakBody} from './operations-api';
import type {JsonObject} from './operations-api';
import {readJson,startPolling} from './poll';
import type {Snapshot} from './poll';
import example from './validate-example.json';
import './operations.css';
import {socketInvalidations} from './socket';

export function useRead(url:string,active=true,revision=0) {
  const [state,setState]=useState<Snapshot<JsonObject>>({stale:false});
  useEffect(()=>{if(!active)return;return startPolling(signal=>readJson(url,signal,parseObject),setState,3000,5000,url==='/status'?socketInvalidations('/ws'):url==='/api/overlay/snapshot'?socketInvalidations('/ws/overlay'):undefined);},[url,active,revision]);
  return state;
}
export function JsonDetails({title,value,open=false}:{title:string;value:unknown;open?:boolean}) {
  return <details className="panel json-detail" open={open}><summary>{title}</summary><pre>{value===undefined?'Nedostupné':JSON.stringify(value,null,2)}</pre></details>;
}
export function ReadNotice({state}:{state:Snapshot<unknown>}){
  return <div role="status" className={`notice ${state.stale?'warning':''}`}>{state.stale?`Poslední data nejsou aktuální: ${state.error}`:state.updatedAt?`Poslední načtení ${new Date(state.updatedAt).toLocaleTimeString('cs-CZ')}`:'Načítání…'}</div>;
}
const text=(value:unknown)=>typeof value==='string'||typeof value==='number'?String(value):typeof value==='boolean'?(value?'Ano':'Ne'):'—';

export function Operations({page}:{page:string}){
  const obs=page==='obs',commentary=page==='commentary',overlay=page==='overlay',diagnostics=page==='diagnostics';
  const [revision,setRevision]=useState(0);
  const status=useRead('/status',obs||diagnostics,revision);
  const runtime=useRead('/api/commentary/runtime',commentary,revision);
  const decisions=useRead('/api/commentary/runtime/decisions?limit=50',commentary,revision);
  const events=useRead('/api/events',diagnostics,revision);
  const metrics=useRead('/metrics',diagnostics,revision);
  const health=useRead('/health',diagnostics,revision);
  const logLevel=useRead('/logging/level',diagnostics,revision);
  const oauth=useRead('/oauth/status',obs,revision);
  const snapshot=useRead('/api/overlay/snapshot',overlay,revision);
  const debug=useRead('/api/overlay/debug/events',overlay,revision);
  const [busy,setBusy]=useState(false),[blocked,setBlocked]=useState(false),[message,setMessage]=useState('');
  const [result,setResult]=useState<unknown>();
  const flight=useRef<AbortController|null>(null);
  const [scene,setScene]=useState(''),[seconds,setSeconds]=useState('120');
  const [speech,setSpeech]=useState(example.text),[bindings,setBindings]=useState(JSON.stringify(example,null,2));
  const [voices,setVoices]=useState<SpeechSynthesisVoice[]>([]),[voice,setVoice]=useState(''),[rate,setRate]=useState('1'),[language,setLanguage]=useState('en-US');
  const [authUrl,setAuthUrl]=useState('');
  const [demo,setDemo]=useState(true),[theme,setTheme]=useState('cyber_racing'),[renderer,setRenderer]=useState('v4'),[previewRun,setPreviewRun]=useState(0);
  useEffect(()=>()=>{flight.current?.abort();window.speechSynthesis?.cancel();},[]);
  useEffect(()=>{
    const synth=window.speechSynthesis;if(!synth)return;
    const update=()=>setVoices(synth.getVoices());update();synth.addEventListener('voiceschanged',update);
    return()=>synth.removeEventListener('voiceschanged',update);
  },[]);
  async function act(url:string,body:unknown={},confirm?:string){
    if(flight.current||blocked||(confirm&&!window.confirm(confirm)))return;
    const controller=new AbortController();flight.current=controller;setBusy(true);setMessage('Provádění akce…');
    try {const value=await postAction(url,body,controller.signal);if(controller.signal.aborted)return;setResult(value);setMessage('Server přijal akci. Aktuální stav se znovu načítá.');setRevision(n=>n+1);}
    catch(error){if(!controller.signal.aborted){setBlocked(true);setMessage(`Akci neopakuji automaticky: ${error instanceof Error?error.message:'Chyba API'}`);}}
    finally {if(!controller.signal.aborted)setBusy(false);if(flight.current===controller)flight.current=null;}
  }
  function guarded(action:()=>void){try{action();}catch(error){setMessage(error instanceof Error?error.message:'Neplatný vstup.');}}
  async function check(){
    if(flight.current)return;
    const controller=new AbortController();flight.current=controller;setBusy(true);
    try{const path=commentary?'/api/commentary/runtime/decisions?limit=50':overlay?'/api/overlay/snapshot':'/status';
      const value=await readAction(path,controller.signal);if(controller.signal.aborted)return;setResult(value);setRevision(n=>n+1);
      setMessage('Načtený stav zkontrolujte. Není to potvrzení výsledku předchozí akce.');
      // Explicit acknowledgement is required for non-idempotent actions after a timeout.
      if(window.confirm('Stav byl načten. Výsledek předchozí akce nemusí být zjistitelný. Povolit další ručně spuštěné akce?'))setBlocked(false);
    }catch(error){if(!controller.signal.aborted)setMessage(String(error));}finally{if(flight.current===controller)flight.current=null;if(!controller.signal.aborted)setBusy(false);}
  }
  async function authorize(){
    if(flight.current||blocked)return;const controller=new AbortController();flight.current=controller;setBusy(true);
    try{const value=await readAction('/oauth/initiate',controller.signal);if(controller.signal.aborted)return;const url=new URL(String(value.authorization_url));
      if(url.protocol!=='https:'||url.hostname!=='accounts.google.com')throw new Error('Neočekávaná autorizační adresa.');setAuthUrl(url.href);
    }catch(error){if(!controller.signal.aborted)setMessage(String(error));}finally{if(flight.current===controller)flight.current=null;if(!controller.signal.aborted)setBusy(false);}
  }
  if(!obs&&!commentary&&!overlay&&!diagnostics)return null;
  const disabled=busy||blocked;
  const current=status.data;
  return <div className="operations">
    {message&&<div className={`notice ${blocked?'warning':''}`} role="status">{message}</div>}
    {blocked&&<button className="button" disabled={busy} onClick={()=>void check()}>Ověřit stav před další akcí</button>}
    {result!==undefined&&<JsonDetails title="Výsledek poslední akce / ověření" value={result}/>}
    {obs&&<><ReadNotice state={status}/><section className="panel"><h2>OBS a automatika</h2><dl>{[['Scéna','current_scene'],['Cílová scéna','target_scene'],['Režim','mode'],['Důvod','reason'],['Automatika','autoswitch'],['Ruční scéna','override_scene'],['OBS připojeno','connected_obs'],['iRacing připojeno','connected_iracing'],['Vysílání','streaming'],['Profil OBS','obs_profile'],['Název vysílání','stream_title'],['Session','session_name']].map(([label,key])=><div key={key}><dt>{label}</dt><dd>{status.stale?'Neznámý stav':text(current?.[key])}</dd></div>)}</dl>
      <div className="action-buttons"><button className="button" disabled={disabled||status.stale||!current} onClick={()=>void act('/autoswitch/toggle')}>Přepnout automatiku</button><button className="button" disabled={disabled||status.stale||!current} onClick={()=>void act('/restart-mode/reset')}>Zrušit režim RESTART</button><button className="button" disabled={disabled||status.stale||current?.connected_obs!==true} onClick={()=>void act('/stream/reinit')}>Obnovit informace vysílání</button></div>
      <fieldset disabled={disabled||status.stale||!current}><legend>Ruční přepnutí scény</legend><label>Název scény<input value={scene} onChange={e=>setScene(e.target.value)}/></label><label>Doba přepnutí (s)<input inputMode="numeric" value={seconds} onChange={e=>setSeconds(e.target.value)}/></label><button className="button" onClick={()=>guarded(()=>void act('/override',overrideBody(scene,seconds)))}>Použít ruční scénu</button></fieldset></section>
      <JsonDetails title="Úplný stav switcheru a vysílání" value={current}/><section className="panel"><h2>Autorizace YouTube</h2><ReadNotice state={oauth}/><p>Stav autorizace: {text(oauth.data?.authenticated)}</p><button className="button" disabled={disabled} onClick={()=>void authorize()}>Připravit autorizaci</button>{authUrl&&<a className="button" href={authUrl} target="_blank" rel="noreferrer">Otevřít autorizaci Google ↗</a>}<JsonDetails title="Stav OAuth" value={oauth.data}/></section></>}
    {diagnostics&&<><section className="panel"><h2>Správa služby</h2><p>Tyto akce mění běžící službu.</p><div className="action-buttons">{[['/config/reload','Načíst konfiguraci','Načíst konfiguraci a aplikovat změny za běhu?'],['/reset','Reset stavu','Resetovat stav a metriky služby a přepnout na bezpečnou scénu?'],['/restart','Restartovat službu','Restartovat službu? Připojení bude přerušeno.'],['/shutdown','Ukončit službu','Ukončit službu? Automatika přestane pracovat.']].map(([url,label,confirmation])=><button key={url} className="button" disabled={disabled} onClick={()=>void act(url,{},confirmation)}>{label}</button>)}<button className="button" disabled={disabled||logLevel.stale||!logLevel.data} onClick={()=>void act('/logging/level',{level:logLevel.data?.level==='DEBUG'?'INFO':'DEBUG'})}>Logování {text(logLevel.data?.level)} · přepnout</button></div></section><ReadNotice state={health}/><JsonDetails title="Zdraví služby" value={health.data}/><ReadNotice state={metrics}/><JsonDetails title="Metriky" value={metrics.data}/><ReadNotice state={events}/><JsonDetails title="Události switcheru" value={events.data}/><section className="panel"><h2>VR a diagnostické výstupy</h2><p>VR widget zůstává samostatný průhledný výstup pro RaceLab. Zdejší stav odpovídá stejnému API.</p><a href="/vr-status" target="_blank" rel="noreferrer">Otevřít VR widget ↗</a> · <a href="/overlay/golden" target="_blank" rel="noreferrer">Vizuální referenční testy ↗</a><JsonDetails title="Stav pro GR / VR" value={status.data}/></section></>}
    {commentary&&<><ReadNotice state={runtime}/><section className="panel"><h2>Provoz komentáře</h2><p>Runtime: {text(runtime.data?.status)} · jazyk EN</p><JsonDetails title="Runtime, komponenty, fronty a konfigurace" value={runtime.data} open/></section><section className="panel"><h2>Test řeči</h2><label>Anglický text<textarea value={speech} maxLength={400} onChange={e=>setSpeech(e.target.value)}/></label><div className="action-buttons"><button className="button" disabled={disabled||runtime.stale||decisions.stale||decisions.data?.runtime!==true} onClick={()=>guarded(()=>void act('/api/commentary/speak',speakBody(speech),'Odeslat testovací text do živého TTS?'))}>Přehrát přes službu</button><button className="button" disabled={!window.speechSynthesis} onClick={()=>guarded(()=>{const utterance=new SpeechSynthesisUtterance(speakBody(speech).text);utterance.lang=language;utterance.rate=Number(rate);utterance.voice=voices.find(v=>v.name===voice)??null;window.speechSynthesis.cancel();window.speechSynthesis.speak(utterance);})}>Test pouze v prohlížeči</button><button className="button" onClick={()=>window.speechSynthesis?.cancel()}>Zastavit hlas prohlížeče</button></div><label>Jazyk prohlížeče<select value={language} onChange={e=>setLanguage(e.target.value)}><option value="en-US">English</option><option value="cs-CZ">Čeština</option></select></label><label>Hlas prohlížeče<select value={voice} onChange={e=>setVoice(e.target.value)}><option value="">Výchozí hlas</option>{voices.map(v=><option key={`${v.name}:${v.lang}`} value={v.name}>{v.name} ({v.lang})</option>)}</select></label><label>Rychlost<input type="range" min="0.6" max="1.4" step="0.1" value={rate} onChange={e=>setRate(e.target.value)}/></label></section><section className="panel"><h2>Offline validace textu</h2><p>Ukázkové vazby jsou testovací data; validace nečte živý stav ani nespouští řeč. Lze vložit vlastní payload stejného kontraktu.</p><label>Vazby a beat (JSON)<textarea className="json-input" value={bindings} onChange={e=>setBindings(e.target.value)}/></label><button className="button" disabled={disabled} onClick={()=>guarded(()=>{const body=parseObject(JSON.parse(bindings));void act('/api/commentary/validate',{...body,text:speech});})}>Ověřit text s vazbami</button></section><ReadNotice state={decisions}/><JsonDetails title={decisions.data?.runtime===false?'Provider rozhodnutí není dostupný':'Poslední rozhodnutí'} value={decisions.data} open/></>}
    {overlay&&<><section className="panel"><h2>{demo?'Izolované demo vzhledu':'Živý náhled overlaye'}</h2><p>{demo?'Vykresluje ukázkové události pouze v tomto náhledu. Není to replay enginu.':'Čte živý overlay výstup; OBS používá stále /overlay/.'}</p><div className="action-buttons"><label><input type="checkbox" checked={demo} onChange={e=>setDemo(e.target.checked)}/> Demo vzhledu</label><label>Téma<select value={theme} onChange={e=>setTheme(e.target.value)}>{['cyber_racing','stealth_graphite','night_attack','pit_wall_dark','pit_wall_light'].map(t=><option key={t}>{t}</option>)}</select></label><label>Renderer (výchozí může být V4)<select value={renderer} onChange={e=>setRenderer(e.target.value)}><option value="v4">V4</option><option value="legacy">Podle konfigurace služby</option></select></label><button className="button" onClick={()=>setPreviewRun(n=>n+1)}>Obnovit náhled</button></div><OverlayFrame key={previewRun} title="Náhled overlaye" src={demo?`/overlay?demo=1&theme=${encodeURIComponent(theme)}${renderer==='v4'?'&renderer=v4':''}`:'/overlay/'}/><a href="/overlay/" target="_blank" rel="noreferrer">OBS výstup ↗</a></section><ReadNotice state={snapshot}/><JsonDetails title="Živý snapshot" value={snapshot.data}/><section className="panel"><h2>Testovací událost do živého overlaye</h2><p>Tato akce publikuje do stejného výstupu, který odebírá OBS.</p><div className="action-buttons">{Array.isArray(debug.data?.events)&&debug.data.events.filter((v):v is string=>typeof v==='string').map(name=><button key={name} className="button" disabled={disabled} onClick={()=>void act('/overlay/debug/emit',{name},`Odeslat ${name} do živého overlaye?`)}>{name}</button>)}</div></section></>}
  </div>;
}

function OverlayFrame({src,title}:{src:string;title:string}){
  const frame=useRef<HTMLDivElement>(null);const [scale,setScale]=useState(1);const [cue,setCue]=useState('');
  useEffect(()=>{const receive=(event:MessageEvent)=>{if(event.origin===location.origin&&event.source===frame.current?.querySelector('iframe')?.contentWindow&&event.data?.type==='overlay-demo-cue'&&typeof event.data.label==='string')setCue(event.data.label);};window.addEventListener('message',receive);return()=>window.removeEventListener('message',receive);},[]);
  useEffect(()=>{const node=frame.current;if(!node)return;const resize=new ResizeObserver(()=>setScale(node.clientWidth/1920));resize.observe(node);return()=>resize.disconnect();},[]);
  return <><p aria-live="polite">{cue}</p><div ref={frame} className="overlay-frame"><iframe title={title} src={src} style={{width:1920,height:1080,transform:`scale(${scale})`,transformOrigin:'top left'}}/></div></>;
}
