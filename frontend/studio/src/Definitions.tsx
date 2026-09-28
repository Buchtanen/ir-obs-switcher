import {useEffect,useRef,useState} from 'react';
import {parseObject,postAction,readAction} from './operations-api';
import {JsonDetails} from './Operations';
import './catalog.css';

type Story={id:string;open_beat_ids:string[];close_beat_ids:string[];update_beat_ids:string[];successor_edge_ids:string[];[key:string]:unknown};
type Document={schemaVersion:string;baseCatalogHash:string;stories:Story[];edges:{id:string;from_beat_id:string;to_beat_id:string}[]};
type Revision={id:string;document:Document};
type Store={savedRevision?:string;available:boolean;baseRevision:number;effectiveRevision:string;pendingRevision:string;builtin:Document;revisions:Revision[];runtime:{effectiveRevision:string;startupError:string|null}};
function safeDocument(value:unknown):Document|undefined{
 if(!value||typeof value!=='object')return;
 const d=value as Document;
 if(typeof d.schemaVersion!=='string'||typeof d.baseCatalogHash!=='string'||!Array.isArray(d.stories)||!Array.isArray(d.edges))return;
 if(!d.stories.every(s=>s&&typeof s==='object'&&typeof s.id==='string'&&['open_beat_ids','close_beat_ids','update_beat_ids','successor_edge_ids'].every(k=>Array.isArray(s[k])&&(s[k] as unknown[]).every(v=>typeof v==='string'))))return;
 if(!d.edges.every(e=>e&&typeof e==='object'&&typeof e.id==='string'&&typeof e.from_beat_id==='string'&&typeof e.to_beat_id==='string'))return;
 return d;
}
const pretty=(v:unknown)=>JSON.stringify(v,null,2);
export function Definitions({active}:{active:boolean}){
 const [store,setStore]=useState<Store>(),[draft,setDraft]=useState(''),[baseline,setBaseline]=useState(''),[revision,setRevision]=useState('builtin');
 const [message,setMessage]=useState(''),[busy,setBusy]=useState(false),[uncertain,setUncertain]=useState(false),[valid,setValid]=useState(false);
 const [undo,setUndo]=useState<string[]>([]),[redo,setRedo]=useState<string[]>([]),[newId,setNewId]=useState(''),[template,setTemplate]=useState('');
 const request=useRef<AbortController|null>(null),started=useRef(false);const dirty=draft!==baseline;
 useEffect(()=>{if(active&&!started.current){started.current=true;void load(false);}},[active]);
 useEffect(()=>()=>request.current?.abort(),[]);
 useEffect(()=>{if(!dirty&&!busy&&!uncertain)return;const warn=(e:BeforeUnloadEvent)=>{e.preventDefault();e.returnValue='';};window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn);},[dirty,busy,uncertain]);
 function edit(value:string){setUndo(u=>[...u.slice(-49),draft]);setRedo([]);setDraft(value);setValid(false);}
 async function load(preserve=true){
  if(request.current)return;const controller=new AbortController();request.current=controller;setBusy(true);
  try{const next=await readAction('/api/studio/definitions',controller.signal) as unknown as Store;if(controller.signal.aborted)return;
   if(!safeDocument(next.builtin)||!Array.isArray(next.revisions)||!next.revisions.every(r=>r&&typeof r.id==='string'&&safeDocument(r.document))||typeof next.baseRevision!=='number')throw new Error('Neplatný store revizí.');
   setStore(next);setUncertain(false);setValid(false);
   if(!preserve){const document=next.revisions.find(r=>r.id===next.pendingRevision)?.document??next.builtin;setDraft(pretty(document));setBaseline(pretty(document));setRevision(next.pendingRevision);}
   setMessage(preserve?'Revize znovu načteny. Koncept zůstal zachován; před dalším zápisem porovnejte změny.':'Definice načteny.');
  }catch(error){if(!controller.signal.aborted)setMessage(String(error));}finally{request.current=null;if(!controller.signal.aborted)setBusy(false);}
 }
 async function write(action:'validate'|'save'|'activate',body:unknown){
  if(request.current||uncertain)return;const controller=new AbortController();request.current=controller;setBusy(true);
  try{const next=await postAction(`/api/studio/definitions/${action}`,body,controller.signal);if(controller.signal.aborted)return;
   if(action==='validate'){setValid(true);setMessage('Validace prošla. Koncept lze uložit jako revizi.');}
   else{const saved=next as unknown as Store;setStore(saved);if(action==='save'){setBaseline(draft);setUndo([]);setRedo([]);setRevision(saved.savedRevision??saved.revisions.find(r=>pretty(r.document)===pretty(JSON.parse(draft)))?.id??saved.revisions.at(-1)?.id??'builtin');setMessage('Revize uložena. Pro příští spuštění ji aktivujte samostatně.');}else setMessage('Revize vybrána pro příští spuštění služby. Tento běh se nemění.');}
  }catch(error){if(!controller.signal.aborted){setValid(false);if(action!=='validate')setUncertain(true);setMessage(`${String(error)} · Koncept zůstal zachován.`);}}
  finally{request.current=null;if(!controller.signal.aborted)setBusy(false);}
 }
 function documentAction(action:'validate'|'save'){try{const document=parseObject(JSON.parse(draft));void write(action,action==='validate'?{document}:{document,baseRevision:store?.baseRevision});}catch(error){setMessage(`${String(error)} · Koncept zůstal zachován.`);}}
 function select(id:string){if(dirty&&!window.confirm('Zahodit neuložený koncept a načíst vybranou revizi?'))return;const document=id==='builtin'?store?.builtin:store?.revisions.find(r=>r.id===id)?.document;if(document){setRevision(id);setDraft(pretty(document));setBaseline(pretty(document));setValid(false);setUndo([]);setRedo([]);}}
 function addStory(){try{const doc=JSON.parse(draft) as Document;const source=doc.stories.find(s=>s.id===template)??doc.stories.find(s=>s.open_beat_ids.length&&s.close_beat_ids.length);if(!source)throw new Error('Vyberte šablonu s otevřením i uzavřením.');if(!/^[a-z][a-z0-9_.-]{0,63}$/.test(newId)||doc.stories.some(s=>s.id.toLowerCase()===newId.toLowerCase()))throw new Error('ID musí být nové, malé písmo, 1–64 znaků: a-z 0-9 _ . -');doc.stories.push({...source,id:newId});edit(pretty(doc));setNewId('');}catch(error){setMessage(String(error));}}
 function exportDraft(){const blob=new Blob([draft],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='studio-definitions.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
 if(!active)return null;
 let parsed:Document|undefined;try{parsed=safeDocument(JSON.parse(draft));}catch{/* editor retains invalid text */}
 const selectedDocument=revision==='builtin'?store?.builtin:store?.revisions.find(r=>r.id===revision)?.document;
 const changed=parsed&&selectedDocument?parsed.stories.filter(s=>pretty(s)!==pretty(selectedDocument.stories.find(x=>x.id===s.id))).map(s=>s.id):[];
 return <section className="panel catalog"><h2>Editor definic</h2><p>Nové story skládají registrované beaty. Upravit lze členství, certifikované návaznosti a ověřované parametry. Emitery, guardy a tvorba nových beatů zůstávají pouze ke čtení.</p><p>Účinná revize: {store?.runtime?.effectiveRevision??'—'} · pro příští spuštění: {store?.pendingRevision??'—'} · generace {store?.baseRevision??'—'}</p>{store?.runtime?.startupError&&<p className="notice warning">{store.runtime.startupError}</p>}
 {message&&<p className={`notice ${uncertain?'warning':''}`} role="status">{message}</p>}{store?.available===false&&<p>Trvalé úložiště není dostupné: tato instance nemá připojenou konfiguraci služby. Validace a export jsou dostupné.</p>}
 <div className="action-buttons"><button className="button" disabled={busy} onClick={()=>void load(!!store)}>Načíst aktuální revize</button><label>Revize<select value={revision} disabled={busy} onChange={e=>select(e.target.value)}><option value="builtin">Vestavěná</option>{store?.revisions.map(r=><option key={r.id} value={r.id}>{r.id}</option>)}</select></label><button className="button" disabled={busy||uncertain||!store?.available} onClick={()=>{if(window.confirm('Použít vybranou uloženou revizi při příštím spuštění služby?'))void write('activate',{revision,baseRevision:store?.baseRevision});}}>Aktivovat / vrátit revizi při příštím spuštění</button></div>
 {store&&<><fieldset disabled={busy||uncertain}><legend>Nová story ze známé struktury</legend><label>Nové ID<input value={newId} maxLength={64} onChange={e=>setNewId(e.target.value)}/></label><label>Šablona story<select value={template} onChange={e=>setTemplate(e.target.value)}><option value="">První platná struktura</option>{parsed?.stories?.filter(s=>s.open_beat_ids?.length&&s.close_beat_ids?.length).map(s=><option key={s.id}>{s.id}</option>)}</select></label><button className="button" onClick={addStory}>Přidat story do konceptu</button></fieldset>
 <label>Koncept definic (JSON)<textarea className="definition-json" spellCheck={false} value={draft} disabled={busy||uncertain} onChange={e=>edit(e.target.value)}/></label><div className="action-buttons"><button className="button" disabled={busy||uncertain||!undo.length} onClick={()=>{setRedo(r=>[...r,draft]);setDraft(undo.at(-1)!);setUndo(u=>u.slice(0,-1));setValid(false);}}>Zpět</button><button className="button" disabled={busy||uncertain||!redo.length} onClick={()=>{setUndo(u=>[...u,draft]);setDraft(redo.at(-1)!);setRedo(r=>r.slice(0,-1));setValid(false);}}>Znovu</button><button className="button" disabled={busy||uncertain} onClick={()=>documentAction('validate')}>Validovat koncept</button><button className="button" disabled={busy||uncertain||!valid||!dirty||!store.available} onClick={()=>documentAction('save')}>Uložit novou revizi</button><button className="button" onClick={exportDraft}>Export JSON</button><label>Import JSON<input type="file" accept="application/json,.json" disabled={busy||uncertain} onChange={async e=>{const file=e.target.files?.[0];if(!file)return;if(file.size>120000){setMessage('Soubor je příliš velký.');return;}if(dirty&&!window.confirm('Nahradit koncept importovaným souborem?'))return;edit(await file.text());setMessage('Import je pouze koncept. Před uložením jej validujte.');e.target.value='';}}/></label></div>
 <p>{dirty?'Neuložené změny':'Koncept odpovídá načtené revizi'} · změněné story: {changed.join(', ')||'—'}</p><JsonDetails title="Porovnání: původní a koncept" value={{before:selectedDocument,after:parsed??draft}}/>
 <p>Po odebrání hrany upravte také successor_edge_ids příslušných story. Validátor vyžaduje přesnou shodu a všechny odkazy. Rozložení grafu se sem neukládá.</p></>}
 </section>;
}
