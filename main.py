"""Flow entry point. `Flow.exe` runs the tray app; `Flow.exe --window` opens the window."""
import sys


def run():
    if "--mcp" in sys.argv:
        import mcp_server
        mcp_server.main(sys.argv[sys.argv.index("--mcp") + 1:])
    elif "--self-test-window" in sys.argv:
        import smoke
        smoke.run_window()
    elif "--self-test" in sys.argv or "--self-test-headless" in sys.argv:
        import smoke
        smoke.run(headless="--self-test-headless" in sys.argv)
    elif "--window" in sys.argv:
        import ui
        ui.main()
    else:
        import flow
        flow.main()


if __name__ == "__main__":
    run()
