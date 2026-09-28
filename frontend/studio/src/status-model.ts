import type {ComponentStatus} from './poll.ts';

export type Signal = {tone: 'good' | 'warn' | 'bad' | 'off' | 'unknown'; label: string};
export function connectionSignal(value: boolean | undefined, stale: boolean): Signal {
  if (stale || value === undefined) return {tone:'unknown',label:'Neznámý stav'};
  return value ? {tone:'good',label:'Připojeno'} : {tone:'bad',label:'Odpojeno'};
}
export function iracingSignal(connected:boolean|undefined, uiRunning:boolean|null|undefined, stale:boolean):Signal {
  if(!stale && connected===false && uiRunning===true)return {tone:'warn',label:'iRacing UI'};
  return connectionSignal(connected,stale);
}
export function componentSignal(row: ComponentStatus | undefined, stale: boolean): Signal {
  if (stale || !row) return {tone:'unknown',label:'Neznámý stav'};
  if (row.enabled === false || row.status === 'disabled') return {tone:'off',label:'Vypnuto'};
  if (row.detail?.stale === true || row.status === 'stale') return {tone:'warn',label:'Neaktuální'};
  const status = row.status;
  if (!status) return {tone:'unknown',label:'Jen konfigurace'};
  const bad: Record<string,string> = {disconnected:'Odpojeno',error:'Chyba',unreachable:'Nedostupné'};
  if (Object.hasOwn(bad,status)) return {tone:'bad',label:bad[status]};
  if (status === 'not_required') return {tone:'off',label:'Není vyžadováno'};
  if (row.available === false) return {tone:'warn',label:'Nedostupné'};
  const warn: Record<string,string> = {connecting:'Připojování',reconnecting:'Obnova spojení',degraded:'Omezený provoz',reachable_empty:'Bez senzorů'};
  if (Object.hasOwn(warn,status)) return {tone:'warn',label:warn[status]};
  const good: Record<string,string> = {connected:'Připojeno',sampling:'Měření běží',running:'Běží',speaking:'Mluví',ready:'Připraveno',recording:'Záznam běží'};
  if (Object.hasOwn(good,status)) return {tone:'good',label:good[status]};
  if (status === 'idle') return {tone:'off',label:'Neaktivní'};
  return {tone:'unknown',label:status};
}
