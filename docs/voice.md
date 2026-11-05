# 语音输入与朗读

语音转写在本机离线执行，朗读用 macOS 系统声音；不接入付费语音 API。转写后的聊天仍通过官方 Codex CLI，消耗原有账号额度。它不是声音克隆，也不冒充原生微信语音气泡。

## 安装可选离线识别

```sh
python3 scripts/setup_speech.py
```

核心仍是零第三方 Python 依赖；可选识别单独安装在私人 `var/runtime/speech`。安装器要求 Python 3.12–3.13；Mac arm64 在系统 Python 较旧时，自动下载固定 Astral python-build-standalone 3.12.16（20261026），校验已记录的 GitHub SHA256，解压到本项目，不替换系统 Python。其他平台请使用 Python 3.12–3.13 执行安装器。

依赖版本和 PyPI wheel 哈希锁在 `integrations/speech/requirements.txt`，仅装二进制 wheel。识别模型是 Systran 转换的 Whisper small，固定 revision，约 484MB；每个资产按上游 Git blob/LFS SHA256 校验。首次安装需要网络和磁盘空间，运行时只读取本地模型，禁用 Hugging Face 在线下载及遥测，不继承 API 密钥。

微信插件须先把语音下载、解码成 WAV，才可由桥接处理。支持最多 60 秒、12MB、16 位 PCM WAV，单声道或双声道、8–48kHz。本机在独立进程中用标准库解析 PCM、重采样为 16kHz，CPU 两线程，识别最多 35 秒；不对上传音频调用通用外部编解码器，不下载模型代码。原始 SILK 或无法解码的音频会明确提示改用微信转文字。

识别文字会标明转写来源；模型可能听错。语音可聊天、回忆、查看任务和请求研究，但写长期记忆、创建提醒、修改项目等动作要求文字确认。平台自己已经转成文字的语音按平台文字上下文处理，不声称本地重新识别。

## 让大肥鱼说话

在微信发送：

```text
用语音跟我说句晚安。
大肥鱼 /speak 今天也辛苦啦，早点休息呀。
```

应用入队本机朗读任务，使用已安装的 Tingting 中文系统声音生成 WAV，不会在电脑扬声器上自动播放。发送遵守同一 owner 绑定、真实新来信窗口、安静时间和投递去重。当前腾讯插件将音频发送为可播放/下载的文件附件，**未实现原生语音气泡**；具体微信播放表现仍需真实平台验证。

音频在 `var/media/outbound` 保留七天，过期附件不会冒充已发送或盲目重发。音频不包含在原有数据库/报告加密快照中，恢复后可能需要重新生成。状态 `accepted` 只表示渠道调用接受，不代表已读。没有可用声音或识别失败时明确报错，不切换付费服务。

## 实际验证

本机真实完成中文文件朗读→离线转写，正确识别了测试句子。原 Python 3.9 的依赖扫描命中 AnyIO、filelock、fsspec 公告，未沿用该环境；新 Python 3.12 运行时使用修复版本，OSV 按安装的 23 个版本查询，当时未返回已知匹配。这只是当时的公告检查，不保证没有未知漏洞。

可选本机检查：

```sh
DAFEIYU_TEST_SPEECH=1 python3 -m unittest discover -s tests -p test_speech.py -v
```

参考：[faster-whisper](https://github.com/SYSTRAN/faster-whisper)、[模型来源](https://huggingface.co/Systran/faster-whisper-small)、[独立 Python 来源](https://github.com/astral-sh/python-build-standalone)。微信端到端入站语音、音频附件播放仍待真实消息验证。
