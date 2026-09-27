import { useEffect, useRef, useState } from 'react';
import { analyseDraft, ConfigRequestError, draftValue, makeDraft, parseConfig, parseSave, reconcileDraft, requestConfig } from './settings-model';
import type { Config, Draft, Field, SaveResult, Value } from './settings-model';
import './settings.css';

const display = (value: Value) => value === null ? 'Výchozí / zděděná' : value === true ? 'Zapnuto' : value === false ? 'Vypnuto' : value === '' ? '(prázdné)' : String(value);
const sectionNames: Record<string, string> = {
  overlay: 'Overlay', event_engine: 'Události', race_observer: 'Sledování závodu',
  sampling: 'Vzorkování', 'sampling.race': 'Vzorkování závodu', 'sampling.system': 'Vzorkování systému', 'sampling.bio': 'Vzorkování tepu',
  'battle.hunting': 'Souboj · útok', 'battle.hunted': 'Souboj · obrana', 'battle.overtake': 'Předjíždění', battle: 'Souboje',
  heart_rate: 'Tepová frekvence', 'heart_rate.bluetooth': 'Snímač tepu', system_info: 'Systém',
  'system_info.cpu': 'Procesor', 'system_info.gpu': 'Grafická karta', 'system_info.memory': 'Paměť', events: 'Overlay události', 'events.priorities': 'Priority událostí',
};

function FieldInput({field, value, error, changed, onChange}: {field: Field; value: Draft[string]; error?: string; changed: boolean; onChange: (value: Draft[string]) => void}) {
  const id = `setting-${field.key}`;
  const common = {id, 'aria-describedby': `${id}-help${error ? ` ${id}-error` : ''}`, 'aria-invalid': !!error};
  const inherited = field.optional && value === null;
  return <div className={`setting-field${changed ? ' changed' : ''}`}>
    <div className="setting-title"><label htmlFor={id}>{field.key}</label><span className={field.live ? 'apply-live' : 'apply-restart'}>{field.live ? 'Za běhu' : 'Po restartu'}</span>{changed && <span className="changed-marker">Změněno</span>}</div>
    {field.optional && <label className="inherit"><input type="checkbox" checked={inherited} onChange={event => onChange(event.target.checked ? null : draftValue(field.default ?? (field.type === 'bool' ? false : field.type === 'str' ? field.choices?.[0] ?? '' : field.min ?? 0)))}/> Použít výchozí / zděděnou hodnotu</label>}
    {field.type === 'bool' ? <label className="toggle"><input {...common} type="checkbox" disabled={inherited} checked={value === true} onChange={event => onChange(event.target.checked)}/><span>{inherited ? 'Zděděno' : value ? 'Zapnuto' : 'Vypnuto'}</span></label>
      : field.choices ? <select {...common} disabled={inherited} value={value === null ? '' : String(value)} onChange={event => onChange(event.target.value)}>
        {(value === null || !field.choices.includes(String(value))) && <option value={value === null ? '' : String(value)}>{value === null ? 'Zděděno' : `Současná hodnota: ${value}`}</option>}
        {field.choices.map(choice => <option key={choice} value={choice}>{choice}</option>)}
      </select>
      : <input {...common} type="text" inputMode={field.type === 'str' ? 'text' : 'decimal'} disabled={inherited} value={value === null ? '' : String(value)} onChange={event => onChange(event.target.value)} autoComplete="off" spellCheck={false}/>}
    <div id={`${id}-help`} className="field-help">{field.help}<small>{field.min !== null && `Minimum: ${field.min}. `}{field.max !== null && `Maximum: ${field.max}. `}{field.type === 'int' && 'Celé číslo. '}{field.optional ? 'Prázdná hodnota se dědí.' : `Prázdná hodnota použije výchozí: ${display(field.default)}.`}</small></div>
    {error && <div id={`${id}-error`} className="field-error">{error}</div>}
  </div>;
}

