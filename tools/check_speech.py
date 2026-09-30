"""Run the actual local speech model against the bundled regression corpus."""
import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
parser=argparse.ArgumentParser()
parser.add_argument('--model',default='small')
parser.add_argument('--download',action='store_true')
parser.add_argument('--report',default='speech-regression.json')
args=parser.parse_args()
if args.download:
    from huggingface_hub import snapshot_download
    repos={'small':'Systran/faster-whisper-small','large-v3':'Systran/faster-whisper-large-v3','large-v3-turbo':'mobiuslabsgmbh/faster-whisper-large-v3-turbo'}
    model=snapshot_download(repos[args.model],allow_patterns=['model.bin','config.json','tokenizer.json','vocabulary.*','preprocessor_config.json'])
else:
    import setup_tasks
    model=setup_tasks.find_model(args.model)
    if not model: parser.error('Download this model first or use --download.')
from engine import Engine
from memory import Memory
import health
with tempfile.TemporaryDirectory() as folder:
    memory=Memory(Path(folder)/'memory.db',['en'])
    engine=Engine(memory)
    engine.load(model)
    report=health.check(engine,{'speech_provider':'local','model':args.model})
    Path(args.report).write_text(json.dumps(report,indent=2)+'\n','utf-8')
    print(json.dumps(report,indent=2),flush=True)
    memory.db.close()
    sys.exit(0 if report['status']=='passed' else 1)
