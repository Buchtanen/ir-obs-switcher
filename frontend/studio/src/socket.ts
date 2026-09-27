type Socket=Pick<WebSocket,'onopen'|'onmessage'|'onclose'|'onerror'|'close'>;
export function watchSocket(url:string,invalidate:()=>void,connect:(url:string)=>Socket=url=>new WebSocket(url),initial=1000,maximum=30000):()=>void{
 let stopped=false,socket:Socket|undefined,delay=initial;
 let retry:ReturnType<typeof setTimeout>|undefined,notification:ReturnType<typeof setTimeout>|undefined;
 function retryLater(){if(stopped||retry)return;retry=setTimeout(()=>{retry=undefined;open();},delay);delay=Math.min(maximum,delay*2);}
 function open(){if(stopped)return;try{const current=connect(url);socket=current;socket.onopen=()=>{delay=initial;};socket.onmessage=()=>{if(!notification)notification=setTimeout(()=>{notification=undefined;if(!stopped)invalidate();},initial);};socket.onclose=retryLater;socket.onerror=()=>current.close();}catch{retryLater();}}
 open();return()=>{stopped=true;clearTimeout(retry);clearTimeout(notification);if(socket){socket.onopen=null;socket.onclose=null;socket.onmessage=null;socket.onerror=null;socket.close();}};
}
export function socketInvalidations(path:string){return (invalidate:()=>void)=>watchSocket(`${location.protocol==='https:'?'wss:':'ws:'}//${location.host}${path}`,invalidate);}
