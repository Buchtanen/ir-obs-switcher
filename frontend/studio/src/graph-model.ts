export type GraphEdge = {id:string; from_beat_id:string; to_beat_id:string};

/** All catalog routes leading to or continuing from the selected beat, not sibling routes. */
export function tracePaths(selected:string, nodeIds:Iterable<string>, edges:GraphEdge[]) {
  const allowed=new Set(nodeIds);
  const visible=edges.filter(e=>allowed.has(e.from_beat_id)&&allowed.has(e.to_beat_id));
  const walk=(reverse:boolean)=>{
    const found=new Set<string>();
    if(!allowed.has(selected))return found;
    const adjacency=new Map<string,string[]>();
    for(const edge of visible){
      const from=reverse?edge.to_beat_id:edge.from_beat_id;
      const to=reverse?edge.from_beat_id:edge.to_beat_id;
      adjacency.set(from,[...(adjacency.get(from)??[]),to]);
    }
    const pending=[selected];
    while(pending.length){
      const id=pending.pop()!;
      if(found.has(id))continue;
      found.add(id);
      pending.push(...(adjacency.get(id)??[]));
    }
    return found;
  };
  const before=walk(true),after=walk(false);
  const nodes=new Set([...before,...after]);
  const links=new Set(visible.filter(e=>
    (before.has(e.from_beat_id)&&before.has(e.to_beat_id))||
    (after.has(e.from_beat_id)&&after.has(e.to_beat_id))).map(e=>e.id));
  return {nodes,links,before,after};
}

export type Position={x:number;y:number};
export function edgeCurve(a:Position,b:Position):string {
  if(a.x===b.x&&a.y===b.y)return `M ${a.x+175} ${a.y} C ${a.x+275} ${a.y-65}, ${a.x+285} ${a.y+75}, ${a.x+224} ${a.y+40}`;
  // Route long links through the gaps in the default grid, not through intervening nodes.
  if(Math.abs(b.x-a.x)>230&&Math.abs(b.y-a.y)>5){
    const forward=b.x>a.x,startX=a.x+(forward?215:0),exitX=startX+(forward?30:-30);
    const entryX=b.x+(forward?-30:245),endX=b.x+(forward?-9:224);
    const laneY=a.y+(b.y>a.y?90:-30);
    return `M ${startX} ${a.y+30} L ${exitX} ${a.y+30} L ${exitX} ${laneY} L ${entryX} ${laneY} L ${entryX} ${b.y+30} L ${endX} ${b.y+30}`;
  }
  if(Math.abs(b.x-a.x)>300&&Math.abs(b.y-a.y)<=5){
    return `M ${a.x+107.5} ${a.y} L ${a.x+107.5} ${a.y-30} L ${b.x+107.5} ${a.y-30} L ${b.x+107.5} ${b.y-9}`;
  }
  if(Math.abs(b.x-a.x)<=230&&Math.abs(b.y-a.y)>140){
    return `M ${a.x+215} ${a.y+30} L ${a.x+245} ${a.y+30} L ${a.x+245} ${b.y+30} L ${b.x+224} ${b.y+30}`;
  }
  if(Math.abs(b.x-a.x)>230){
    const forward=b.x>a.x, start={x:a.x+(forward?215:0),y:a.y+30};
    const end={x:b.x+(forward?-9:224),y:b.y+30},bend=Math.max(45,Math.abs(end.x-start.x)*.45);
    return `M ${start.x} ${start.y} C ${start.x+(forward?bend:-bend)} ${start.y}, ${end.x+(forward?-bend:bend)} ${end.y}, ${end.x} ${end.y}`;
  }
  const down=b.y>a.y,start={x:a.x+107.5,y:a.y+(down?60:0)},end={x:b.x+107.5,y:b.y+(down?-9:69)};
  const bend=Math.max(32,Math.abs(end.y-start.y)*.45);
  return `M ${start.x} ${start.y} C ${start.x} ${start.y+(down?bend:-bend)}, ${end.x} ${end.y+(down?-bend:bend)}, ${end.x} ${end.y}`;
}
