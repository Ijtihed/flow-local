"""Bundled app identities. No titles are stored or sent to a remote service."""
import json
import re
from paths import APP

CATALOG = json.loads((APP / "assets/apps.json").read_text("utf-8"))
BY_ID = {app["id"]: app for app in CATALOG}
ALIASES = {alias.casefold(): app["id"] for app in CATALOG for alias in app["aliases"]}
BROWSERS = {"firefox", "chrome", "edge", "brave", "opera", "vivaldi"}
TITLE_PATTERNS = [
    (app["id"], re.compile(r"(?:^|\s[-–—|•:]\s*|\|\s*)" + re.escape(title) +
                          r"(?=$|\s*[-–—|•:]\s)", re.I))
    for app in CATALOG if app["id"] not in BROWSERS for title in app["titles"]
]


def canonical_app(process):
    name = (process or "").casefold().removesuffix(".exe")
    return ALIASES.get(name, name)


def resolve_app(foreground):
    process, title = foreground
    ident = canonical_app(process)
    # Desktop notes and documents may mention any other app. Only browser tabs
    # and browser-hosted PWAs need a title override, matched at a brand separator.
    if ident in BROWSERS or process.casefold() in {"chrome_proxy", "msedge_proxy"}:
        for candidate, pattern in TITLE_PATTERNS:
            if pattern.search(title or ""):
                return candidate
    return ident


def category_for(foreground):
    return BY_ID.get(resolve_app(foreground), {}).get("category", "other")


def display_name(ident):
    key = canonical_app(ident)
    return BY_ID.get(key, {}).get("name", key.capitalize())
