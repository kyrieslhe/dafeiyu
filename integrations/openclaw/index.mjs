import {spawn} from 'node:child_process';

export function stableSender(event, context) {
  // Tencent 2.4.10 sets From=To=OriginatingTo=from_user_id, but omits SenderId.
  // OpenClaw 2026.10.10 projects OriginatingTo into conversationId without lowercasing.
  const directPeer = event.isGroup === false && /^[A-Za-z0-9_-]+@im\.wechat$/.test(context.conversationId || '') ? context.conversationId : undefined;
  return context.senderId || event.senderId || directPeer;
}

export function stableMessageId(event, context) {
  const id=context.messageId || event.messageId;
  // Generated fallback MessageSid values change across duplicate deliveries.
  return typeof id==='string' && id && !id.startsWith('openclaw-weixin') ? id : undefined;
}

export function inboundFromDispatch(event) {
  const ctx=event.ctx || {};
  const paths=ctx.MediaPaths || (ctx.MediaPath ? [ctx.MediaPath] : []);
  return {
    event:{content:ctx.CommandBody ?? ctx.RawBody ?? ctx.Body ?? '',isGroup:ctx.ChatType!=='direct',
      media:paths.slice(0,3).map((path,index)=>({path,mime:ctx.MediaTypes?.[index] || ctx.MediaType || ''}))},
    context:{channelId:ctx.OriginatingChannel || ctx.Provider,accountId:ctx.AccountId,
      conversationId:ctx.OriginatingTo || ctx.From,senderId:ctx.SenderId,
      messageId:ctx.MessageSidFull || ctx.MessageSid}
  };
}

export function bridge(config, event, context, abortSignal) {
  if (abortSignal?.aborted) return Promise.resolve({handled:true,text:'本次处理已取消。'});
  return new Promise((resolve) => {
    const child = spawn(config.python, ['-m', 'dafeiyu.channel', '--home', config.home, 'inbound'], {
      cwd: config.project, stdio: ['pipe','pipe','pipe'], detached: true,
      env: {...process.env, PYTHONUNBUFFERED:'1'}
    });
    let stdout = '', done = false;
    const finish = text => { if (!done) { done = true; clearTimeout(timer); abortSignal?.removeEventListener('abort',abort); resolve({handled:true,text}); } };
    const timer = setTimeout(() => {
      try { process.kill(-child.pid, 'SIGTERM'); } catch {}
      finish('这次处理超时了，请稍后查看 /fish /tasks；我不会假装已经完成。');
    }, 115000);
    const abort=()=>{try {process.kill(-child.pid,'SIGTERM');} catch {} finish('本次处理已取消。');};
    abortSignal?.addEventListener('abort',abort,{once:true});
    if (abortSignal?.aborted) abort();
    child.stdout.on('data', data => {
      stdout += data;
      if (stdout.length > 1000000) { try {process.kill(-child.pid,'SIGTERM');} catch {} finish('回复超过限制，请在本机查看成果。'); }
    });
    // Do not forward logs, credentials or raw internal errors into WeChat.
    child.stderr.resume();
    child.on('error', () => finish('本地大肥鱼服务不可用。'));
    child.on('close', code => {
      try { finish(code===0 ? JSON.parse(stdout).text : '本地处理失败，请在本机检查状态。'); }
      catch { finish('本地回复格式异常。'); }
    });
    child.stdin.on('error', () => {});
    child.stdin.end(JSON.stringify({
      channel:context.channelId || event.channel,
      account:context.accountId,
      sender:stableSender(event,context),
      message_id:stableMessageId(event,context),
      group:event.isGroup !== false,
      text:event.content || event.body || '',
      media:event.media || []
    }));
  });
}
export default {
  id:'dafeiyu-bridge', name:'大肥鱼',
  register(api) {
    const config=api.pluginConfig;
    api.on('reply_dispatch', async (event, context) => {
      const input=inboundFromDispatch(event);
      if (input.context.channelId!=='openclaw-weixin') return {handled:false};
      if (event.isTailDispatch) return {handled:false};
      if (event.sendPolicy==='deny' || event.suppressUserDelivery) {
        context.recordProcessed?.('skipped',{reason:'dafeiyu_delivery_suppressed'});
        return {handled:true,queuedFinal:false,counts:{tool:0,block:0,final:0}};
      }
      await context.turnAdoption?.adopt();
      let response;
      try { response=await bridge(config,input.event,input.context,context.abortSignal); }
      catch { response={text:'本地大肥鱼服务暂时不可用，请在本机检查状态。'}; }
      context.turnAdoption?.assertCurrent();
      const queuedFinal=context.dispatcher.sendFinalReply({text:response.text});
      context.recordProcessed?.(queuedFinal?'completed':'error',{reason:queuedFinal?'dafeiyu_reply_queued':'dafeiyu_reply_not_queued'});
      context.markIdle?.('dafeiyu_reply_finished');
      return {handled:true,queuedFinal,counts:context.dispatcher.getQueuedCounts()};
    }, {timeoutMs:120000,priority:1000});
    api.registerCommand({name:'fish',description:'和大肥鱼聊天或管理任务',acceptsArgs:true,requireAuth:true,
      handler:async ctx => {
        if ((ctx.channelId || ctx.channel)!=='openclaw-weixin') return {text:'仅用于已绑定的微信私聊。'};
        // Native commands lack a stable message ID in this SDK. Only expose read-only help here;
        // normal inbound text carries provider IDs and performs all stateful operations.
        return {text:'直接发送普通文字和我聊天。管理命令请写成「大肥鱼 /命令 参数」，例如「大肥鱼 /tasks」。'};
      }});
    api.on('before_agent_run', (_event, context) => {
      // No fallback model runtime should bypass the bridge's identity and permission checks.
      if (String(context.sessionKey || '').includes('openclaw-weixin')) return {outcome:'block',reason:'微信只通过大肥鱼身份桥处理。'};
    });
  }
};