export function Settings({active, onDirtyChange}: {active: boolean; onDirtyChange: (count: number) => void}) {
  const [config, setConfig] = useState<Config>();
  const [draft, setDraft] = useState<Draft>({});
  const [busy, setBusy] = useState<'load' | 'save' | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [uncertain, setUncertain] = useState(false);
  const [result, setResult] = useState<SaveResult>();
  const [restartKeys, setRestartKeys] = useState<string[]>([]);
  const [query, setQuery] = useState('');
  const [section, setSection] = useState('');
  const [changedOnly, setChangedOnly] = useState(false);
  const initialStarted = useRef(false);
  const request = useRef<AbortController | null>(null);
  const analysis = config ? analyseDraft(config, draft) : {changes: [], errors: {}, values: {}};
  const dirty = analysis.changes.length;
  const invalid = Object.keys(analysis.errors).length;

  useEffect(() => { onDirtyChange(dirty); }, [dirty, onDirtyChange]);
  useEffect(() => {
    if (!dirty && !busy && !uncertain) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty, busy, uncertain]);
  useEffect(() => () => { request.current?.abort(); }, []);
  useEffect(() => {
    if (active && !initialStarted.current) { initialStarted.current = true; void load(false); }
  }, [active]);

  async function load(preserve: boolean) {
    if (request.current) return;
    const controller = new AbortController(); request.current = controller;
    setBusy('load'); setError(''); setNotice('');
    try {
      const next = parseConfig(await requestConfig('GET', controller.signal));
      if (controller.signal.aborted) return;
      const nextDraft = preserve && config ? reconcileDraft(config, draft, next) : makeDraft(next);
      setConfig(next); setDraft(nextDraft); setUncertain(false);
      setNotice(preserve ? 'Aktuální hodnoty načteny. Rozepsané změny zůstaly zachované; před uložením zkontrolujte jejich přehled.' : 'Konfigurace je načtená.');
    } catch (caught) {
      if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : 'Konfiguraci se nepodařilo načíst.');
    } finally {
      if (!controller.signal.aborted) setBusy(null);
      if (request.current === controller) request.current = null;
    }
  }

  async function save() {
    if (!config || request.current || !dirty || invalid || uncertain) return;
    const controller = new AbortController(); request.current = controller;
    setBusy('save'); setError(''); setNotice('');
    let saved: SaveResult | undefined;
    try {
      saved = parseSave(await requestConfig('PUT', controller.signal, analysis.values), Object.keys(analysis.values));
      if (controller.signal.aborted) return;
      setResult(saved);
      setRestartKeys(previous => [...new Set([...previous, ...saved!.needs_restart])]);
      const next = parseConfig(await requestConfig('GET', controller.signal));
      if (controller.signal.aborted) return;
      setConfig(next); setDraft(makeDraft(next)); setUncertain(false);
      setNotice(`Uloženo ${saved.applied.length} změn. Znovu načtené hodnoty jsou zobrazené ve formuláři.`);
    } catch (caught) {
      if (controller.signal.aborted) return;
      const ambiguous = !!saved || !(caught instanceof ConfigRequestError) || caught.uncertain;
      setUncertain(ambiguous);
      const detail = caught instanceof Error ? caught.message : 'API není dostupné.';
      setError(saved ? `Server potvrdil uložení, ale načtení hodnot selhalo: ${detail}` : ambiguous ? `Výsledek uložení nelze potvrdit: ${detail}` : `Změny nebyly přijaty: ${detail}`);
    } finally {
      if (!controller.signal.aborted) setBusy(null);
      if (request.current === controller) request.current = null;
    }
  }

  if (!active) return null;
  const sections = config ? [...new Set(config.schema.map(field => field.section))] : [];
  const changedKeys = new Set(analysis.changes.map(change => change.field.key));
  const search = query.trim().toLocaleLowerCase();
  const visible = config?.schema.filter(field => (!section || field.section === section)
    && (!changedOnly || changedKeys.has(field.key))
    && `${field.key} ${field.help} ${field.section} ${sectionNames[field.section] ?? ''}`.toLocaleLowerCase().includes(search)) ?? [];
  return <div className="settings">
    <p className="settings-intro">Nastavení overlaye, událostí a snímačů. Změny se projeví až po uložení. <a href="/config">Původní nastavení ↗</a></p>
    {error && <div className="notice warning" role="alert">{error}</div>}
    {uncertain && <div className="notice warning">Před dalším zápisem načtěte aktuální hodnoty. Rozepsané změny zůstanou zachované; stav použití předchozího pokusu nemusí být známý.</div>}
    {notice && <div className="notice" role="status">{notice}</div>}
    {restartKeys.length > 0 && <section className="notice warning restart-summary"><strong>Server označil změny vyžadující restart</strong><ul>{restartKeys.map(key => <li key={key}>{key}</li>)}</ul><span>Tento seznam zůstává viditelný během práce ve Studiu. Samotné uložení službu nerestartuje.</span></section>}
    {result && <details className="save-details"><summary>Poslední potvrzené uložení · {result.applied.length} polí</summary><p>Server hlásí použití za běhu: {result.applied_live.length ? result.applied_live.join(', ') : 'žádné klíče'}</p><p>Vyžaduje restart: {result.needs_restart.length ? result.needs_restart.join(', ') : 'žádné klíče'}</p></details>}
    {!config ? <section className="panel"><h2>{busy ? 'Načítání nastavení…' : 'Nastavení není dostupné'}</h2><p>Formuláře budou dostupné po načtení konfigurace služby.</p><button type="button" className="button" disabled={!!busy} onClick={() => void load(false)}>Zkusit znovu</button></section> : <>
      <div className="settings-toolbar"><label>Vyhledat pole<input type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="Název nebo popis…"/></label><label>Sekce<select aria-label="Sekce" value={section} onChange={event => setSection(event.target.value)}><option value="">Všechny sekce</option>{sections.map(key => <option key={key} value={key}>{sectionNames[key] ?? key}</option>)}</select></label><label className="filter-changes"><input type="checkbox" checked={changedOnly} onChange={event => setChangedOnly(event.target.checked)}/> Jen změněné ({dirty})</label></div>
      <div className="settings-actions"><div><strong>{dirty ? `${dirty} neuložených změn` : 'Bez neuložených změn'}</strong><small>{invalid ? `${invalid} polí vyžaduje opravu.` : 'Rozepsané změny zůstávají při přepínání stránek Studia.'}</small></div><div className="action-buttons"><button className="button" type="button" disabled={!!busy} onClick={() => void load(true)}>{busy === 'load' ? 'Načítání…' : 'Načíst aktuální hodnoty'}</button><button className="button" type="button" disabled={!!busy || !dirty || uncertain} onClick={() => {if (window.confirm('Zahodit všechny neuložené změny?')) {setDraft(makeDraft(config));setError('');setNotice('Rozepsané změny byly vráceny.');}}}>Vrátit změny</button><button className="button primary" type="button" disabled={!!busy || !dirty || invalid > 0 || uncertain} onClick={() => void save()}>{busy === 'save' ? 'Ukládání…' : 'Uložit změny'}</button></div></div>
      {dirty > 0 && <details className="change-summary" open><summary>Přehled neuložených změn ({dirty})</summary><ul>{analysis.changes.map(({field,before,after,error:fieldError}) => <li key={field.key}><button type="button" className="field-jump" onClick={() => {setQuery(field.key);setSection('');setChangedOnly(false);}}>{field.key}</button><span>{display(before)} → {display(after)}</span><small>{fieldError ?? (field.live ? 'Za běhu' : 'Po restartu')}</small></li>)}</ul></details>}
      <p className="muted field-count">Zobrazeno {visible.length} z {config.schema.length} polí. {visible.length === 0 && 'Zkuste upravit filtr.'}</p>
      <form onSubmit={event => {event.preventDefault();void save();}}><fieldset disabled={!!busy || uncertain} className="settings-fields"><legend className="sr-only">Upravitelná konfigurace</legend>{sections.map(key => {const fields = visible.filter(field => field.section === key); return fields.length > 0 && <section className="panel settings-section" key={key}><h2>{sectionNames[key] ?? key}</h2><p className="section-key">{key}</p>{fields.map(field => <FieldInput key={field.key} field={field} value={draft[field.key]} changed={changedKeys.has(field.key)} error={analysis.errors[field.key]} onChange={value => setDraft(previous => ({...previous,[field.key]:value}))}/>)}</section>;})}</fieldset></form>
      <p className="muted settings-scope">Přístupové údaje a další položky mimo toto schéma se zde neupravují. Konfigurace komentáře používá samostatný postup.</p>
    </>}
  </div>;
}
