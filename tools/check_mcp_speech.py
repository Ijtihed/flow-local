"""Exercise real file transcription through MCP with bundled audio and a temporary profile.

Requires an already cached model; never records the microphone or calls an API.
"""
import argparse
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mcp import Client, StdioServerParameters
from health import error_rate, words


async def check(model="small", command=None, args=None):
    manifest = json.loads((ROOT / "assets/speech-check/manifest.json").read_text("utf-8"))
    with tempfile.TemporaryDirectory(prefix="flow-mcp-speech-") as profile:
        Path(profile, "settings.json").write_text(json.dumps({"name": "Alex", "model": model,
            "speech_provider": "local", "languages": ["en"], "cleanup": False, "auto_update": False}), encoding="utf-8")
        parameters = StdioServerParameters(command=command or sys.executable,
            args=args if args is not None else [str(ROOT / "main.py"), "--mcp"],
            env={**os.environ, "FLOW_DATA": profile, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"})
        checks = []
        async with Client(parameters, read_timeout_seconds=180) as client:
            for fixture in manifest["fixtures"]:
                result = await client.call_tool("flow_transcribe_file", {"file": str(ROOT / "assets/speech-check" / fixture["file"]), "category": "email"})
                if result.is_error:
                    raise RuntimeError(str(result))
                payload = result.structured_content or json.loads(next(block.text for block in result.content if block.type == "text"))
                heard = payload["text"]
                rate = error_rate(fixture["text"], heard)
                required = all(word in words(heard) for word in fixture.get("required", []))
                checks.append({"fixture": fixture["id"], "expected": fixture["text"], "heard": heard,
                    "word_error_rate": round(rate, 3), "passed": rate <= fixture["max_word_error_rate"] and required})
        return {"ok": bool(checks) and all(c["passed"] for c in checks), "model": model, "checks": checks,
            "profile": "temporary", "audio": "bundled fixtures only", "api": "no calls or uploads"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="small")
    parser.add_argument("--command")
    parser.add_argument("--args", help="JSON launch arguments; [] for FlowMCP.exe.")
    parser.add_argument("--report", default="mcp-speech-regression.json")
    options = parser.parse_args()
    report = asyncio.run(check(options.model, options.command, json.loads(options.args) if options.args is not None else None))
    Path(options.report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    sys.exit(0 if report["ok"] else 1)
