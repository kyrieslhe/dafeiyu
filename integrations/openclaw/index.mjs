import {spawn} from 'node:child_process';

export function bridge(config, event, context) {
  return new Promise((resolve) => {
    const child = spawn(config.python, ['-m', 'dafeiyu.channel', '--home', config.home, 'inbound'], {
      cwd: config.project, stdio: ['pipe','pipe','pipe'], detached: true,
      env: {...process.env, PYTHONUNBUFFERED:'1'}
    });
    let stdout = '', done = false;
    const finish = text => { if (!done) { done = true; clearTimeout(timer); resolve({handled:true,text}); } };
    const timer = setTimeout(() => {
      try { process.kill(-child.pid, 'SIGTERM'); } catch {}
      finish('这次处理超时了，请稍后查看 /fish /tasks；我不会假装已经完成。');
    }, 115000);
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
      sender:context.senderId || event.senderId,
      message_id:context.messageId || event.messageId,
      group:Boolean(event.isGroup),
      text:event.content || event.body || ''
    }));
  });
}
export default {
  id:'dafeiyu-bridge', name:'大肥鱼',
  register(api) {
    const config=api.pluginConfig;
    api.on('before_dispatch', async (event, context) => {
      if ((context.channelId || event.channel)!=='openclaw-weixin') return {handled:false};
      return bridge(config,event,context);
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
