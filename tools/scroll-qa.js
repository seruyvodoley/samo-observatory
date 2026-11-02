async (page) => {
 await page.addInitScript(()=>{window.__scrollCalls=[];const original=window.scrollTo.bind(window);window.scrollTo=(...args)=>{window.__scrollCalls.push({args,height:document.body.scrollHeight,viewport:innerHeight,before:scrollY,time:performance.now()});return original(...args)};document.addEventListener('click',e=>window.__scrollCalls.push({click:e.target.textContent,before:scrollY}),true);window.addEventListener('popstate',()=>window.__scrollCalls.push({popstate:true,before:scrollY}));});
 await page.setViewportSize({width:1440,height:1040});
 await page.goto('http://127.0.0.1:4174/memory');
 await page.getByRole('heading',{name:'Память',exact:true}).waitFor();await page.waitForTimeout(500);
 await page.evaluate(()=>scrollTo({top:700,behavior:'instant'}));await page.waitForTimeout(100);
 const before=await page.evaluate(()=>scrollY);
 const box=await page.getByRole('navigation').getByRole('link',{name:'Наука',exact:true}).boundingBox();
 await page.mouse.click(box.x+box.width/2,box.y+box.height/2);
 await page.getByRole('heading',{name:'Наука',exact:true}).waitFor();await page.waitForTimeout(400);
 await page.goBack();await page.getByRole('heading',{name:'Память',exact:true}).waitFor();await page.waitForTimeout(400);
 const after=await page.evaluate(()=>scrollY);
 const calls=await page.evaluate(()=>window.__scrollCalls);
 return {before,after,calls,passed:Math.abs(before-after)<5,url:page.url()};
}
