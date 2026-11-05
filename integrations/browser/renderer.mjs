import {chromium} from './node_modules/playwright-core/index.mjs';
import {createInterface} from 'node:readline';
import {writeFile} from 'node:fs/promises';

const rl=createInterface({input:process.stdin});
const waiting=new Map();let sequence=0;let initResolve;
const initialized=new Promise(resolve=>initResolve=resolve);
function send(value){process.stdout.write(JSON.stringify(value)+'\n');}
rl.on('line',line=>{
 try {
  const item=JSON.parse(line);
  if(item.type==='init')initResolve(item);
  else if(item.type==='resource' && waiting.has(item.id)){waiting.get(item.id)(item);waiting.delete(item.id);}
 }catch{}
});
let browser;
try {
 const {url}=await initialized;
 browser=await chromium.launch({headless:true,chromiumSandbox:true,timeout:15000});
 const context=await browser.newContext({viewport:{width:1280,height:800},serviceWorkers:'block',acceptDownloads:false,permissions:[]});
 await context.route('**/*',async route=>{
  const request=route.request();let parsed;
  try{parsed=new URL(request.url());}catch{return route.abort();}
  if(request.method()!=='GET'||parsed.protocol!=='https:')return route.abort();
  const id=++sequence;
  if(id>32)return route.abort();
  const response=new Promise(resolve=>waiting.set(id,resolve));
  send({type:'fetch',id,url:request.url(),resourceType:request.resourceType()});
  const item=await response;
  try {
   if(item.ok)await route.fulfill({status:item.status,headers:item.headers,body:Buffer.from(item.body,'base64')});
   else await route.abort();
  }catch{}
 });
 await context.routeWebSocket('**/*',ws=>ws.close());
 const page=await context.newPage();context.on('page',other=>{if(other!==page)other.close().catch(()=>{});});
 page.on('dialog',dialog=>dialog.dismiss().catch(()=>{}));
 let partial=false;
 try{await page.goto(url,{waitUntil:'domcontentloaded',timeout:25000});}catch{partial=true;}
 await page.waitForTimeout(300);
 const current=page.url();
 if(!current.startsWith('https://'))throw new Error('Page did not reach a public HTTPS document');
 const text=(await page.locator('body').innerText({timeout:3000})).slice(0,10000);
 const links=await page.locator('a[href]').evaluateAll(nodes=>nodes.slice(0,120).map(n=>({text:(n.innerText||n.textContent||'').trim().slice(0,100),url:n.href.slice(0,2000)})).filter(x=>x.url.startsWith('https://')));
 await page.screenshot({path:'/output/screenshot.png',timeout:5000});
 const result={type:'page',url:current,title:await page.title(),text,links,partial,browser:browser.version()};
 await writeFile('/output/page.json',JSON.stringify(result));
 await browser.close();browser=undefined;send(result);
}catch(error){send({type:'error',message:'隔离浏览器未能完成页面渲染。'});process.exitCode=1;}
finally{if(browser)await browser.close().catch(()=>{});rl.close();process.stdin.destroy();}
