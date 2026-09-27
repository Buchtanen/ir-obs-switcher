// Optional browser QA with an externally supplied Playwright runtime. No live config writes.
// STUDIO_PLAYWRIGHT_MODULE must point to installed Playwright; STUDIO_CHROME_PATH is optional.
const {chromium} = require(process.env.STUDIO_PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const base = process.env.STUDIO_BASE_URL || 'http://127.0.0.1:17329';
const field = (key, type, value, extra = {}) => ({key,type,default:value,live:true,section:'overlay',help:'Test field',min:null,max:null,optional:false,choices:null,secret:false,...extra});
const fixture = () => ({schema:[
  field('overlay.enabled','bool',true), field('overlay.theme','str','dark',{choices:['dark','light']}),
  field('sampling.hz','float',2,{section:'sampling',min:1,max:20}),
  field('sampling.optional','int',null,{section:'sampling',optional:true,min:1,max:10}),
  field('overlay.session_tape_dir','str','recordings',{live:false}),
  field('secret','str','SHOULD_NOT_RENDER',{secret:true}),
],overlay:{'overlay.enabled':true,'overlay.theme':'dark','sampling.hz':2,'sampling.optional':null,'overlay.session_tape_dir':'recordings',secret:'SHOULD_NOT_RENDER'},switcher:{password:'SHOULD_NOT_RENDER'}});

(async () => {
  const browser = await chromium.launch({headless:true,...(process.env.STUDIO_CHROME_PATH ? {executablePath:process.env.STUDIO_CHROME_PATH} : {})});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1100}});
    const errors=[]; page.on('pageerror',error=>errors.push(error.message));
    let data=fixture(), reads=0, writes=[], failRead=false, failWrite=0, pendingRelease;
    await page.route('**/api/config', async route => {
      if (route.request().method()==='GET') {reads++; return route.fulfill(failRead ? {status:500,json:{error:'config unavailable'}} : {json:data});}
      const body=route.request().postDataJSON(); writes.push(body);
      assert.equal(route.request().headers()['x-requested-with'],'irswitch');
      if(failWrite) return route.fulfill({status:failWrite,json:{error:'test rejection'}});
      await new Promise(resolve=>{pendingRelease=resolve;});
      Object.assign(data.overlay,body.values);
      return route.fulfill({json:{status:'ok',applied:Object.keys(body.values),applied_live:Object.keys(body.values).filter(key=>key!=='overlay.session_tape_dir'),needs_restart:Object.keys(body.values).filter(key=>key==='overlay.session_tape_dir')}});
    });
    await page.goto(`${base}/studio/#/settings`);
    await page.getByText('Konfigurace je načtená.',{exact:true}).waitFor();
    assert.equal(reads,1);
    assert.equal(await page.getByText('SHOULD_NOT_RENDER',{exact:false}).count(),0);
    const input=key=>page.locator(`[id="setting-${key}"]`);
    await input('sampling.hz').fill('99');
    await page.getByText('Maximum je 20.',{exact:true}).first().waitFor();
    assert.equal(await page.getByRole('button',{name:'Uložit změny',exact:true}).isDisabled(),true);
    await input('sampling.hz').fill('4.5');
    await page.getByRole('link',{name:'Přehled',exact:true}).click();
    await page.getByRole('link',{name:/Nastavení/}).click();
    assert.equal(await input('sampling.hz').inputValue(),'4.5');
    assert.equal(reads,1);
    assert.equal(await page.evaluate(()=>{const event=new Event('beforeunload',{cancelable:true});window.dispatchEvent(event);return event.defaultPrevented;}),true);
    await page.getByLabel('Vyhledat pole').fill('theme');
    assert.equal(await page.locator('.setting-field').count(),1);
    await input('overlay.theme').selectOption('light');
    await page.getByLabel('Vyhledat pole').fill('');
    await page.getByLabel('Sekce',{exact:true}).selectOption('sampling');
    assert.equal(await page.locator('.setting-field').count(),2);
    await page.getByLabel('Použít výchozí / zděděnou hodnotu').uncheck();
    await input('sampling.optional').fill('3');
    await page.getByLabel('Sekce',{exact:true}).selectOption('');
    await input('overlay.enabled').uncheck();
    await input('overlay.session_tape_dir').fill('recordings-new');
    await page.getByLabel(/Jen změněné/).check();
    assert.equal(await page.locator('.setting-field').count(),5);
    await page.getByRole('button',{name:'Uložit změny',exact:true}).click();
    await page.getByRole('button',{name:'Ukládání…',exact:true}).waitFor();
    assert.equal(await input('sampling.hz').isDisabled(),true);
    await page.waitForFunction(()=>document.querySelector('.settings-fields').disabled);
    for(let i=0;!pendingRelease && i<100;i++) await page.waitForTimeout(10);
    assert.ok(pendingRelease,'PUT arrived');
    pendingRelease();pendingRelease=null;
    await page.getByText('Uloženo 5 změn.',{exact:false}).waitFor();
    assert.deepEqual(writes[0].values,{'overlay.enabled':false,'overlay.theme':'light','sampling.hz':4.5,'sampling.optional':3,'overlay.session_tape_dir':'recordings-new'});
    await page.getByText('Server označil změny vyžadující restart',{exact:true}).waitFor();
    assert.equal(reads,2);
    await page.getByLabel(/Jen změněné/).uncheck();
    // A rejected write is retryable and retains the edit.
    await input('sampling.hz').fill('5');failWrite=403;
    await page.getByRole('button',{name:'Uložit změny',exact:true}).click();
    await page.getByText('Změny nebyly přijaty:',{exact:false}).waitFor();
    assert.equal(await input('sampling.hz').inputValue(),'5');
    assert.equal(await page.getByRole('button',{name:'Uložit změny',exact:true}).isEnabled(),true);
    // A server failure has an uncertain outcome and requires a read before another write.
    failWrite=400;await page.getByRole('button',{name:'Uložit změny',exact:true}).click();
    await page.getByText('Výsledek uložení nelze potvrdit:',{exact:false}).waitFor();
    assert.equal(await page.getByRole('button',{name:'Uložit změny',exact:true}).isDisabled(),true);
    failRead=true;await page.getByRole('button',{name:'Načíst aktuální hodnoty',exact:true}).click();
    await page.getByText('config unavailable',{exact:true}).waitFor();
    assert.equal(await input('sampling.hz').inputValue(),'5');
    assert.equal(await page.getByRole('button',{name:'Uložit změny',exact:true}).isDisabled(),true);
    failRead=false;data.overlay['overlay.theme']='dark';
    await page.getByRole('button',{name:'Načíst aktuální hodnoty',exact:true}).click();
    await page.getByText('Aktuální hodnoty načteny.',{exact:false}).waitFor();
    assert.equal(await input('sampling.hz').inputValue(),'5');
    assert.equal(await input('overlay.theme').inputValue(),'dark');
    assert.equal(await page.getByRole('button',{name:'Uložit změny',exact:true}).isEnabled(),true);
    // Reverting requires confirmation; cancel retains edits, confirm resets them.
    page.once('dialog',dialog=>dialog.dismiss());
    await page.getByRole('button',{name:'Vrátit změny',exact:true}).click();
    assert.equal(await input('sampling.hz').inputValue(),'5');
    page.once('dialog',dialog=>dialog.accept());
    await page.getByRole('button',{name:'Vrátit změny',exact:true}).click();
    assert.equal(await input('sampling.hz').inputValue(),'4.5');
    assert.equal(await page.evaluate(()=>{const event=new Event('beforeunload',{cancelable:true});window.dispatchEvent(event);return event.defaultPrevented;}),false);
    // Confirmed save followed by failed canonical readback also requires reconciliation.
    failWrite=0;failRead=true;await input('sampling.hz').fill('6');
    await page.getByRole('button',{name:'Uložit změny',exact:true}).click();
    for(let i=0;!pendingRelease && i<100;i++) await page.waitForTimeout(10);
    assert.ok(pendingRelease,'second PUT arrived');pendingRelease();pendingRelease=null;
    await page.getByText('Server potvrdil uložení, ale načtení hodnot selhalo:',{exact:false}).waitFor();
    assert.equal(await input('sampling.hz').inputValue(),'6');
    assert.equal(await page.getByRole('button',{name:'Uložit změny',exact:true}).isDisabled(),true);
    failRead=false;await page.getByRole('button',{name:'Načíst aktuální hodnoty',exact:true}).click();
    await page.getByText('Aktuální hodnoty načteny.',{exact:false}).waitFor();
    assert.equal(await input('sampling.hz').inputValue(),'6');
    await page.getByText('Bez neuložených změn',{exact:true}).waitFor();
    await page.locator('main').focus();await page.evaluate(()=>window.scrollTo(0,0));
    if(process.env.STUDIO_SCREENSHOT) await page.screenshot({path:process.env.STUDIO_SCREENSHOT.replace('.png','-desktop.png'),fullPage:true});
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    if(process.env.STUDIO_SCREENSHOT) await page.screenshot({path:process.env.STUDIO_SCREENSHOT,fullPage:true});
    assert.deepEqual(errors,[]);
    // A fresh page starts unavailable and can explicitly retry without any writes.
    const offline = await browser.newPage();let unavailable=true;
    await offline.route('**/api/config',route=>route.fulfill(unavailable ? {status:500,json:{error:'config unavailable'}} : {json:fixture()}));
    await offline.goto(`${base}/studio/#/settings`);
    await offline.getByRole('heading',{name:'Nastavení není dostupné'}).waitFor();
    unavailable=false;await offline.getByRole('button',{name:'Zkusit znovu'}).click();
    await offline.getByText('Konfigurace je načtená.',{exact:true}).waitFor();
    await offline.close();
    console.log('PASS: settings browser workflow, fixtures only; no live configuration writes.');
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
