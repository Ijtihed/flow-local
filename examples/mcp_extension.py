"""Load explicitly with FlowMCP.exe --plugin /absolute/path/mcp_extension.py."""
from mcp.types import ToolAnnotations


def register(server, service):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False))
    def flow_find_word(query: str) -> list[dict]:
        """Find personal vocabulary containing this text, ignoring case."""
        return [term for term in service.api.memory()["terms"] if query.casefold() in term["text"].casefold()]
