"""Real stdio round-trip against source or a packaged MCP entry, using only temporary data."""
import argparse
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mcp import Client, StdioServerParameters


async def check(command=None, args=None):
    with tempfile.TemporaryDirectory(prefix="flow-mcp-check-") as profile:
        Path(profile, "settings.json").write_text(json.dumps({"name": "Demo", "model": "small", "auto_update": False,
            "api_key": "do-not-return-this-secret", "update_key": "do-not-return-this-secret"}), encoding="utf-8")
        environment = {**os.environ, "FLOW_DATA": profile}
        parameters = StdioServerParameters(command=command or sys.executable,
            args=args if args is not None else [str(Path(__file__).resolve().parents[1] / "main.py"), "--mcp"], env=environment)
        async with Client(parameters, read_timeout_seconds=30) as client:
            tools = await client.list_tools()
            names = {tool.name for tool in tools.tools}
            assert len(names) >= 35, names
            assert {"flow_configure", "flow_add_words", "flow_set_spoken_shortcut", "flow_recording", "flow_transcribe_file"} <= names
            async def call(name, arguments=None):
                result = await client.call_tool(name, arguments or {})
                assert not result.is_error, str(result)
                assert "do-not-return-this-secret" not in str(result)
                return result
            await call("flow_get_settings")
            await call("flow_configure", {"patch": {"name": "Alex", "languages": ["en"], "styles": {"work": "formal"}}})
            saved = json.loads(Path(profile, "settings.json").read_text("utf-8"))
            assert saved["name"] == "Alex" and saved["styles"]["work"] == "formal"
            await call("flow_add_words", {"words": ["Kubernetes", "Ijtihed"]})
            await call("flow_add_correction", {"heard": "itchy head", "correct": "Ijtihed"})
            await call("flow_set_spoken_shortcut", {"phrase": "my email", "expansion": "alex@example.com"})
            await call("flow_set_spoken_shortcut", {"phrase": "My Email", "expansion": "hello@example.com"})
            assert len(json.loads(Path(profile, "settings.json").read_text("utf-8"))["snippets"]) == 1
            await call("flow_list_spoken_shortcuts")
            await call("flow_get_dictionary")
            invalid = await client.call_tool("flow_configure", {"patch": {"tutorial_version": 2}})
            assert invalid.is_error
            invalid = await client.call_tool("flow_set_speech_engine", {"provider": "api", "model": "test-model", "key": "secret-test-key", "consent": False})
            assert invalid.is_error and "secret-test-key" not in str(invalid)
            resources = await client.list_resources()
            assert len(resources.resources) >= 6
            await client.read_resource("flow://settings")
            await client.read_resource("flow://dictionary")
            prompts = await client.list_prompts()
            assert len(prompts.prompts) >= 2
            await client.get_prompt("flow_personalize")
            await call("flow_remove_spoken_shortcut", {"phrase": "my email"})
            assert not json.loads(Path(profile, "settings.json").read_text("utf-8"))["snippets"]
        readonly = StdioServerParameters(command=parameters.command, args=[*parameters.args, "--read-only"], env=environment)
        async with Client(readonly, read_timeout_seconds=30) as client:
            for name, arguments in [("flow_configure", {"patch": {"name": "Changed"}}), ("flow_clear_history", {}),
                                    ("flow_recording", {"action": "start"}), ("flow_practice", {"action": "open"})]:
                result = await client.call_tool(name, arguments)
                assert result.is_error, name
            assert not (await client.call_tool("flow_get_settings", {})).is_error
            assert json.loads(Path(profile, "settings.json").read_text("utf-8"))["name"] == "Alex"
        extension = str(Path(__file__).resolve().parents[1] / "examples/mcp_extension.py")
        extended = StdioServerParameters(command=parameters.command, args=[*parameters.args, "--plugin", extension], env=environment)
        async with Client(extended, read_timeout_seconds=30) as client:
            tools = await client.list_tools()
            assert "flow_find_word" in {tool.name for tool in tools.tools}
            result = await client.call_tool("flow_find_word", {"query": "Ijtihed"})
            assert not result.is_error and "Ijtihed" in str(result)
        return {"ok": True, "tools": len(names), "resources": len(resources.resources), "prompts": len(prompts.prompts),
                "transport": "stdio", "profile": "temporary", "credential_redaction": "passed", "read_only": "enforced",
                "extensions": "passed", "audio": "not captured", "api": "no paid calls or uploads"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--command")
    parser.add_argument("--args", help="JSON array of launch arguments; [] for FlowMCP.exe.")
    parser.add_argument("--report")
    options = parser.parse_args()
    result = asyncio.run(check(options.command, json.loads(options.args) if options.args is not None else None))
    if options.report:
        Path(options.report).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))
