import {test} from 'node:test';
import assert from 'node:assert/strict';
import {tracePaths,edgeCurve} from './graph-model.ts';
const edge=(from:string,to:string)=>({id:`${from}-${to}`,from_beat_id:from,to_beat_id:to});
test('selection includes every incoming and outgoing branch without unrelated siblings',()=>{
  const edges=[edge('a','b'),edge('a','sibling'),edge('z','b'),edge('b','c'),edge('b','d'),edge('c','e'),edge('d','e'),edge('other','c')];
  const path=tracePaths('b',['a','z','b','c','d','e','sibling','other'],edges);
  assert.deepEqual([...path.nodes].sort(),['a','b','c','d','e','z']);
  assert.equal(path.links.size,6);
  assert.ok(!path.links.has('a-sibling')&&!path.links.has('other-c'));
});
test('cycles terminate, parallel links remain and story boundaries stop traversal',()=>{
  const edges=[edge('a','b'),edge('b','c'),edge('c','a'),edge('c','outside'),{...edge('a','b'),id:'parallel'}];
  const path=tracePaths('b',['a','b','c'],edges);
  assert.equal(path.nodes.size,3);
  assert.equal(path.links.size,4);
  assert.ok(!path.nodes.has('outside'));
});
test('isolated selection is retained and absent selection highlights nothing',()=>{
  assert.deepEqual([...tracePaths('solo',['solo'],[]).nodes],['solo']);
  assert.equal(tracePaths('missing',['solo'],[]).nodes.size,0);
});
test('directional curves end outside target boxes including backwards and self links',()=>{
  assert.match(edgeCurve({x:0,y:0},{x:300,y:0}),/291 30$/);
  assert.match(edgeCurve({x:300,y:0},{x:0,y:0}),/224 30$/);
  assert.match(edgeCurve({x:0,y:0},{x:0,y:100}),/107.5 91$/);
  assert.match(edgeCurve({x:0,y:100},{x:0,y:0}),/107.5 69$/);
  assert.match(edgeCurve({x:0,y:0},{x:0,y:0}),/224 40$/);
  assert.equal(edgeCurve({x:855,y:0},{x:0,y:125}),'M 855 30 L 825 30 L 825 90 L 245 90 L 245 155 L 224 155');
});
