async page=>{
 const base='https://samo-observatory.duckdns.org',checks=[],errors=[];page.on('pageerror',e=>errors.push(e.message));
 const check=(name,pass,detail)=>{checks.push({name,pass,detail});if(!pass)throw Error(name)};
 const routes=[['/','Жизнь САМО','Жизнь'],['/organism','Программа под лупой','Организм'],['/evolution','Как меняется САМО','Эволюция'],['/lab','Как проходят испытания','Лаборатория'],['/inventions','Что удалось открыть','Изобретения'],['/memory','Что хранится в памяти','Память'],['/science','Как мы проверяем результаты','Наука'],['/about','Что такое САМО','О проекте']];
 await page.emulateMedia({reducedMotion:'reduce'});await page.goto(base);await page.getByRole('heading',{name:routes[0][1],exact:true}).waitFor();
 for(const width of [1440,768,360]){
  await page.setViewportSize({width,height:1000});
  for(const [path,title,label] of routes){
   if(await page.locator('.menu-toggle').isVisible()&&await page.locator('.menu-toggle').getAttribute('aria-expanded')==='false')await page.locator('.menu-toggle').click();
   await page.getByRole('navigation',{name:'Основные разделы'}).getByRole('link',{name:label,exact:true}).click();await page.getByRole('heading',{name:title,level:1,exact:true}).waitFor();await page.waitForTimeout(250);
   check('nav and content '+width+' '+path,true);check('fits '+width+' '+path,await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));check('research closed '+width+' '+path,await page.locator('.visitor-research[open]').count()===0);
   if(width===1440)await page.screenshot({path:'/Users/serg/Projects/SAMO/output/visitor-site/'+(path==='/'?'life':path.slice(1))+'.png',fullPage:true});
   if(width===360&&['/','/organism','/memory'].includes(path))await page.screenshot({path:'/Users/serg/Projects/SAMO/output/visitor-site/'+(path==='/'?'life':path.slice(1))+'-mobile.png',fullPage:true});
  }
 }
 await page.goto(base+'/organism');await page.locator('.live-instrument').waitFor();const f=page.locator('.live-instrument path[role=button]').first();await f.focus();const before=await page.evaluate(()=>document.activeElement.getAttribute('aria-label'));await page.keyboard.press('ArrowRight');const after=await page.evaluate(()=>document.activeElement.getAttribute('aria-label'));check('instrument arrow navigation',before!==after);check('one instrument tab stop',await page.locator('.live-instrument path[tabindex="0"]').count()===1);check('no running motion when reduced',await page.evaluate(()=>document.getAnimations().filter(a=>a.playState==='running').length)===0);
 await page.goto(base+'/memory');await page.getByRole('heading',{name:'Что хранится в памяти',exact:true}).waitFor();const cell=page.locator('.visitor-memory button').first();if(await cell.count()){const label=await cell.getAttribute('aria-label');await cell.click();check('memory cell explanation',!!(await page.getByRole('status').textContent())&&label.includes(':'));}
 await page.goto(base+'/evolution');await page.getByRole('heading',{name:'Как меняется САМО',exact:true}).waitFor();const old=await page.locator('.visitor-timeline>li').count();const more=page.getByRole('button',{name:'Показать более ранние попытки'});if(await more.count()){await more.click();check('older events accessible',await page.locator('.visitor-timeline>li').count()>old);}
 await page.goto(base+'/lab');await page.getByRole('heading',{name:'Как проходят испытания',exact:true}).waitFor();check('example explicitly educational',await page.getByText('Учебный пример задачи',{exact:true}).isVisible());
 await page.route('**/data/ecosystem.json',r=>r.fulfill({status:503,body:'unavailable'}));for(const path of ['/about','/science']){await page.goto(base+path);await page.getByRole('heading',{name:routes.find(x=>x[0]===path)[1],exact:true}).waitFor();check('info survives data outage '+path,true);}
 await page.goto(base);await page.getByRole('heading',{name:'Не удалось получить наблюдения',exact:true}).waitFor();check('friendly data failure without pilot',await page.locator('.specimen,.live-instrument').count()===0);await page.unroute('**/data/ecosystem.json');
 await page.goto(base+'/organism?archive=pilot');await page.getByRole('heading',{name:'Внутри организма',exact:true}).waitFor();check('research archive preserved',await page.locator('.specimen').count()===1);
 check('no JS errors',errors.length===0,errors);return {checks,errors,passed:checks.filter(x=>x.pass).length};
}
