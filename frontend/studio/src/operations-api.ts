export type JsonObject = Record<string, unknown>;
export function parseObject(value: unknown): JsonObject {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Neplatná odpověď API.');
  return value as JsonObject;
}
export function overrideBody(scene: string, seconds: string) {
  const duration=Number(seconds);
  if (!scene.trim() || !Number.isSafeInteger(duration) || duration<=0) throw new Error('Vyplňte scénu a kladný celý počet sekund.');
  return {scene:scene.trim(),seconds:duration};
}
export function speakBody(text: string) {
  const normalized=text.trim().replace(/\s+/g,' ');
  if (!normalized || normalized.length>400 || /[\x00-\x1f]/.test(normalized)) throw new Error('Text musí mít 1–400 znaků.');
  return {schemaVersion:'commentary-runtime/2',language:'en',text:normalized};
}
type Fetcher=(url:string,options:RequestInit)=>Promise<Response>;
export async function readAction(url:string,signal:AbortSignal,timeout=8000):Promise<JsonObject>{
  const controller=new AbortController();const abort=()=>controller.abort();
  signal.addEventListener('abort',abort,{once:true});if(signal.aborted)abort();
  const timer=setTimeout(abort,timeout);
  try {
    if(controller.signal.aborted)throw new Error('Přerušeno.');
    return await Promise.race([
      new Promise<never>((_,reject)=>controller.signal.addEventListener('abort',()=>reject(new Error('Vypršel čas API.')),{once:true})),
      (async()=>{const response=await fetch(url,{signal:controller.signal,cache:'no-store'});if(!response.ok)throw new Error(`API HTTP ${response.status}`);return parseObject(await response.json());})(),
    ]);
  }finally{clearTimeout(timer);signal.removeEventListener('abort',abort);}
}
export async function postAction(url:string,body:unknown,signal:AbortSignal,fetcher:Fetcher=fetch,timeout=8000):Promise<JsonObject>{
  const controller=new AbortController();const abort=()=>controller.abort();
  signal.addEventListener('abort',abort,{once:true});if(signal.aborted) abort();
  const timer=setTimeout(abort,timeout);
  try {
    if(controller.signal.aborted) throw new Error('Přerušeno.');
    return await Promise.race([new Promise<never>((_resolve,reject)=>controller.signal.addEventListener('abort',()=>reject(new Error('Čas akce vypršel; výsledek není potvrzen.')),{once:true})),(async()=>{
      const response=await fetcher(url,{method:'POST',headers:{'Content-Type':'application/json','X-Requested-With':'irswitch'},body:JSON.stringify(body),signal:controller.signal});
      const data=parseObject(await response.json());
      if(!response.ok) {
        const error=data.error;
        throw new Error(typeof error==='string'?error:error&&typeof error==='object'&&'code' in error?String(error.code):`HTTP ${response.status}`);
      }
      return data;
    })()]);
  } finally {clearTimeout(timer);signal.removeEventListener('abort',abort);}
}
