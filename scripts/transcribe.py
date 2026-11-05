#!/usr/bin/env python3
"""Private subprocess entry for offline, CPU-only speech recognition."""
import json
import fcntl
from pathlib import Path
import sys
from faster_whisper import WhisperModel

ROOT=Path(__file__).resolve().parent.parent
lock=(ROOT/'var/runtime/speech.lock').open('a')
try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
except BlockingIOError:raise SystemExit(2)
model=WhisperModel(str(ROOT/'var/runtime/speech-model'),device='cpu',compute_type='int8',cpu_threads=2,num_workers=1,local_files_only=True)
segments,info=model.transcribe(sys.argv[1],language='zh',beam_size=1,vad_filter=True,condition_on_previous_text=False)
text=''.join(segment.text for segment in segments).strip()
print(json.dumps({'text':text[:3000],'language':info.language},ensure_ascii=False))
