"""Known-audio startup checks. Reports contain fixtures, never user dictations."""
import importlib.metadata
import json
import platform
import tempfile
import time
import wave
from pathlib import Path

import numpy as np
import paths
import control
from version import APP_VERSION


def words(text):
    value = control.normalized(text)
    for old,new in (("git hub","github"),("chat gpt","chatgpt")):
        value=value.replace(old,new)
    return value.split()


def error_rate(expected, actual):
    a,b=words(expected),words(actual)
    previous=list(range(len(b)+1))
    for i,word in enumerate(a,1):
        current=[i]
        for j,got in enumerate(b,1):
            current.append(min(current[-1]+1,previous[j]+1,previous[j-1]+(word!=got)))
        previous=current
    return previous[-1]/max(1,len(a))


def baseline(settings, status):
    versions={}
    for package in ('faster-whisper','ctranslate2','onnxruntime'):
        try: versions[package]=importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError: pass
    return {'schema':1,'version':APP_VERSION,'checked_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
            'platform':platform.system(),'provider':settings.get('speech_provider','local'),
            'model':settings.get('api_model') if settings.get('speech_provider')=='api' else settings.get('model','large-v3'),
            'status':status,'runtime':versions,
            'privacy':'Only bundled test audio and its transcripts; no personal recordings, history, names, keys or file paths.'}


def check(engine, settings):
    report=baseline(settings,'checking')
    if settings.get('speech_provider')=='api':
        report.update(status='not_run',reason='API speech is tested with the interactive spoken practice. No automatic paid request was made.')
        return report
    start=time.monotonic()
    try:
        from engine import Engine
        from memory import Memory
        manifest=json.loads((paths.APP/'assets/speech-check/manifest.json').read_text('utf-8'))
        with tempfile.TemporaryDirectory() as folder:
            memory=Memory(Path(folder)/'memory.db',['en'])
            try:
                probe=Engine(memory)
                probe.whisper=engine.whisper
                probe.device=engine.device
                checks=[]
                for fixture in manifest['fixtures']:
                    file=paths.APP/'assets/speech-check'/fixture['file']
                    with wave.open(str(file)) as wav:
                        if wav.getframerate()!=16000 or wav.getnchannels()!=1 or wav.getsampwidth()!=2:
                            raise ValueError('Invalid bundled test audio')
                        audio=np.frombuffer(wav.readframes(wav.getnframes()),dtype=np.int16).astype(np.float32)/32768
                    text,lang=probe.transcribe(audio,{'speech_provider':'local','languages':['en']})
                    rate=error_rate(fixture['text'],text)
                    required=all(word in words(text) for word in fixture.get('required',[]))
                    checks.append({'fixture':fixture['id'],'expected':fixture['text'],'heard':text,
                                   'word_error_rate':round(rate,3),'passed':rate<=fixture.get('max_word_error_rate',.2) and required})
                report.update(status='passed' if checks and all(c['passed'] for c in checks) else 'failed',
                              device=engine.device,checks=checks)
            finally:
                memory.db.close()
    except Exception as error:
        # Exception messages can contain paths, URLs or secrets. Retain the type only.
        report.update(status='failed',error_type=type(error).__name__,reason='The bundled speech check could not complete.')
    report['seconds']=round(time.monotonic()-start,2)
    return report


def save(report):
    control.atomic_json(paths.DATA/'speech-check.json',report)


def current():
    value=control.read_json(paths.DATA/'speech-check.json')
    return value if value.get('version')==APP_VERSION else {'status':'checking','version':APP_VERSION}


def failed_load(settings, error):
    report=baseline(settings,'failed')
    report.update(error_type=type(error).__name__,reason='The selected speech model could not load.')
    save(report)
    return report


def failed_transcription(settings, error_type):
    report=baseline(settings,'failed')
    report.update(error_type=error_type if error_type.isidentifier() else 'SpeechError',
                  reason='The speech engine could not transcribe a recording. No recording or user transcript is included in this report.')
    save(report)
