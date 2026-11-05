import argparse
import json
import time
from .core import Fish, HELP, ModelError


def main():
    parser = argparse.ArgumentParser(description='🐳 大肥鱼私人伙伴')
    parser.add_argument('--home', default='var', help='私人数据目录（默认 ./var）')
    parser.add_argument('mode', nargs='?', default='chat', choices=['chat', 'worker', 'doctor', 'setup', 'run'])
    parser.add_argument('message', nargs='?', help='run 模式执行单条命令')
    parser.add_argument('--once', action='store_true', help='worker 只处理一个到期任务')
    args = parser.parse_args()
    fish = Fish(args.home)
    def show(value):
        print(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2))
    try:
        if args.mode in ('setup', 'doctor'):
            show(fish.command('/status'))
        elif args.mode == 'run':
            show(fish.command(args.message or '/help'))
        elif args.mode == 'worker':
            while True:
                identifier = fish.tick()
                if identifier:
                    print('processed ' + identifier, flush=True)
                if args.once:
                    break
                time.sleep(1)
        else:
            print(HELP)
            while True:
                try:
                    text = input('\n你 > ').strip()
                    if text == '/quit':
                        break
                    if text:
                        show(fish.command(text))
                except (ValueError, ModelError) as error:
                    print(str(error))
    except (EOFError, KeyboardInterrupt):
        print('\n🐳 下次见，记忆会留在这里。')
    except (ValueError, ModelError) as error:
        print(str(error))
        raise SystemExit(1)
    finally:
        fish.close()


if __name__ == '__main__':
    main()
