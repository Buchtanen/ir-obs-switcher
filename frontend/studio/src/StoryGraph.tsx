import {useEffect,useRef,useState} from 'react';
import {edgeCurve,tracePaths} from './graph-model';
import type {GraphEdge,Position} from './graph-model';

type Beat={id:string;role:string};
const fallback=(i:number):Position=>({x:40+(i%4)*285,y:50+Math.floor(i/4)*125});
export function StoryGraph({beats,edges,catalogHash,selected,onSelect}:{beats:Beat[];edges:(GraphEdge&{guard_profile_id:string})[];catalogHash:string;selected:string;onSelect:(id:string)=>void}) {
  const key=`studio-layout:v2:${catalogHash}`,svg=useRef<SVGSVGElement>(null);
  const [positions,setPositions]=useState<Record<string,Position>>(()=>{
    try{const value=JSON.parse(localStorage.getItem(key)||'{}');return value&&typeof value==='object'&&!Array.isArray(value)?value:{};}catch{return {};}
  });
  const [view,setView]=useState({zoom:1,x:0,y:0});
  const drag=useRef<{id:string;start:Position;origin:Position;moved:boolean}|null>(null);
  const dragged=useRef(false);
  const point=(id:string)=>{
    const p=positions[id];
    return p&&Number.isFinite(p.x)&&Number.isFinite(p.y)?p:fallback(beats.findIndex(b=>b.id===id));
  };
  const ids=new Set(beats.map(b=>b.id));
  const links=edges.filter(e=>ids.has(e.from_beat_id)&&ids.has(e.to_beat_id));
  const path=tracePaths(selected,ids,links);
  const fit=(onlyPath:boolean,reset=false)=>{
    const nodes=beats.filter(b=>!onlyPath||path.nodes.has(b.id));
    if(!nodes.length)return;
    const points=nodes.map(b=>reset?fallback(beats.findIndex(n=>n.id===b.id)):point(b.id));
    const minX=Math.min(...points.map(p=>p.x))-45,minY=Math.min(...points.map(p=>p.y))-55;
    const width=Math.max(...points.map(p=>p.x))+260-minX,height=Math.max(...points.map(p=>p.y))+115-minY;
    const zoom=Math.min(1.5,1100/width,640/height);
    setView({zoom,x:(1100-width*zoom)/2-minX*zoom,y:(640-height*zoom)/2-minY*zoom});
  };
  // Polls produce new arrays; only a changed selection/catalog membership resets the viewport.
  const membership=JSON.stringify(beats.map(b=>b.id));
  useEffect(()=>{fit(Boolean(selected));},[selected,membership,catalogHash]);
  useEffect(()=>{try{localStorage.setItem(key,JSON.stringify(positions));}catch{/* optional local layout */}},[key,positions]);
  const cursor=(e:React.PointerEvent)=>{
    const matrix=svg.current!.getScreenCTM();
    if(!matrix)return {x:0,y:0};
    const p=new DOMPoint(e.clientX,e.clientY).matrixTransform(matrix.inverse());
    return {x:p.x,y:p.y};
  };
  const zoomBy=(factor:number)=>setView(v=>{
    const zoom=Math.max(.05,Math.min(3,v.zoom*factor)),ratio=zoom/v.zoom;
    return {zoom,x:550-(550-v.x)*ratio,y:320-(320-v.y)*ratio};
  });
  const endDrag=()=>{dragged.current=drag.current?.moved??false;drag.current=null;};
  return <div className="graph-section">
    <div className="action-buttons graph-tools"><button className="button" onClick={()=>zoomBy(1.25)}>Přiblížit</button><button className="button" onClick={()=>zoomBy(.8)}>Oddálit</button><button className="button" onClick={()=>fit(false)}>Celý graf</button><button className="button" disabled={!selected} onClick={()=>fit(true)}>Přiblížit cestu</button><button className="button" disabled={!selected} onClick={()=>onSelect('')}>Zrušit výběr</button><button className="button" onClick={()=>{setPositions({});fit(Boolean(selected),true);}}>Obnovit rozložení</button></div>
    <p className="graph-summary" role="status">{selected?<><b>{selected}</b> · {path.nodes.size} uzlů · {path.links.size} návazností ve vybrané cestě</>:'Vyberte uzel nebo položku v seznamu pro zvýraznění celé možné cesty.'}</p>
    <div className="graph-legend"><span className="legend-selected">Vybraný beat</span><span className="legend-before">Předchůdci</span><span className="legend-after">Pokračování →</span><span>Možné vazby · podmínky se zde nevyhodnocují</span></div>
    <svg ref={svg} className="story-graph" viewBox="0 0 1100 640" aria-label="Graf návazností beatů" onPointerDown={e=>{if(e.target===e.currentTarget){dragged.current=false;drag.current={id:'',start:cursor(e),origin:{x:view.x,y:view.y},moved:false};e.currentTarget.setPointerCapture(e.pointerId);}}} onPointerMove={e=>{
      const d=drag.current;if(!d)return;
      const p=cursor(e),dx=p.x-d.start.x,dy=p.y-d.start.y;
      if(Math.abs(dx)+Math.abs(dy)<4&&!d.moved)return;
      d.moved=true;
      if(d.id)setPositions(old=>({...old,[d.id]:{x:d.origin.x+dx/view.zoom,y:d.origin.y+dy/view.zoom}}));
      else setView(v=>({...v,x:d.origin.x+dx,y:d.origin.y+dy}));
    }} onPointerUp={endDrag} onPointerCancel={endDrag}>
      <defs>{['base','before','after'].map(kind=><marker key={kind} id={`story-arrow-${kind}`} viewBox="0 0 12 12" refX="11" refY="6" markerWidth="12" markerHeight="12" markerUnits="userSpaceOnUse" orient="auto"><path d="M 1 1 L 11 6 L 1 11 z" className={`arrow-${kind}`}/></marker>)}</defs>
      <g transform={`translate(${view.x},${view.y}) scale(${view.zoom})`}>
        {links.map(e=>{
          const highlighted=path.links.has(e.id),kind=highlighted?(path.after.has(e.from_beat_id)&&path.after.has(e.to_beat_id)?'after':'before'):'base';
          return <path key={e.id} data-edge={e.id} data-highlighted={highlighted} className={`graph-edge edge-${kind}${selected&&!highlighted?' graph-muted':''}`} d={edgeCurve(point(e.from_beat_id),point(e.to_beat_id))} markerEnd={`url(#story-arrow-${kind})`}><title>{e.from_beat_id} → {e.to_beat_id} · {e.guard_profile_id}</title></path>;
        })}
        {beats.map(b=>{
          const p=point(b.id),kind=b.id===selected?'selected':path.after.has(b.id)?'after':path.before.has(b.id)?'before':'base';
          return <g key={b.id} role="button" tabIndex={0} aria-label={b.id} aria-pressed={b.id===selected} data-node={b.id} data-highlighted={path.nodes.has(b.id)} className={`graph-node node-${kind}${selected&&!path.nodes.has(b.id)?' graph-muted':''}`} transform={`translate(${p.x},${p.y})`} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();onSelect(b.id);}}} onPointerDown={e=>{e.stopPropagation();dragged.current=false;drag.current={id:b.id,start:cursor(e),origin:p,moved:false};e.currentTarget.setPointerCapture(e.pointerId);}} onClick={()=>{if(!dragged.current)onSelect(b.id);dragged.current=false;}}>
            <rect width="215" height="60" rx="8"/><text x="10" y="25" fontSize="12">{b.id}</text><text className="node-role" x="10" y="45" fontSize="11">{b.role}</text><title>{b.id} · {b.role}</title>
          </g>;
        })}
      </g>
    </svg>
  </div>;
}
