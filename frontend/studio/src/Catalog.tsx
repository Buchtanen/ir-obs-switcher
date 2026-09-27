import {useEffect,useState} from 'react';
import {JsonDetails,ReadNotice,useRead} from './Operations';
import './catalog.css';
import {StoryGraph} from './StoryGraph';
import {tracePaths} from './graph-model';

type Beat={id:string;group:string;role:string;story_routes:string[];triggers:{id:string;kind:string}[];[key:string]:unknown};
type Story={id:string;open_beat_ids:string[];update_beat_ids:string[];close_beat_ids:string[];[key:string]:unknown};
type Edge={id:string;from_beat_id:string;to_beat_id:string;guard_profile_id:string;[key:string]:unknown};
type CatalogData={schemaVersion:string;narrative:{catalog_hash:string;beats:Beat[];stories:Story[];edges:Edge[];event_routes:{event_id:string;beat_ids:string[];story_routes:string[]}[]};events:Record<string,unknown>[];overlay:Record<string,unknown>;guards:unknown[]};

export function Catalog({page}:{page:string}){
 const active=page==='events'||page==='scenarios';const state=useRead('/api/studio/catalog',active);
 const [query,setQuery]=useState(''),[story,setStory]=useState(''),[selected,setSelected]=useState('');
 if(!active)return null;
 const data=state.data as unknown as CatalogData|undefined;
 if(!data||data.schemaVersion!=='studio-catalog/1'||!Array.isArray(data.narrative?.beats))return <><ReadNotice state={state}/><p>Katalog není dostupný.</p></>;
 const scoped=data.narrative.beats.filter(b=>!story||b.story_routes.includes(story));
 const matches=scoped.filter(b=>JSON.stringify(b).toLowerCase().includes(query.toLowerCase()));
 const path=tracePaths(selected,scoped.map(b=>b.id),data.narrative.edges);
 const beats=scoped.filter(b=>matches.some(m=>m.id===b.id)||path.nodes.has(b.id));
 const detail=data.narrative.beats.find(b=>b.id===selected);
 return <div className="catalog"><ReadNotice state={state}/><p>Autoritativní definice · {data.narrative.catalog_hash}. Graf neukazuje živou aktivitu.</p>
 <section className="panel"><div className="catalog-filters"><label>Hledat v katalogu<input value={query} onChange={e=>{setQuery(e.target.value);setSelected('');}}/></label><label>Story<select value={story} onChange={e=>{setStory(e.target.value);setSelected('');}}><option value="">Všechny</option>{data.narrative.stories.map(s=><option key={s.id}>{s.id}</option>)}</select></label></div>
 {page==='scenarios'&&<StoryGraph selected={selected} beats={beats} edges={data.narrative.edges} catalogHash={data.narrative.catalog_hash} onSelect={setSelected}/>}
 <h2>Beaty a návaznosti · {beats.length}</h2><p>Posouvání uzlů mění pouze rozložení v tomto prohlížeči. Seznam poskytuje stejné vazby bez grafu.</p>
 <ul className="catalog-list">{beats.map(b=><li key={b.id}><button className="button" aria-pressed={selected===b.id} onClick={()=>setSelected(b.id)}>{b.id}</button><span>{b.role} · {b.story_routes.join(', ')}</span><small>→ {data.narrative.edges.filter(e=>e.from_beat_id===b.id).map(e=>e.to_beat_id).join(', ')||'Bez následníka'}</small></li>)}</ul></section>
 {detail&&<section className="panel"><h2>{detail.id}</h2><p>Skupina {detail.group} · role {detail.role}</p><p>Triggery: {detail.triggers.map(t=>`${t.kind}: ${t.id}`).join(', ')}</p><a className="button" href={`#/settings?search=${encodeURIComponent(detail.group==='pit'?'pit':detail.group==='battle'?'battle':detail.group==='bio'?'heart_rate':detail.group==='session'?'event_engine':'events')}`}>Související parametry (FieldSpec)</a><p>Nastavení nabízí pouze parametry podporované stávajícím API. Interní podmínky a emitery jsou pouze evidované.</p><JsonDetails title="Definice beatu" value={detail} open/><JsonDetails title="Navazující hrany a guardy" value={data.narrative.edges.filter(e=>e.from_beat_id===detail.id||e.to_beat_id===detail.id)}/></section>}
 {story&&<JsonDetails title="Definice story" value={data.narrative.stories.find(s=>s.id===story)} open/>}
 {page==='events'&&<><JsonDetails title="Události a dispozice autoritativního registru" value={data.events.filter(e=>JSON.stringify(e).toLowerCase().includes(query.toLowerCase()))} open/><JsonDetails title="Event → beat → story" value={data.narrative.event_routes.filter(e=>JSON.stringify(e).toLowerCase().includes(query.toLowerCase()))}/><JsonDetails title="Samostatný katalog výstupu overlaye" value={data.overlay}/></>}
 <JsonDetails title="Registrované guard profily (pouze ke čtení)" value={data.guards}/></div>;
}

