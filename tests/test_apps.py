"""App identities, browser disambiguation, packaged logos and history persistence."""
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import apps
import paths
from engine import app_category
from flow import Flow


class AppCatalog(unittest.TestCase):
    def test_catalog_has_fifty_distinct_products_with_bundled_publisher_logos(self):
        self.assertGreaterEqual(len(apps.CATALOG), 50)
        self.assertEqual(len(apps.BY_ID), len(apps.CATALOG))
        for app in apps.CATALOG:
            with self.subTest(app=app["id"]):
                asset = paths.APP / "assets/logos" / app["logo"]
                self.assertTrue(asset.is_file())
                self.assertEqual(asset.read_bytes(), (paths.APP / "site/assets/logos" / app["logo"]).read_bytes())
                self.assertTrue(app["site"].startswith("https://"))
        js = (paths.APP / "assets/apps.js").read_text("utf-8")
        self.assertEqual(json.loads(js.split("window.FLOW_APPS = ", 1)[1].rstrip(";\n")), apps.CATALOG)
        self.assertEqual(js, (paths.APP / "site/assets/apps.js").read_text("utf-8"))

    def test_process_aliases_include_windows_and_linux_and_case(self):
        for app in apps.CATALOG:
            for alias in app["aliases"]:
                with self.subTest(alias=alias):
                    self.assertEqual(apps.resolve_app((alias.upper() + ".exe", "My document")), app["id"])
        self.assertEqual(apps.resolve_app(("org.telegram.desktop", "Maya")), "telegram")
        self.assertEqual(app_category(("WINWORD", "Draft")), "docs")

    def test_browser_tabs_use_app_identity_and_writing_category(self):
        cases = [("Quarterly draft - Google Docs - Mozilla Firefox", "googledocs", "docs"),
                 ("Inbox (2) - me@example.com - Gmail - Google Chrome", "gmail", "email"),
                 ("My project | Notion", "notion", "docs"),
                 ("Claude - Microsoft Edge", "claude", "ai"),
                 ("#launch | Slack", "slack", "work")]
        for browser in ("firefox", "chrome", "msedge", "msedge_proxy", "brave-browser"):
            for title, ident, category in cases:
                with self.subTest(browser=browser, title=title):
                    self.assertEqual(apps.resolve_app((browser, title)), ident)
                    self.assertEqual(app_category((browser, title)), category)

    def test_titles_do_not_change_native_apps_or_match_words_inside_documents(self):
        self.assertEqual(apps.resolve_app(("obsidian", "Telegram - Obsidian")), "obsidian")
        for title in ("How to count a word - Mozilla Firefox", "Slack integration notes - Firefox", "Signal processing - Firefox"):
            self.assertEqual(apps.resolve_app(("firefox", title)), "firefox")
            self.assertEqual(app_category(("firefox", title)), "other")
        self.assertEqual(apps.resolve_app(("unknown-editor", "My document")), "unknown-editor")
        self.assertEqual(apps.resolve_app(("", "")), "")

    def test_terminal_hosts_use_their_identity_and_code_category(self):
        cases = [("WindowsTerminal.exe", "windowsterminal", "Windows Terminal"),
                 ("wt", "windowsterminal", "Windows Terminal"),
                 ("pwsh.exe", "powershell", "PowerShell"),
                 ("cmd.exe", "commandprompt", "Command Prompt"),
                 ("conhost", "terminal", "Terminal"),
                 ("gnome-terminal-server", "gnometerminal", "GNOME Terminal"),
                 ("org.kde.konsole", "konsole", "Konsole"),
                 ("kitty", "kitty", "kitty"),
                 ("Alacritty", "alacritty", "Alacritty"),
                 ("wezterm-gui.exe", "wezterm", "WezTerm")]
        for process, ident, name in cases:
            with self.subTest(process=process):
                self.assertEqual(apps.resolve_app((process, "Telegram - shell output")), ident)
                self.assertEqual(apps.display_name(process), name)
                self.assertEqual(app_category((process, "Shell")), "code")

    def test_existing_terminal_history_is_grouped_without_rewriting_it(self):
        from ui import Api
        fixture = [{"app": name, "words": 3, "seconds": 2}
                   for name in ("Windowsterminal", "WindowsTerminal.exe", "wt", "pwsh")]
        with tempfile.TemporaryDirectory() as folder:
            history = Path(folder) / "history.jsonl"
            raw = "".join(json.dumps(item) + "\n" for item in fixture)
            history.write_text(raw, "utf-8")
            api = Api()
            api._mem = type("MemoryFixture", (), {"terms": lambda self: []})()
            with patch("ui.HISTORY", history):
                self.assertEqual(api.insights()["apps"], [("windowsterminal", 3), ("powershell", 1)])
                self.assertEqual(api.history(), fixture[::-1])
            self.assertEqual(history.read_text("utf-8"), raw)

    def test_history_records_web_app_without_storing_title(self):
        flow = Flow.__new__(Flow)
        flow.target_app = ("firefox", "Secret budget draft - Google Docs - Mozilla Firefox")
        flow.engine = type("EngineFixture", (), {"last_path": "local"})()
        flow.category = "docs"
        flow.settings = {}
        with tempfile.TemporaryDirectory() as folder, patch("flow.HISTORY", Path(folder) / "history.jsonl"), patch("flow.voicenotes.save") as notes:
            flow.save("Please send the draft.", 2, "en", 0.3)
            raw = (Path(folder) / "history.jsonl").read_text()
            self.assertEqual(json.loads(raw)["app"], "googledocs")
            self.assertNotIn("Secret budget", raw)
            self.assertEqual(notes.call_args.args[1], "Google Docs")
