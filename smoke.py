"""Check the installed payload without opening personal settings or downloading models."""
import json
import tempfile
from pathlib import Path


def run_window():
    """Open the shipped Windows GUI with an empty, isolated tutorial profile."""
    import os
    import sys
    import threading
    import time

    if sys.platform != 'win32':
        raise RuntimeError('The native window check requires Windows.')
    from version import APP_VERSION
    report_path = None
    if '--test-report' in sys.argv:
        report_path = Path(sys.argv[sys.argv.index('--test-report') + 1]).resolve()
    report = {'ok': False, 'version': APP_VERSION, 'native_window': 'starting'}

    def persist():
        if report_path:
            report_path.write_text(json.dumps(report), encoding='utf-8')

    def timed_out():
        report.update(native_window='failed', error='Native window did not initialize within 30 seconds.')
        persist()
        os._exit(1)

    with tempfile.TemporaryDirectory() as folder:
        os.environ['FLOW_DATA'] = folder  # Before importing paths or ui.
        import paths
        import ui
        import webview

        class ProbeApi(ui.Api):
            def settings(self):
                return {**paths.load_settings(), 'version': APP_VERSION, 'name': 'Alex',
                        'onboarded': True, 'tutorial_version': 0, 'native_window': True,
                        'platform': 'windows', 'startup': False, 'speech_models': [],
                        'recommended_model': 'small', 'gpu': None, 'cuda': False, 'ollama': {}}

            def memory(self):
                return {'terms': [], 'fixes': [], 'scanned': None}

            def insights(self):
                return {'words': 0, 'minutes_saved': 0, 'sessions': 0, 'known': 0,
                        'wpm': 0, 'apps': [], 'today_count': 0, 'last_used': None}

            def _ensure_tray(self):
                pass  # This check never starts a recorder, engine or downloader.

            def practice_status(self, focused=None):
                return {'ready': True, 'recording': False, 'busy': False, 'phase': 'ready'}

            def diagnostics(self):
                return {'status': 'passed'}

            def update_status(self):
                return {'phase': 'current', 'current': APP_VERSION}

        api = ProbeApi()
        win = ui.create_window(api)
        watchdog = threading.Timer(30, timed_out)
        watchdog.daemon = True
        watchdog.start()

        def verify():
            try:
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    state = win.evaluate_js("""({tutorial: !document.querySelector('#tutorial').hidden,
                        title: document.querySelector('#tourTitle')?.textContent,
                        ready: document.querySelector('#practiceOutput')?.dataset.ready === 'true',
                        blank: document.querySelector('#practiceOutput')?.value === '',
                        readonly: document.querySelector('#practiceOutput')?.readOnly === true,
                        locked: document.querySelector('#practiceAction')?.hidden === true,
                        phrase: document.querySelector('#practicePhrase')?.textContent,
                        empty: document.querySelector('.empty')?.textContent.includes('Nothing yet.')})""")
                    if (getattr(win, '_flow_style_applied', False) and state['tutorial']
                            and state['ready'] and state['blank'] and state['readonly'] and state['locked']
                            and state['phrase'] and state['empty']):
                        report.update(ok=True, native_window='responsive', icon='applied on GUI thread',
                                      tutorial='visible, initialized, ready to record', history='empty')
                        break
                    time.sleep(.1)
                else:
                    raise RuntimeError('Window opened but the icon or interactive tutorial did not initialize.')
            except Exception as error:
                report.update(native_window='failed', error=str(error))
            finally:
                persist()
                win.destroy()

        win.events.loaded += verify
        webview.start()
        watchdog.cancel()
    if not report['ok']:
        raise RuntimeError(report.get('error', 'Native window closed before verification.'))
    if sys.stdout is not None:
        print(json.dumps(report), flush=True)


def run(headless=False):
    import flow
    import ui
    import setup_tasks
    import system
    import paths
    import numpy as np
    import sounddevice
    import ctranslate2
    import onnxruntime
    import faster_whisper
    from memory import Memory
    from engine import Engine
    import tkinter as tk
    from pill import Pill

    with tempfile.TemporaryDirectory() as folder:
        mem = Memory(Path(folder) / "memory.db", ["en"])
        mem.add_term("Kubernetes", "you")
        assert mem.correct("Kubernetes") == "Kubernetes"
        mem.db.close()
    if not headless:
        root = tk.Tk()
        root.withdraw()
        pill = Pill(root)
        for state in ("listening", "transcribing", "message"):
            pill.render(state, 1, [0.5] * 20, "Ready", 1)
            pill.show()
            root.update()
            if system.IS_WIN:
                import ctypes
                from pill import user32, wt
                rect = wt.RECT()
                assert user32.IsWindowVisible(pill.hwnd), "Recording popup is hidden"
                assert user32.GetWindowRect(pill.hwnd, ctypes.byref(rect))
                assert rect.right - rect.left > 140 and rect.bottom - rect.top >= 36, "Recording popup has no visible frame"
                assert user32.GetWindowLongW(pill.hwnd, -20) & 0x8, "Recording popup is not topmost"
        pill.hide()
        root.destroy()
    assert (paths.APP / "ui.html").is_file()
    assert (paths.APP / "assets/PlexSans-400.woff2").is_file()
    assert (paths.APP / "assets/logos/codex.png").is_file()
    for logo in ("telegram.svg", "firefox.svg", "teams.svg", "word.svg", "powerpoint.svg", "obsidian.svg", "vscode.png"):
        assert (paths.APP / "assets/logos" / logo).is_file()
    from apps import CATALOG
    from version import APP_VERSION
    assert len(CATALOG) >= 50
    for app in CATALOG:
        assert (paths.APP / "assets/logos" / app["logo"]).is_file(), app["id"]
    import speech_api
    import control
    import health
    fixtures = json.loads((paths.APP / "assets/speech-check/manifest.json").read_text("utf-8"))
    for fixture in fixtures["fixtures"]:
        assert (paths.APP / "assets/speech-check" / fixture["file"]).is_file()
    assert control.TUTORIAL_VERSION == 2
    assert control.matches("I can speak instead of typing", control.PHRASES["en"])
    assert speech_api.validated_base("https://api.openai.com/v1") == "https://api.openai.com/v1"
    result = {"ok": True, "version": APP_VERSION, "app_catalog": len(CATALOG), "platform": "windows" if system.IS_WIN else "linux",
                      "gpu": system.nvidia_gpu() if not headless else "not inspected",
                      "cuda_libraries": system.cuda_ready() if not headless else "not inspected",
                      "audio_devices": len(sounddevice.query_devices()) if not headless else "not inspected",
                      "overlay": "visible, sized and topmost" if not headless and system.IS_WIN else "rendered" if not headless else "not opened",
                      "assets": "present", "speech_runtime": ctranslate2.__version__,
                      "interactive_practice": "bundled", "recording_states": "recording, thinking, polishing",
                      "speech_check": "bundled known-audio corpus"}
    if "--test-report" in __import__("sys").argv:
        args = __import__("sys").argv
        Path(args[args.index("--test-report") + 1]).write_text(json.dumps(result), "utf-8")
    if __import__("sys").stdout is not None:
        print(json.dumps(result), flush=True)
