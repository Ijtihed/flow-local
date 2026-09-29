"""Flow entry point. `Flow.exe` runs the tray app; `Flow.exe --window` opens the window."""
import sys


def run():
    if "--window" in sys.argv:
        import ui
        ui.main()
    else:
        import flow
        flow.main()


if __name__ == "__main__":
    run()
