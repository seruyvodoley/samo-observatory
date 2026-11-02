async page=>{
 const base='https://samo-observatory.duckdns.org',checks=[],errors=[];page.on('pageerror',e=>errors.push(e.message));
 const check=(name,pass,detail)=>{checks.push({name,pass,detail});if(!pass)throw Error(name)};
 await page.goto(base+'/organism');await page.locator('.live-instrument').waitFor();
 const data=await (await page.request.get(base+'/data/ecosystem.json')).json();
 const count=g=>g.modules.reduce((n,c)=>n+c.length,0)+g.search.length+g.router.length+g.dialect.reduce((n,c)=>n+c.length,0)+g.memory.length;
 for(const f of data.population){await page.locator('.instrument-choice').selectOption(f.id);await page.waitForTimeout(250);check('actual form '+f.id,await page.locator('.live-instrument').getAttribute('data-genome-hash')===f.hash);check('actual arc count '+f.id,await page.locator('.live-instrument path').count()===count(f.genome));}
 check('no pilot circle',await page.locator('.specimen').count()===0);
 const historical=data.history?.find(x=>!data.population.some(y=>y.id===x.id));if(historical){await page.locator('.instrument-choice').selectOption(historical.id);await page.waitForFunction(hash=>document.querySelector('.live-instrument')?.getAttribute('data-genome-hash')===hash,historical.hash);check('historical genome',await page.locator('.live-instrument').getAttribute('data-genome-hash')===historical.hash);}
 await page.locator('.instrument-choice').selectOption(data.population[0].id);await page.waitForFunction(h=>document.querySelector('.live-instrument')?.getAttribute('data-genome-hash')===h,data.population[0].hash);await page.screenshot({path:'/Users/serg/Projects/SAMO/output/instrument-after.png',fullPage:true});await page.setViewportSize({width:360,height:850});check('mobile no overflow',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.screenshot({path:'/Users/serg/Projects/SAMO/output/instrument-mobile.png',fullPage:true});
 let fixture;await page.route('**/data/ecosystem.json',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(fixture)}));
 const hash=async g=>page.evaluate(async g=>{const c=x=>Array.isArray(x)?'['+x.map(c).join(',')+']':x&&typeof x==='object'?'{'+Object.keys(x).sort().map(k=>JSON.stringify(k)+':'+c(x[k])).join(',')+'}':JSON.stringify(x);return [...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(c(g))))].map(v=>v.toString(16).padStart(2,'0')).join('')},g);
 for(const modules of [1,5,8]){
  const g=structuredClone(data.population[0].genome);g.modules=Array.from({length:modules},(_,i)=>Array.from({length:i+1},(_,j)=>[0,j]));g.memory=Array.from({length:modules===8?64:0},(_,i)=>i);
  const f={...data.population[0],id:'fixture-'+modules,genome:g,hash:await hash(g)};fixture={...data,population:[f],history:[],events:[]};await page.goto(base+'/organism?eco='+f.id);await page.locator('.live-instrument').waitFor();
  check('fixture SVG exact '+modules,await page.locator('.live-instrument path').count()===count(g));
  check('opcode and argument mapping '+modules,await page.locator('[data-track="Модуль 0"][data-index="0"]').getAttribute('data-argument')==='0');
 }
 fixture={...data,population:[{...data.population[0],hash:'0'.repeat(64)}],history:[]};await page.goto(base+'/organism');await page.getByRole('alert').filter({hasText:'не совпадает'}).waitFor();check('hash mismatch rejects without fallback',await page.locator('.live-instrument,.specimen').count()===0);
 fixture={...data,history:[{...data.population[0],hash:'0'.repeat(64)}]};await page.goto(base+'/organism');await page.getByRole('alert').filter({hasText:'conflict'}).waitFor();check('ID conflict rejected',await page.locator('.live-instrument').count()===0);
 fixture={...data,schema:999};await page.goto(base+'/organism');await page.getByRole('alert').waitFor();check('unsupported schema no pilot',await page.locator('.specimen').count()===0);
 fixture={...data,population:[],history:[]};await page.goto(base+'/organism');await page.getByRole('heading',{level:1}).waitFor();check('empty population no invented form',await page.locator('.live-instrument').count()===0);
 await page.unroute('**/data/ecosystem.json');await page.goto(base+'/organism');await page.locator('.live-instrument').waitFor();
 const paths=['/','/organism','/evolution','/lab','/inventions','/memory','/science','/about'];for(const path of paths){await page.goto(base+path);await page.getByRole('heading',{level:1}).waitFor();check('direct route '+path,true);}
 check('no JS errors',errors.length===0,errors);
 return {checks,errors,step:data.step,snapshot:data.snapshot_id};
}
