async (page) => {
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.emulateMedia({reducedMotion:'no-preference'});await page.setViewportSize({width:1440,height:1040});
 await page.goto('http://127.0.0.1:4174/memory');await page.locator('.compare-controls select').last().locator('option').nth(1).waitFor({state:'attached'});await page.waitForTimeout(500);
 const row=page.getByRole('row').filter({hasText:'Точность train'});
 const cells=await row.locator('td').allTextContents();
 await page.screenshot({path:'/Users/serg/Projects/SAMO/output/playwright/memory-desktop.png',fullPage:true});
 const initial={cells,passed:cells.at(-1)==='Нет измерения'&&cells.at(-2)==='Нет измерения'};
 const select=page.locator('.compare-controls select').last();const options=await select.locator('option').evaluateAll(o=>o.map(x=>x.value));await select.selectOption(options[1]);await page.waitForTimeout(500);
 const measured=await row.locator('td').allTextContents();
 await page.setViewportSize({width:360,height:900});await page.goto('http://127.0.0.1:4174/evolution');await page.locator('.mobile-events li').first().waitFor();await page.waitForTimeout(500);
 const mobile={cards:await page.locator('.mobile-events li').count(),overflow:await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)};
 await page.screenshot({path:'/Users/serg/Projects/SAMO/output/playwright/evolution-mobile.png',fullPage:true});
 return {unmeasuredDifference:initial,measuredDifference:{cells:measured,passed:measured.at(-1)!=='Нет измерения'},mobile,errors};
}
