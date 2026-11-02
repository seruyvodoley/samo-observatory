async page=>{
 await page.goto('https://samo-observatory.duckdns.org/organism');await page.locator('.live-instrument').waitFor();
 const before=await page.locator('.ecology-panel').getAttribute('data-step');const beforeHash=await page.locator('.live-instrument').getAttribute('data-genome-hash');
 await page.waitForFunction(n=>Number(document.querySelector('.ecology-panel')?.getAttribute('data-step'))>Number(n),before,{timeout:260000});
 return {beforeStep:before,afterStep:await page.locator('.ecology-panel').getAttribute('data-step'),beforeHash,afterHash:await page.locator('.live-instrument').getAttribute('data-genome-hash'),snapshot:await page.locator('.ecology-panel').getAttribute('data-snapshot-id'),reloaded:false};
}
