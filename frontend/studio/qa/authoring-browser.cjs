// Run against an isolated preview with a disposable APP_STUDIO_STORE; never production.
const {chromium}=require(process.env.STUDIO_PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.STUDIO_CHROME_PATH?{executablePath:process.env.STUDIO_CHROME_PATH}:{})});
 try{
  const page=await browser.newPage({viewport:{width:1500,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const base=process.env.STUDIO_BASE_URL||'http://127.0.0.1:17330';
  // Fail closed if someone points the QA at a normal configured service.
  const config=await page.request.get(`${base}/api/config`);assert.equal(config.ok(),false,'QA requires an unconfigured disposable preview');
  await page.goto(`${base}/studio/#/scenarios`);
  await page.getByText('Definice načteny.',{exact:true}).waitFor();
  const editor=page.getByLabel('Koncept definic (JSON)'),original=await editor.inputValue();
  for(const value of ['{}','null','[]','{"stories":1}']){
   await editor.fill(value);await page.getByRole('button',{name:'Validovat koncept',exact:true}).click();
   await page.getByText('Koncept zůstal zachován.',{exact:false}).waitFor();assert.equal(await editor.inputValue(),value);
  }
  await editor.fill(original);
  await page.getByLabel('Nové ID',{exact:true}).fill(`studio.qa_${Date.now()}`);
  await page.getByLabel(/Šablona story/).selectOption('battle_ahead');
  await page.getByRole('button',{name:'Přidat story do konceptu'}).click();
  const modified=await editor.inputValue();assert.equal(JSON.parse(modified).stories.length,JSON.parse(original).stories.length+1);
  await page.getByRole('button',{name:'Zpět',exact:true}).click();assert.equal(await editor.inputValue(),original);
  await page.getByRole('button',{name:'Znovu',exact:true}).click();assert.equal(await editor.inputValue(),modified);
  await page.getByRole('link',{name:'Přehled',exact:true}).click();await page.getByRole('link',{name:'Scénáře',exact:true}).click();assert.equal(await editor.inputValue(),modified);
  await page.getByRole('button',{name:'Validovat koncept',exact:true}).click();await page.getByText('Validace prošla.',{exact:false}).waitFor();
  await page.getByRole('button',{name:'Uložit novou revizi',exact:true}).click();await page.getByText('Revize uložena.',{exact:false}).waitFor();
  page.once('dialog',d=>d.accept());await page.getByRole('button',{name:'Aktivovat / vrátit revizi při příštím spuštění'}).click();await page.getByText('Revize vybrána pro příští spuštění služby.',{exact:false}).waitFor();
  const state=await (await page.request.get(`${base}/api/studio/definitions`)).json();assert.equal(state.runtime.effectiveRevision,'builtin');assert.notEqual(state.pendingRevision,'builtin');
  // Explicit concurrent mutation forces a 409 and retains the editor draft.
  await page.request.post(`${base}/api/studio/definitions/save`,{data:{document:state.builtin,baseRevision:state.baseRevision},headers:{'X-Requested-With':'irswitch'}});
  await editor.fill(original);await page.getByRole('button',{name:'Validovat koncept',exact:true}).click();await page.getByText('Validace prošla.',{exact:false}).waitFor();
  await page.getByRole('button',{name:'Uložit novou revizi',exact:true}).click();await page.getByText('Revision changed',{exact:false}).waitFor();assert.equal(await editor.inputValue(),original);assert.equal(await editor.isDisabled(),true);
  await page.getByRole('button',{name:'Načíst aktuální revize'}).click();await page.getByText('Revize znovu načteny.',{exact:false}).waitFor();assert.equal(await editor.isEnabled(),true);
  // Graph selection and layout stay client-side.
  await page.getByRole('button',{name:'battle.pursuit',exact:true}).first().click();await page.getByRole('heading',{name:'battle.pursuit',exact:true}).waitFor();
  await page.getByRole('button',{name:'Oddálit',exact:true}).click();
  const exported=page.waitForEvent('download');await page.getByRole('button',{name:'Export JSON',exact:true}).click();assert.equal((await exported).suggestedFilename(),'studio-definitions.json');
  await page.getByRole('link',{name:'Epizody',exact:true}).click();await page.getByText('Provider epizod není dostupný.',{exact:true}).waitFor();
  await page.getByRole('link',{name:'Replay',exact:true}).click();await page.getByLabel(/Scénář/).selectOption('narrative_world');
  await page.getByLabel('Volitelný koncept definic (JSON, prázdné = vestavěné)').fill(modified);
  await page.getByRole('button',{name:'Spustit nový izolovaný běh'}).click();await page.getByText('Běh ',{exact:false}).filter({hasText:'otisk výstupu'}).waitFor();
  await page.getByRole('button',{name:'Na konec',exact:true}).click();await page.getByText('APPLY_CONTEXT_BATCH',{exact:false}).first().waitFor();
  assert.equal(await page.locator('.replay-nodes button[data-reached=true]').count(),3);
  await page.getByRole('button',{name:'Na začátek',exact:true}).click();assert.equal(await page.locator('.replay-nodes button[data-reached=true]').count(),0);
  await page.getByRole('button',{name:'Připnout běh pro porovnání',exact:true}).click();
  const before=await page.getByText('Běh ',{exact:false}).filter({hasText:'otisk výstupu'}).textContent();
  await page.getByRole('button',{name:'Spustit nový izolovaný běh'}).click();await page.getByRole('button',{name:'Spustit nový izolovaný běh'}).waitFor();
  assert.notEqual(await page.getByText('Běh ',{exact:false}).filter({hasText:'otisk výstupu'}).textContent(),before);
  await page.getByText('Shodný deterministický výstup.',{exact:true}).waitFor();
  await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  if(process.env.STUDIO_SCREENSHOT)await page.screenshot({path:process.env.STUDIO_SCREENSHOT,fullPage:true});
  assert.deepEqual(errors,[]);console.log('PASS authoring browser: real disposable store, malformed drafts, undo/redo, persistence/conflict/activation, graph/list, unavailable episodes, custom-definition replay, mobile.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});

