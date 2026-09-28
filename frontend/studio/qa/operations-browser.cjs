// All operational writes are intercepted; this test never controls a live service.
const {chromium}=require(process.env.STUDIO_PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.STUDIO_CHROME_PATH?{executablePath:process.env.STUDIO_CHROME_PATH}:{})});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const writes=[];let fail=false,release;let delay=false,staleStatus=false,staleDecisions=false;
  await page.route('**/*',async route=>{
   const req=route.request(),path=new URL(req.url()).pathname;
   if(req.method()!=='GET'){
    assert.equal(req.headers()['x-requested-with'],'irswitch');writes.push({path,body:req.postDataJSON()});
    if(delay)await new Promise(resolve=>{release=resolve;});
    return route.fulfill({status:fail?500:200,json:fail?{error:'uncertain result'}:{accepted:true,status:'ok'}});
   }
   const fixtures={'/status':{connected_obs:true,connected_iracing:false,autoswitch:true,current_scene:'Race',streaming:false},'/oauth/status':{authenticated:false},'/logging/level':{level:'INFO'},'/api/commentary/runtime':{status:'ready'},'/api/commentary/runtime/decisions':{runtime:true,decisions:[]},'/api/overlay/debug/events':{events:['race_start']},'/api/overlay/snapshot':{race:{},bio:{},system:{}}};
   if((path==='/status'&&staleStatus)||(path==='/api/commentary/runtime/decisions'&&staleDecisions))return route.fulfill({status:503,json:{error:'offline'}});
   if(fixtures[path])return route.fulfill({json:fixtures[path]});
   if(path==='/oauth/initiate')return route.fulfill({json:{authorization_url:'https://accounts.google.com/o/oauth2/v2/auth?fixture=true'}});
   return route.continue();
  });
  const base=process.env.STUDIO_BASE_URL||'http://127.0.0.1:17329';
  await page.goto(`${base}/studio/#/obs`);
  await page.getByText('Race',{exact:true}).waitFor();
  await page.getByRole('button',{name:'Použít ruční scénu'}).click();
  assert.equal(writes.length,0);
  await page.getByLabel('Název scény',{exact:true}).fill('Camera');await page.getByLabel('Doba přepnutí (s)').fill('12');
  delay=true;await page.getByRole('button',{name:'Použít ruční scénu'}).click();
  await page.getByRole('link',{name:'Diagnostika',exact:true}).click();
  assert.equal(await page.getByRole('button',{name:'Restartovat službu',exact:true}).isDisabled(),true);
  for(let i=0;!release&&i<100;i++)await page.waitForTimeout(10);assert.ok(release);release();delay=false;
  await page.getByText('Server přijal akci.',{exact:false}).waitFor();
  assert.deepEqual(writes[0],{path:'/override',body:{scene:'Camera',seconds:12}});
  page.once('dialog',d=>d.dismiss());await page.getByRole('button',{name:'Restartovat službu',exact:true}).click();assert.equal(writes.length,1);
  fail=true;page.once('dialog',d=>d.accept());await page.getByRole('button',{name:'Restartovat službu',exact:true}).click();
  await page.getByRole('button',{name:'Ověřit stav před další akcí'}).waitFor();
  assert.equal(await page.getByRole('button',{name:'Reset stavu',exact:true}).isDisabled(),true);
  page.once('dialog',d=>d.accept());await page.getByRole('button',{name:'Ověřit stav před další akcí'}).click();fail=false;
  await page.getByRole('link',{name:'Komentář',exact:true}).click();
  await page.getByLabel('Jazyk prohlížeče').selectOption('cs-CZ');
  await page.getByRole('button',{name:'Ověřit text s vazbami'}).click();
  await page.getByText('Server přijal akci.',{exact:false}).waitFor();assert.equal(writes.at(-1).path,'/api/commentary/validate');assert.ok(writes.at(-1).body.actorBindings);
  page.once('dialog',d=>d.dismiss());await page.getByRole('button',{name:'Přehrát přes službu'}).click();assert.equal(writes.length,3);
  staleDecisions=true;await page.getByText('Poslední data nejsou aktuální:',{exact:false}).waitFor();assert.equal(await page.getByRole('button',{name:'Přehrát přes službu'}).isDisabled(),true);
  await page.getByRole('link',{name:'OBS scény',exact:true}).click();staleStatus=true;await page.getByText('Poslední data nejsou aktuální:',{exact:false}).waitFor();assert.equal(await page.getByRole('button',{name:'Obnovit informace vysílání'}).isDisabled(),true);assert.equal(await page.getByText('Neznámý stav',{exact:true}).count()>0,true);
  await page.getByRole('link',{name:'Overlay',exact:true}).click();
  await page.getByRole('heading',{name:'Izolované demo vzhledu'}).waitFor();assert.match(await page.locator('iframe').getAttribute('src'),/demo=1/);
  page.once('dialog',d=>d.dismiss());await page.getByRole('button',{name:'race_start',exact:true}).click();assert.equal(writes.length,3);
  page.once('dialog',d=>d.accept());await page.getByRole('button',{name:'race_start',exact:true}).click();await page.getByText('Server přijal akci.',{exact:false}).waitFor();assert.equal(writes.at(-1).path,'/overlay/debug/emit');
  await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  assert.deepEqual(errors,[]);console.log('PASS operations: validation, shared action lock, uncertain outcome reconciliation, cancellation, fixture-only validation and live debug gating, mobile layout.');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
