async (page) => {
  const base='http://127.0.0.1:4174';
  const root='/Users/serg/Projects/SAMO/output/playwright/';
  const names=['Жизнь','Организм','Эволюция','Лаборатория','Изобретения','Память','Наука','О проекте'];
  const paths=['/','/organism','/evolution','/lab','/inventions','/memory','/science','/about'];
  const errors=[],checks=[],network=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
  page.on('request',r=>{if(!r.url().startsWith(base)&&!r.url().startsWith('data:'))network.push(r.url());});
  const check=(name,passed,detail)=>{checks.push({name,passed,detail});};
  await page.addInitScript(()=>{
    window.__vtCount=0;
    if(document.startViewTransition){const original=document.startViewTransition.bind(document);document.startViewTransition=(...args)=>{window.__vtCount++;return original(...args);};}
  });
  await page.setViewportSize({width:1440,height:1040});
  await page.goto(base);
  await page.getByRole('heading',{level:1}).filter({hasText:'Жизнь'}).waitFor();
  const snapshot=await (await page.request.get(base+'/data/snapshot.json')).json();
  await page.screenshot({path:root+'life-desktop.png',fullPage:true});
  async function navigate(i){
    if(await page.getByRole('button',{name:'Разделы',exact:true}).isVisible())await page.getByRole('button',{name:'Разделы',exact:true}).click();
    await page.getByRole('navigation',{name:'Основные разделы'}).getByRole('link',{name:names[i],exact:true}).click();
    await page.waitForFunction(path=>location.pathname===path,paths[i]);
    await page.waitForTimeout(340);
  }
  let pairs=0;
  for(let from=0;from<8;from++){
    await navigate(from);
    for(let to=0;to<8;to++){
      await navigate(to);
      check(`navigation ${names[from]} -> ${names[to]}`,await page.locator('main h1').count()===1);
      pairs++;
      await navigate(from);
    }
  }
  check('64 navigation pairs',pairs===64);
  check('native React ViewTransitions invoked',await page.evaluate(()=>window.__vtCount)>0,await page.evaluate(()=>window.__vtCount));
  for(let i=0;i<8;i++){
    await navigate(i);
    await page.screenshot({path:root+(paths[i]==='/'?'life':paths[i].slice(1))+'-desktop.png',fullPage:true});
  }
  await navigate(2);
  const graphHref=await page.locator('.graph-viewport a').first().getAttribute('href');
  await page.locator('.graph-viewport a').first().click();
  await page.waitForURL('**/organism/**');
  await page.getByRole('heading',{name:'Внутри организма',exact:true}).waitFor();
  check('graph node to organism',true);
  await page.reload();
  await page.getByRole('heading',{name:'Внутри организма',exact:true}).waitFor();
  check('nested route refresh',page.url().includes('/organism/'));
  await page.getByRole('link',{name:/^Испытание /}).click();
  await page.getByRole('heading',{name:'Карточка испытания',exact:true}).waitFor();
  check('organism to evidence',true);
  await page.reload();await page.getByRole('heading',{name:'Карточка испытания',exact:true}).waitFor();
  check('nested evidence refresh',true);
  await page.goto(base+graphHref);
  await page.getByRole('heading',{name:'Внутри организма',exact:true}).waitFor();
  check('direct nested link',true);
  await navigate(5);
  const later=page.getByLabel('Позже',{exact:true});
  const options=await later.locator('option').evaluateAll(opts=>opts.map(o=>o.value));
  if(options.length>1){await later.selectOption(options[1]);await page.waitForTimeout(350);check('historical state stored in URL',new URL(page.url()).searchParams.get('right')===options[1]);}
  await page.evaluate(()=>scrollTo(0,700));
  await page.waitForTimeout(100);
  const savedScroll=await page.evaluate(()=>scrollY);
  const memoryUrl=page.url();
  const scienceBox=await page.getByRole('navigation').getByRole('link',{name:'Наука',exact:true}).boundingBox();
  await page.mouse.click(scienceBox.x+scienceBox.width/2,scienceBox.y+scienceBox.height/2);
  await page.waitForFunction(()=>location.pathname==='/science');await page.waitForTimeout(350);
  await page.goBack();await page.waitForTimeout(350);
  check('Back restores historical URL',page.url()===memoryUrl);
  check('Back restores scroll',Math.abs((await page.evaluate(()=>scrollY))-savedScroll)<5,{saved:savedScroll,restored:await page.evaluate(()=>scrollY)});
  check('Back restores selected state',options.length<2||await page.getByLabel('Позже',{exact:true}).inputValue()===options[1]);
  await page.goForward();await page.waitForTimeout(350);check('Forward restores route',new URL(page.url()).pathname==='/science');
  await page.goto(base+'/unavailable');await page.getByRole('heading',{name:'Страница не найдена'}).waitFor();check('404 route',true);
  await page.goto(base+'/organism/missing');await page.getByRole('heading',{name:'Состояние не найдено'}).waitFor();check('unknown artifact',true);
  await page.goto(base+'/lab/missing');await page.getByRole('heading',{name:'Испытание не найдено'}).waitFor();check('unknown evidence',true);
  for(const width of [360,768,1440]){
    await page.setViewportSize({width,height:900});
    for(let i=0;i<8;i++){
      await navigate(i);
      const sizes=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,viewport:innerWidth}));
      check(`no page overflow ${width} ${paths[i]}`,sizes.scroll<=sizes.viewport,sizes);
    }
    if(width===360){await navigate(0);await page.screenshot({path:root+'life-mobile.png',fullPage:true});await navigate(2);await page.screenshot({path:root+'evolution-mobile.png',fullPage:true});}
  }
  await page.emulateMedia({reducedMotion:'reduce'});await navigate(0);await navigate(1);
  const motion=await page.locator('main').evaluate(el=>({animation:getComputedStyle(el).animationName,reduced:matchMedia('(prefers-reduced-motion: reduce)').matches}));
  check('reduced motion disables CSS animation',motion.reduced&&motion.animation==='none',motion);
  await page.emulateMedia({reducedMotion:'no-preference'});
  await page.goto(base);await page.getByRole('heading',{level:1}).filter({hasText:'Жизнь'}).waitFor();
  await page.keyboard.press('Tab');
  check('keyboard focus visible',await page.evaluate(()=>getComputedStyle(document.activeElement).outlineStyle!=='none'));
  await page.getByRole('navigation',{name:'Основные разделы'}).getByRole('link',{name:'Организм',exact:true}).focus();
  await page.keyboard.press('Enter');await page.getByRole('heading',{name:'Внутри организма',exact:true}).waitFor();
  check('keyboard navigation works',new URL(page.url()).pathname==='/organism');
  const session=await page.context().newCDPSession(page);
  await session.send('HeapProfiler.collectGarbage');
  const before=await session.send('Runtime.getHeapUsage');
  const domBefore=await session.send('Memory.getDOMCounters');
  for(let i=0;i<80;i++)await navigate(i%8);
  await session.send('HeapProfiler.collectGarbage');
  const after=await session.send('Runtime.getHeapUsage');
  const domAfter=await session.send('Memory.getDOMCounters');
  check('80-route navigation heap smoke',after.usedSize-before.usedSize<8_000_000,{before:before.usedSize,after:after.usedSize,domBefore,domAfter,limitBytes:8000000,scope:'smoke, not a long-running leak proof'});
  const empty={...snapshot,source_status:'empty',latest_observation_at:null,source_run_ids:[],runs:[],events:[],artifacts:{},evidence:[],protocols:[],claims:[]};
  await page.route('**/data/snapshot.json',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(empty)}));
  await page.goto(base);await page.getByRole('heading',{name:'Наблюдений пока нет',exact:true}).waitFor();check('empty archive honest',await page.locator('.specimen').count()===0);
  await page.screenshot({path:root+'empty-archive.png',fullPage:true});
  await page.unroute('**/data/snapshot.json');
  await page.route('**/data/snapshot.json',route=>route.fulfill({status:200,contentType:'application/json',body:'{"schema_version":999}'}));
  await page.goto(base);await page.getByRole('heading',{name:'Не удалось прочитать архив'}).waitFor();check('invalid schema rejected',true);
  await page.unroute('**/data/snapshot.json');
  await page.goto(base);await page.getByRole('heading',{level:1}).filter({hasText:'Жизнь'}).waitFor();
  check('stopped organism archive remains accessible',(await page.locator('.observation-line').innerText()).includes('Размножение прекратилось'));
  check('no external requests',network.length===0,network);
  check('no JavaScript errors',errors.length===0,errors);
  return {browser:await page.context().browser().version(),snapshotHash:snapshot.snapshot_hash,checks,passed:checks.filter(c=>c.passed).length,failed:checks.filter(c=>!c.passed),errors};
}
