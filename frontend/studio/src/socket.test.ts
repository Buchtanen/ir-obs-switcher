import test from 'node:test';
import assert from 'node:assert/strict';
import {watchSocket} from './socket.ts';
import {startPolling} from './poll.ts';
const wait=(ms:number)=>new Promise(resolve=>setTimeout(resolve,ms));
test('socket reconnects, coalesces invalidations and owns cleanup',async()=>{
 const sockets:{onopen:(()=>void)|null;onmessage:(()=>void)|null;onclose:(()=>void)|null;onerror:(()=>void)|null;close:()=>void}[]=[];let invalidated=0,closed=0;
 const stop=watchSocket('ws://fixture',()=>invalidated++,()=>{const socket={onopen:null,onmessage:null,onclose:null,onerror:null,close:()=>{closed++;}};sockets.push(socket);return socket;},5,10);
 sockets[0].onmessage!();sockets[0].onmessage!();await wait(10);assert.equal(invalidated,1);
 sockets[0].onclose!();await wait(10);assert.equal(sockets.length,2);
 sockets[1].onmessage!();stop();await wait(15);assert.equal(invalidated,1);assert.equal(closed,1);assert.equal(sockets[1].onclose,null);
});
test('invalidation during a pending read queues once without aborting or overlap',async()=>{
 let invalidate=()=>{};let calls=0;let release:(v:number)=>void=()=>{};let cleaned=false;
 const stop=startPolling(()=>{calls++;return new Promise<number>(r=>{release=r;});},()=>{},1000,500,fn=>{invalidate=fn;return()=>{cleaned=true;};});
 invalidate();invalidate();assert.equal(calls,1);release(1);await wait(10);assert.equal(calls,2);stop();release(2);assert.equal(cleaned,true);
});
