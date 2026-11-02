async (page) => {
 const base='http://127.0.0.1:4174', results=[];
 await page.emulateMedia({reducedMotion:'no-preference'});
 await page.addInitScript(()=>{
  window.__transitions=[];
  const original=document.startViewTransition?.bind(document);
  if(original)document.startViewTransition=(...args)=>{const t=original(...args);t.ready.then(()=>window.__transitions.push({animations:document.getAnimations().map(a=>({name:a.animationName||'',target:a.effect?.pseudoElement||a.effect?.target?.tagName||null})),time:performance.now()})).catch(()=>{});return t;};
 });
 await page.setViewportSize({width:1440,height:1000});
 await page.goto(base);await page.getByRole('heading',{level:1}).filter({hasText:'Жизнь'}).waitFor();
 await page.getByRole('link',{name:'Исследовать организм',exact:true}).click();
 await page.getByRole('heading',{name:'Внутри организма',exact:true}).waitFor();await page.waitForTimeout(500);
 results.push({flow:'life -> organism',native:await page.evaluate(()=>window.__transitions),sharedName:'organism-specimen'});
 await page.getByRole('navigation').getByRole('link',{name:'Эволюция',exact:true}).click();await page.getByRole('heading',{name:'Эволюция',exact:true}).waitFor();await page.waitForTimeout(500);
 const href=await page.locator('.graph-viewport a').first().getAttribute('href');
 await page.locator('.graph-viewport a').first().click();await page.getByRole('heading',{name:'Внутри организма',exact:true}).waitFor();await page.waitForTimeout(500);
 const graphFrame=await page.evaluate(()=>window.__transitions.at(-1));
 const nodeName='node-'+decodeURIComponent(href.split('/').at(-1)).replaceAll(':','-');
 results.push({flow:'graph -> organism',native:graphFrame,target:href,sharedNode:graphFrame.animations.some(a=>a.target===`::view-transition-old(${nodeName})`)&&graphFrame.animations.some(a=>a.target===`::view-transition-new(${nodeName})`)});
 await page.getByRole('navigation').getByRole('link',{name:'Память',exact:true}).click();await page.getByRole('heading',{name:'Память',exact:true}).waitFor();await page.waitForTimeout(500);
 const select=page.locator('.compare-controls select').last();await select.locator('option').nth(1).waitFor({state:'attached'});const values=await select.locator('option').evaluateAll(a=>a.map(x=>x.value));
 await select.selectOption(values[1]);await page.waitForTimeout(500);
 results.push({flow:'memory state -> state',native:await page.evaluate(()=>window.__transitions.at(-1)),url:page.url(),sharedNames:['memory-left','memory-right']});
 await page.emulateMedia({reducedMotion:'reduce'});
 await page.getByRole('navigation').getByRole('link',{name:'Жизнь',exact:true}).click();await page.waitForTimeout(500);
 const motion=await page.evaluate(()=>document.getAnimations().filter(a=>a.playState==='running').length);
 return {supported:await page.evaluate(()=>!!document.startViewTransition),results,reducedMotionRunningAnimations:motion,inventionFlow:'No confirmed inventions exist; evidence -> catalog navigation only. No fictitious confirmed artifact transition.'};
}
