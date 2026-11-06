#!/usr/bin/env python3
"""Activate verified code only while idle; roll back code/config on failed readiness."""
import argparse
import fcntl
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import time

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from dafeiyu.deployment import prepare,selected,verify,configure,write


def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/(name+'.py'))
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


def activate(commit):
    release=verify(ROOT,commit);services=module('services');supervisor=module('supervise')
    with (ROOT/'var/services.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if (ROOT/'var/services.paused').exists():raise ValueError('服务已明确暂停，未切换。')
        db=sqlite3.connect(ROOT/'var/fish.sqlite',timeout=10)
        try:
            db.execute('BEGIN IMMEDIATE')
            busy=db.execute("SELECT count(*) FROM tasks WHERE state IN ('running','applying')").fetchone()[0]
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='inbound'").fetchone():busy+=db.execute("SELECT count(*) FROM inbound WHERE state='running'").fetchone()[0]
            if busy:raise ValueError('有聊天或任务运行，未切换，请稍后重试。')
            config_path=ROOT/'var/gateway/openclaw.json';config=json.loads(config_path.read_text())
            receipt=ROOT/'var/active-release.json';old=json.loads(receipt.read_text()) if receipt.exists() else None
            if old and old['commit']==commit:
                print('已运行该版本，未重启服务。');return
            selected(ROOT)
            updated=configure(json.loads(json.dumps(config)),release,ROOT)
            services.control(argparse.Namespace(action='stop',internal=True))
            db.rollback();db.close();db=None
            try:
                write(config_path,updated);write(receipt,{'commit':commit,'previous':old.get('commit') if old else None})
                services.control(argparse.Namespace(action='start',internal=True))
                for _ in range(12):
                    records=services.state()
                    if len(records)==2 and all(services.active(e) for e in records.values()) and all(supervisor.probe()):break
                    time.sleep(1)
                else:raise ValueError('新版本渠道健康检查未通过。')
            except BaseException:
                services.control(argparse.Namespace(action='stop',internal=True));write(config_path,config)
                if old is None:receipt.unlink(missing_ok=True)
                else:write(receipt,old)
                services.control(argparse.Namespace(action='start',internal=True))
                raise
        finally:
            if db is not None:db.rollback();db.close()
    print('代码版本已切换：'+commit+'；未回滚数据库或复制登录凭据。')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','activate','rollback','status']);parser.add_argument('commit',nargs='?');args=parser.parse_args()
    if args.action=='prepare':print(prepare(ROOT).name)
    elif args.action=='status':print(selected(ROOT))
    elif args.action=='rollback':
        receipt=json.loads((ROOT/'var/active-release.json').read_text())
        if not receipt.get('previous'):raise ValueError('没有上一份独立版本。')
        activate(receipt['previous'])
    elif args.commit:activate(args.commit)
    else:parser.error('activate 需要版本提交编号')

if __name__=='__main__':
    try:main()
    except (ValueError,OSError,KeyError):raise SystemExit('部署未完成；请检查版本、配置和空闲状态。启动失败会尝试恢复原版本，详情请检查本机服务状态。')
