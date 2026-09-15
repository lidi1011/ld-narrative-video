import {createRequire} from 'node:module';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
const root=resolve(process.argv[2]);
let browser;
try {
  const require=createRequire(resolve(root,'node_modules/hyperframes/package.json'));
  const puppeteer=require('puppeteer-core');
  const options=process.env.NARRATIVE_VIDEO_CHROME ? {executablePath:process.env.NARRATIVE_VIDEO_CHROME} : {channel:'chrome'};
  browser=await puppeteer.launch({...options,headless:true});
  const page=await browser.newPage();
  await page.goto(pathToFileURL(resolve(root,'index.html')).href,{waitUntil:'networkidle0',timeout:30000});
  const result=await page.evaluate(async()=>{
    await document.fonts.load('28px "Noto Sans CJK SC"','中文');
    await document.fonts.ready;
    const faces=[...document.fonts].filter(f=>f.family.replaceAll('"','')==='Noto Sans CJK SC');
    const fontLoaded=faces.length>0 && faces.every(f=>f.status==='loaded');
    if(!fontLoaded)throw Error('Bundled Chinese font failed to load');
    return {fontLoaded,timeline:!!window.__timelines?.main};
  });
  if(!result.timeline)throw Error('Missing main timeline; build index.html first');
  console.log(JSON.stringify(result));
} catch(e) { console.error(e.message);process.exitCode=1; }
finally { if(browser)await browser.close(); }
