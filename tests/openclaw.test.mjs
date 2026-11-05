import test from 'node:test';
import assert from 'node:assert/strict';
import plugin, {bridge,stableSender,stableMessageId} from '../integrations/openclaw/index.mjs';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';

test('bridge registers public hooks with bounded timeout and no foreign-channel takeover', async()=>{
 const hooks={};const commands=[];
 plugin.register({pluginConfig:{},on:(name,fn,options)=>hooks[name]={fn,options},registerCommand:x=>commands.push(x)});
 assert.equal(hooks.before_dispatch.options.timeoutMs,120000);
 assert.deepEqual(await hooks.before_dispatch.fn({channel:'other'},{channelId:'other'}),{handled:false});
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
