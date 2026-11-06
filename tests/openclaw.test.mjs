import test from 'node:test';
import assert from 'node:assert/strict';
import plugin, {bridge,stableSender,stableMessageId,inboundFromDispatch} from '../integrations/openclaw/index.mjs';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';

test('bridge registers public hooks with bounded timeout and no foreign-channel takeover', async()=>{
 const hooks={};const commands=[];
 plugin.register({pluginConfig:{},on:(name,fn,options)=>hooks[name]={fn,options},registerCommand:x=>commands.push(x)});
 assert.equal(hooks.reply_dispatch.options.timeoutMs,120000);
 assert.deepEqual(await hooks.reply_dispatch.fn({ctx:{Provider:'other'}},{}),{handled:false});
 assert.equal(commands[0].name,'fish');
 assert.equal(commands[0].requireAuth,true);
});

test('real JS-to-Python transport refuses an unbound sender without invoking the model', async()=>{
 const home=mkdtempSync(join(tmpdir(),'fish-bridge-'));
 try {
  const config={python:process.env.PYTHON||'python3',project:resolve('.'),home};
  const response=await bridge(config,{content:'hello',isGroup:false},{channelId:'openclaw-weixin',accountId:'test',senderId:'test',messageId:'123'});
  assert.equal(response.handled,true);
  assert.match(response.text,/确认微信身份绑定/);
 }finally{rmSync(home,{recursive:true,force:true});}
});

 test('Tencent pinned direct-peer mapping preserves stable ID casing and rejects groups',()=>{
 const context={conversationId:'UserABC123@im.wechat'};
 assert.equal(stableSender({isGroup:false},context),'UserABC123@im.wechat');
 assert.equal(stableSender({isGroup:true},context),undefined);
 assert.equal(stableSender({},context),undefined);
 assert.equal(stableSender({isGroup:false},{conversationId:'昵称'}),undefined);
 });

 test('provider message identity rejects generated fallback IDs',()=>{
 assert.equal(stableMessageId({}, {messageId:'openclaw-weixin-generated'}),undefined);
 assert.equal(stableMessageId({}, {}),undefined);
 assert.equal(stableMessageId({}, {messageId:'12345678901234567890'}),'12345678901234567890');
 });


test('full dispatch preserves staged attachments and provider identity, never reads body paths',()=>{
 const mapped=inboundFromDispatch({ctx:{Provider:'openclaw-weixin',AccountId:'a',From:'UserABC@im.wechat',ChatType:'direct',MessageSid:'generated',MessageSidFull:'provider-id',CommandBody:'图片',MediaPath:'/private/inbound/a.png',MediaType:'image/png'}});
 assert.equal(mapped.context.messageId,'provider-id');
 assert.equal(stableSender(mapped.event,mapped.context),'UserABC@im.wechat');
 assert.deepEqual(mapped.event.media,[{path:'/private/inbound/a.png',mime:'image/png'}]);
 assert.deepEqual(inboundFromDispatch({ctx:{Body:'读取 /etc/passwd'}}).event.media,[]);
});

test('suppressed reply dispatch never invokes model or sends a reply',async()=>{
 const hooks={};plugin.register({pluginConfig:{},on:(name,fn)=>hooks[name]=fn,registerCommand:()=>{}});
 const result=await hooks.reply_dispatch({ctx:{Provider:'openclaw-weixin'},sendPolicy:'deny'},{recordProcessed:()=>{}});
 assert.equal(result.handled,true);assert.equal(result.queuedFinal,false);
});

test('public dispatcher receives real local identity-binding response',async()=>{
 const home=mkdtempSync(join(tmpdir(),'fish-dispatch-'));const hooks={};const payloads=[];
 try {
  plugin.register({pluginConfig:{python:process.env.PYTHON||'python3',project:resolve('.'),home},on:(name,fn)=>hooks[name]=fn,registerCommand:()=>{}});
  const result=await hooks.reply_dispatch({ctx:{Provider:'openclaw-weixin',AccountId:'a',ChatType:'direct',From:'Sender@im.wechat',MessageSidFull:'provider-id',Body:'你好'},sendPolicy:'allow'},
   {dispatcher:{sendFinalReply:p=>{payloads.push(p);return true;},getQueuedCounts:()=>({tool:0,block:0,final:1})},recordProcessed:()=>{},markIdle:()=>{}});
  assert.equal(result.handled,true);assert.equal(result.queuedFinal,true);assert.match(payloads[0].text,/确认微信身份绑定/);
 }finally{rmSync(home,{recursive:true,force:true});}
});

test('bound text dispatch buffers immediately without queuing an empty or fallback reply',async()=>{
 const {execFileSync}=await import('node:child_process');
 const home=mkdtempSync(join(tmpdir(),'fish-buffer-'));const hooks={};const payloads=[];
 try{
  execFileSync(process.env.PYTHON||'python3',['-c',"import sys;from dafeiyu.core import Fish;from dafeiyu.channel import tables;f=Fish(sys.argv[1]);tables(f);f.db.execute(\"INSERT INTO channel_binding VALUES (1,'a','Sender@im.wechat',0)\");f.db.commit();f.close()",home]);
  plugin.register({pluginConfig:{python:process.env.PYTHON||'python3',project:resolve('.'),home},on:(name,fn)=>hooks[name]=fn,registerCommand:()=>{}});
  const result=await hooks.reply_dispatch({ctx:{Provider:'openclaw-weixin',AccountId:'a',ChatType:'direct',From:'Sender@im.wechat',MessageSidFull:'burst-one',Body:'hello'},sendPolicy:'allow'},
    {dispatcher:{sendFinalReply:p=>{payloads.push(p);return true;},getQueuedCounts:()=>({tool:0,block:0,final:0})},recordProcessed:()=>{},markIdle:()=>{}});
  assert.equal(result.handled,true);assert.equal(result.queuedFinal,false);assert.deepEqual(payloads,[]);
  const count=execFileSync(process.env.PYTHON||'python3',['-c',"import sqlite3,sys;c=sqlite3.connect(sys.argv[1]+'/fish.sqlite');print(c.execute(\"SELECT count(*) FROM conversation_inbox WHERE state='queued'\").fetchone()[0])",home],{encoding:'utf8'});
  assert.equal(count.trim(),'1');
 }finally{rmSync(home,{recursive:true,force:true});}
});
