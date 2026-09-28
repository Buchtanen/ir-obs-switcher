import type {CompanionApp} from './poll';
import type {Signal} from './status-model';
const ids=['dre','maira','simhub','cammus','trading_paints','virtual_desktop'];
export function companionSignal(row:CompanionApp,stale:boolean):Signal {
  if(stale||row.running===null)return {tone:'unknown',label:'Neznámý stav'};
  return row.running?{tone:'good',label:'Běží'}:row.required?{tone:'warn',label:'Chybí'}:{tone:'off',label:'Neběží · volitelná'};
}
export function readinessSignal(rows:CompanionApp[]|undefined,stale:boolean):Signal {
  if(stale||!rows||ids.some(id=>!rows.some(r=>r.id===id)))return {tone:'unknown',label:'Připravenost nelze ověřit'};
  const required=rows.filter(r=>r.required);
  if(!required.length)return {tone:'off',label:'Žádné požadované aplikace'};
  const missing=required.filter(r=>r.running===false);
  if(missing.length)return {tone:'warn',label:`Chybí ${missing.length} z ${required.length} požadovaných aplikací`};
  if(required.some(r=>r.running===null))return {tone:'unknown',label:'Připravenost nelze ověřit'};
  return {tone:'good',label:`Všech ${required.length} požadovaných aplikací běží`};
}