export function Episodes({active}:{active:boolean}){
 const [offset,setOffset]=useState(0),[selected,setSelected]=useState(''),[run,setRun]=useState<string|null>(null);
 const state=useRead(`/api/studio/episodes?limit=25&offset=${offset}`,active);const data=state.data;
 useEffect(()=>{if(typeof data?.runId==='string'&&data.runId!==run){setRun(data.runId);setOffset(0);setSelected('');}},[data,run]);
 if(!active)return null;
 const items=Array.isArray(data?.items)?data.items as Record<string,unknown>[]:[];
 const history=Array.isArray(data?.history)?data.history as {sequence:number;reason:string;previous_state:string|null;episode:Record<string,unknown>;source_refs:string[]}[]:[];
 const current=items.find(row=>row.episode_id===selected);
 return <div className="catalog"><ReadNotice state={state}/><p>{data?.available===false?'Provider epizod není dostupný.':!data?'Čekám na runtime.':`Běh ${data.runId} · ${data.total} uložených epizod`}</p>{data?.available===true&&<><p>Historie aktuální instance služby. Identita zahrnuje běh, occurrence a lineage; shodný název nespojuje epizody.</p>{data.historyComplete===false&&<p className="notice warning">Část historie již není uchována (omezená kapacita).</p>}<section className="panel"><ul className="catalog-list">{items.map(row=><li key={String(row.episode_id)}><button className="button" onClick={()=>setSelected(String(row.episode_id))}>{String(row.definition_id)} · {String(row.state)}</button><small>{String(row.episode_id)} · occurrence {String(row.occurrence_id??'stream')} · lineage {String(row.lineage_id??'—')}</small></li>)}</ul>{!items.length&&<p>V této části běhu nejsou epizody.</p>}<div className="action-buttons"><button className="button" disabled={offset===0} onClick={()=>{setOffset(n=>Math.max(0,n-25));setSelected('');}}>Předchozí</button><button className="button" disabled={offset+25>=Number(data.total)} onClick={()=>{setOffset(n=>n+25);setSelected('');}}>Další</button></div></section>{current&&<><JsonDetails title="Identita a stav epizody" value={current} open/><section className="panel"><h2>Zaznamenané přechody epizody</h2><ol>{history.filter(row=>row.episode.episode_id===selected).map(row=><li key={row.sequence}>{String(row.episode.updated_mono_ms)} ms · {row.previous_state??'—'} → {String(row.episode.state)} · {row.reason}<small> [{row.source_refs.join(', ')}]</small></li>)}</ol></section><JsonDetails title="Rozhodnutí se shodným episodeId" value={Array.isArray(data.decisions)?data.decisions.filter(row=>row&&typeof row==='object'&&(row as Record<string,unknown>).episodeId===selected):[]}/></>}</>}</div>;
}
