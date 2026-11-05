# Contributing

Use a feature branch and open a pull request. Include the concrete behavior change and relevant validation. All changes to main must pass Python, bridge, container-isolation and privacy checks. The maintainer uses squash merges and deletes merged branches.

```sh
python3 -m unittest discover -s tests -v
node --test tests/openclaw.test.mjs
DAFEIYU_TEST_DOCKER=1 python3 -m unittest discover -s tests -p test_docker.py -v
python3 scripts/privacy_audit.py
```

Install the pinned runtimes with `python3 scripts/setup_runtime.py` on macOS if needed. Docker integration tests require the fixed image documented in the workflow. Ordinary CI must never use live model credentials, a personal WeChat account or real companion data. Use temporary directories and fake identities in tests.

Keep provider/channel authentication in the official clients. Do not add cookie extraction, protocol bypasses, implicit paid fallbacks or host execution of generated code. Persona and long-term memory must stay distinguishable from verified facts and completed tool actions.

This repository contains original code under MIT. Respect third-party licenses; do not add community character images, sprites, voice samples or persona text without verified redistribution rights and attribution.
