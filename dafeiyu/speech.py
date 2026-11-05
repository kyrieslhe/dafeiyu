"""Optional offline ASR and local macOS file-only TTS. No paid service fallback."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid

ROOT=Path(__file__).resolve().parent.parent


def transcribe(path,runner=subprocess.run):
    python=ROOT/'var/runtime/speech/bin/python';model=ROOT/'var/runtime/speech-model/model.bin'
    if not python.exists() or not model.exists():raise ValueError('离线语音识别尚未安装，请在本机运行 scripts/setup_speech.py，或用微信转文字后发送。')
    env={'PATH':os.defpath,'HF_HOME':str(ROOT/'var/runtime/speech-cache'),'HF_HUB_OFFLINE':'1','HF_HUB_DISABLE_TELEMETRY':'1','HF_HUB_DISABLE_IMPLICIT_TOKEN':'1','OMP_NUM_THREADS':'2'}
    try:
        result=runner([str(python),str(ROOT/'scripts/transcribe.py'),path],env=env,capture_output=True,text=True,timeout=35)
        if result.returncode==2:raise ValueError('本鱼正在听另一条语音，请稍后再发。')
        if result.returncode:raise ValueError('本机语音识别失败；未上传音频，请用微信转文字后重发。')
        value=json.loads(result.stdout)
        text=value.get('text')
        if not isinstance(text,str) or not text.strip():raise ValueError('这条语音没有识别到清楚的文字，请重说一次。')
        return text.strip()[:3000]
    except subprocess.TimeoutExpired:raise ValueError('本机语音识别超时；请缩短语音或转文字后重发。') from None
    except (OSError,json.JSONDecodeError):raise ValueError('本机语音识别暂不可用；未使用付费服务。') from None


def synthesize(home,text,runner=subprocess.run):
    if sys.platform!='darwin':raise ValueError('当前朗读后端使用 macOS 系统声音；此主机尚未配置本地语音合成。')
    if not isinstance(text,str) or not 1<=len(text.strip())<=600:raise ValueError('朗读文字须为 1–600 字符。')
    root=Path(home).resolve()/'media/outbound';root.mkdir(mode=0o700,parents=True,exist_ok=True)
    destination=root/(uuid.uuid4().hex+'.wav')
    try:
        with tempfile.TemporaryDirectory(prefix='tts-',dir=root) as directory:
            source=Path(directory)/'text.txt';source.write_text(text);source.chmod(0o600)
            aiff=Path(directory)/'voice.aiff'
            result=runner(['/usr/bin/say','-v','Tingting','-r','185','-f',str(source),'-o',str(aiff)],capture_output=True,timeout=35)
            if result.returncode:raise ValueError('系统中文声音不可用，请检查 macOS 语音设置。')
            result=runner(['/usr/bin/afconvert','-f','WAVE','-d','LEI16@16000',str(aiff),str(destination)],capture_output=True,timeout=10)
            if result.returncode or not destination.exists() or not 44<destination.stat().st_size<=10*1024*1024:raise ValueError('语音文件生成失败或超出大小限制。')
            destination.chmod(0o600)
        return destination
    except (OSError,subprocess.TimeoutExpired):
        destination.unlink(missing_ok=True);raise ValueError('本机语音合成失败或超时，未生成可发送的音频。') from None
    except ValueError:
        destination.unlink(missing_ok=True);raise
