#!/usr/bin/env python3
"""Private subprocess entry for offline, CPU-only speech recognition."""
import json
import argparse
import fcntl
from pathlib import Path
import sys
import wave
import numpy as np
from faster_whisper import WhisperModel

parser=argparse.ArgumentParser();parser.add_argument('path');parser.add_argument('--language',choices=['zh','en','auto'],default='zh');args=parser.parse_args()

ROOT=Path(__file__).resolve().parent.parent
lock=(ROOT/'var/runtime/speech.lock').open('a')
try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
except BlockingIOError:raise SystemExit(2)
model=WhisperModel(str(ROOT/'var/runtime/speech-model'),device='cpu',compute_type='int8',cpu_threads=2,num_workers=1,local_files_only=True)
# Decode only bounded PCM WAV with stdlib; no network/codec format guessing.
with wave.open(args.path,'rb') as source:
    rate=source.getframerate();channels=source.getnchannels();frames=source.getnframes()
    if source.getsampwidth()!=2 or channels not in (1,2) or not 8000<=rate<=48000 or not 0<frames/rate<=60:raise SystemExit(1)
    raw=source.readframes(frames)
    if len(raw)!=frames*channels*2:raise SystemExit(1)
    audio=np.frombuffer(raw,dtype='<i2').astype(np.float32).reshape(-1,channels).mean(axis=1)/32768.0
    if rate!=16000:
        audio=np.interp(np.arange(round(len(audio)*16000/rate))*rate/16000,np.arange(len(audio)),audio).astype(np.float32)
segments,info=model.transcribe(audio,language=None if args.language=='auto' else args.language,beam_size=1,vad_filter=True,condition_on_previous_text=False)
uncertain=args.language=='auto' and info.language_probability<.5
text='' if uncertain else ''.join(segment.text for segment in segments).strip()
print(json.dumps({'text':text[:3000],'language':info.language,'language_probability':info.language_probability,'uncertain_language':uncertain},ensure_ascii=False))
