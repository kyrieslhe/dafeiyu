#!/bin/zsh
cd "${0:A:h}" || exit 1
export PATH="/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS:/opt/homebrew/bin:$PATH"
python3 -m dafeiyu
