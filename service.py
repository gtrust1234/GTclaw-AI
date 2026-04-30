"""
Windows Service wrapper for the Personal AI Assistant bot.
Installs/removes/starts/stops as a Windows Service using pywin32.

Usage (run as Administrator):
  python service.py install     -- register service
  python service.py start       -- start service
  python service.py stop        -- stop service
  python service.py remove      -- uninstall service
  python service.py debug       -- run interactively (no service manager)
"""
import subprocess
import sys
import time
from pathlib import Path

try:
    import win32event
    import win32service
    import win32serviceutil
    import servicemanager
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

BOT_SCRIPT = str(Path(__file__).parent / "bot.py")
SERVICE_NAME = "PersonalAIAssistant"
SERVICE_DISPLAY = "Personal AI Assistant Bot"
SERVICE_DESC = "24/7 AI assistant — Telegram + Claude API"


if HAS_WIN32:
    class BotService(win32serviceutil.ServiceFramework):
        _svc_name_ = SERVICE_NAME
        _svc_display_name_ = SERVICE_DISPLAY
        _svc_description_ = SERVICE_DESC

        def __init__(self, args):
            super().__init__(args)
            self._stop_event = win32event.CreateEvent(None, 0, 0, None)
            self._proc = None

        def SvcStop(self):
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            win32event.SetEvent(self._stop_event)
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self._proc.kill()

        def SvcDoRun(self):
            servicemanager.LogMsg(
                servicemanager.EVENTLOG_INFORMATION_TYPE,
                servicemanager.PYS_SERVICE_STARTED,
                (self._svc_name_, ""),
            )
            self._run()

        def _run(self):
            python_exe = sys.executable
            while True:
                self._proc = subprocess.Popen(
                    [python_exe, BOT_SCRIPT],
                    cwd=str(Path(__file__).parent),
                )
                # Wait for stop event or process exit
                while True:
                    rc = win32event.WaitForSingleObject(self._stop_event, 2000)
                    if rc == win32event.WAIT_OBJECT_0:
                        # Stop requested
                        return
                    if self._proc.poll() is not None:
                        # Process exited unexpectedly — restart after 5 s
                        servicemanager.LogMsg(
                            servicemanager.EVENTLOG_WARNING_TYPE,
                            servicemanager.PYS_SERVICE_STOPPED,
                            (self._svc_name_, "Bot crashed — restarting in 5s"),
                        )
                        time.sleep(5)
                        break  # inner loop — will restart outer loop


def _run_debug():
    """Run bot directly (no service manager) for testing / daemon mode."""
    if getattr(sys, 'frozen', False):
        # Running as a compiled EXE: bot code is bundled inside this binary.
        # Import and run it directly — no external python or bot.py file needed.
        import asyncio
        import bot as _bot
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        _bot.main()
    else:
        proc = subprocess.Popen(
            [sys.executable, BOT_SCRIPT],
            cwd=str(Path(__file__).parent),
        )
        print(f"Bot started (PID {proc.pid}). Press Ctrl+C to stop.")
        try:
            proc.wait()
        except KeyboardInterrupt:
            proc.terminate()
            proc.wait()
            print("Bot stopped.")


if __name__ == "__main__":
    if not HAS_WIN32:
        print("pywin32 not installed. Running bot directly instead.")
        _run_debug()
        sys.exit(0)

    if len(sys.argv) == 2 and sys.argv[1] == "debug":
        _run_debug()
    elif len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(BotService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(BotService)
