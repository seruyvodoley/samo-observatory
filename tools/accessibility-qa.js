async (page) => {
 const paths=['/','/organism','/evolution','/lab','/inventions','/memory','/science','/about'];const results=[];
 for(const width of [1440,360]){
  await page.setViewportSize({width,height:1000});
  for(const path of paths){
   await page.goto('http://127.0.0.1:4174'+path);await page.waitForFunction(()=>!document.querySelector('[role="status"]')&&document.querySelector('main h1'));
   await page.waitForTimeout(600);
   await page.addScriptTag({url:'http://127.0.0.1:4174/qa-axe.min.js'});
   const result=await page.evaluate(async()=>{const r=await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']}});return {violations:r.violations.map(v=>({id:v.id,impact:v.impact,description:v.description,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))})),incomplete:r.incomplete.map(v=>({id:v.id,nodes:v.nodes.length})),passes:r.passes.length};});
   results.push({path,width,...result});
  }
 }
 return {tool:'axe-core',results,violations:results.flatMap(r=>r.violations.map(v=>({path:r.path,width:r.width,...v})))};
}
