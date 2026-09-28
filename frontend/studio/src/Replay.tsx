import {useEffect,useRef,useState} from 'react';
import {JsonDetails,ReadNotice,useRead} from './Operations';
import {postAction} from './operations-api';
import './catalog.css';

type Result={runId:string;fixture:string;outputHash:string;virtualDurationMs:number;outputs:{atMs:number;[key:string]:unknown}[];episodes?:unknown[];history?:{episode:{updated_mono_ms:number;[key:string]:unknown};[key:string]:unknown}[]};
export function Replay({active}:{active:boolean}){
 const state=useRead('/api/studio/replay',active);const [fixture,setFixture]=useState('narrative_world'),[document,setDocument]=useState('');
 const [result,setResult]=useState<Result>(),[busy,setBusy]=useState(false),[error,setError]=useState(''),[at,setAt]=useState(0),[playing,setPlaying]=useState(false);
 const request=useRef<AbortController|null>(null);
 const [reference,setReference]=useState<Result>();
 useEffect(()=>()=>request.current?.abort(),[]);
 useEffect(()=>{if(!active||!playing||!result)return;const timer=setInterval(()=>setAt(t=>{const next=Math.min(result.virtualDurationMs,t+100);if(next>=result.virtualDurationMs)setPlaying(false);return next;}),100);return()=>clearInterval(timer);},[active,playing,result]);
 async function run(){if(request.current)return;const controller=new AbortController();request.current=controller;setBusy(true);setError('');setPlaying(false);
  try{const value=await postAction('/api/studio/replay',{fixture,...(fixture==='narrative_world'&&document.trim()?{document:JSON.parse(document)}:{})},controller.signal);if(controller.signal.aborted)return;if(!Array.isArray(value.outputs)||typeof value.virtualDurationMs!=='number'||typeof value.runId!=='string')throw new Error('Neplatný výsledek replay.');setResult(value as unknown as Result);setAt(0);}
  catch(e){if(!controller.signal.aborted)setError(String(e));}finally{request.current=null;if(!controller.signal.aborted)setBusy(false);}
 }
 if(!active)return null;
 const firstDifference=reference&&result?Array.from({length:Math.max(reference.outputs.length,result.outputs.length)},(_,i)=>i).find(i=>JSON.stringify(reference.outputs[i])!==JSON.stringify(result.outputs[i])):undefined;
 const fixtures=Array.isArray(state.data?.fixtures)?state.data.fixtures as {id:string;name:string;domain:string}[]:[];
 return <section className="panel catalog"><h2>Izolovaný replay</h2><p>Každé spuštění vytváří nový runtime a virtuální čas z fixture. Výsledky neodesílá do OBS, živého overlaye ani TTS. Přehrávání časové osy pouze filtruje vypočtený výsledek.</p><ReadNotice state={state}/><label>Scénář<select value={fixture} disabled={busy} onChange={e=>setFixture(e.target.value)}>{fixtures.map(f=><option key={f.id} value={f.id}>{f.domain} · {f.name}</option>)}</select></label>
 {fixture==='narrative_world'&&<label>Volitelný koncept definic (JSON, prázdné = vestavěné)<textarea className="definition-json" value={document} disabled={busy} onChange={e=>setDocument(e.target.value)}/></label>}
 <button className="button" disabled={busy||!fixtures.length} onClick={()=>void run()}>{busy?'Výpočet…':'Spustit nový izolovaný běh'}</button>{error&&<p className="notice warning" role="alert">{error}</p>}
 {result&&<><p>Běh {result.runId} · otisk výstupu {result.outputHash}</p><label>Virtuální čas · {at} ms<input type="range" min="0" max={result.virtualDurationMs} step="1" value={at} onChange={e=>{setPlaying(false);setAt(Number(e.target.value));}}/></label><div className="action-buttons"><button className="button" onClick={()=>setPlaying(v=>!v)}>{playing?'Pozastavit':'Přehrát časovou osu'}</button><button className="button" onClick={()=>{setPlaying(false);setAt(0);}}>Na začátek</button><button className="button" onClick={()=>{setPlaying(false);setAt(result.virtualDurationMs);}}>Na konec</button><button className="button" onClick={()=>setReference(result)}>Připnout běh pro porovnání</button></div>
 <h3>Průchod zaznamenanými uzly</h3><p>Spojnice ukazují pořadí výstupů fixture, nikoli odvozené příčiny nebo uskutečněnou řeč. Výběr uzlu posune virtuální čas.</p>
 <ol className="replay-nodes">{result.outputs.map((row,index)=><li key={index}><button className="button" data-reached={row.atMs<=at} aria-label={`Uzel ${index+1}, ${row.atMs} ms`} onClick={()=>{setPlaying(false);setAt(row.atMs);}}><strong>{String(row.commandKind??row.eventType??'Výstup')}</strong><small>{row.atMs} ms · {String(row.disposition??row.phase??'')}</small></button></li>)}</ol>
 <JsonDetails title="Výstupy do zvoleného virtuálního času" value={result.outputs.filter(row=>row.atMs<=at)} open/>{result.episodes&&<><JsonDetails title="Epizody na konci izolovaného běhu" value={result.episodes}/><JsonDetails title="Zaznamenané přechody do zvoleného času" value={result.history?.filter(row=>row.episode.updated_mono_ms<=at)}/></>}
 {reference&&<section aria-label="Porovnání replay"><h3>Porovnání s připnutým během</h3><p>{reference.runId} · {reference.fixture}</p>{reference.fixture!==result.fixture?<p className="notice warning">Různé fixture: rozdíl není sám o sobě regresí definice.</p>:null}<p>{reference.outputHash===result.outputHash?'Shodný deterministický výstup.':'Výstupy běhů se liší.'}</p><p>Počet výstupů: {reference.outputs.length} → {result.outputs.length}. První odlišný výstup: {firstDifference===undefined?'žádný':firstDifference+1}.</p><JsonDetails title="Připnutý výsledek" value={{outputs:reference.outputs,episodes:reference.episodes,history:reference.history}}/><JsonDetails title="Aktuální výsledek" value={{outputs:result.outputs,episodes:result.episodes,history:result.history}}/><button className="button" onClick={()=>setReference(undefined)}>Zrušit porovnání</button></section>}
 </>}
 </section>;
}

