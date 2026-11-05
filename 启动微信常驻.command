#!/bin/zsh
set -eu
cd "${0:A:h}"
export PATH="/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS:/opt/homebrew/bin:$PATH"
python3 scripts/stay_online.py start --keep-awake
python3 scripts/stay_online.py status
print '🐳 微信常驻监管已启动，可以关闭这个窗口。接电时保持唤醒；合盖、断网、退出登录或关机仍可能离线。'
