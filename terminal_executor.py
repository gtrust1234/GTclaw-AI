"""
Safe Windows terminal command execution.
Executes PowerShell or CMD commands in a subprocess, captures output,
respects timeout, and blocks dangerous patterns.
"""
import os
import re
import subprocess
import time
from typing import Optional

from config_manager import get_config

# Patterns always blocked regardless of user settings
_ALWAYS_BLOCKED = [
    r"format\s+[a-z]:",
    r"\bdiskpart\b",
    r"del\s+.*\/f.*\/s",
    r"rmdir\s+.*\/s.*\/q",
    r"Remove-Item.*-Recurse.*-Force",
    r"\brm\s+-[rf]+\b",
    r"\bcipher\s+\/w\b",
    r"\bnet\s+user\b.*\/add\b",
    r"\b(shutdown|Restart-Computer)\b",
    r"\breg\s+delete\b",
]


class CommandResult:
    """Result of a terminal command execution."""

    def __init__(
        self,
        command: str,
        stdout: str,
        stderr: str,
        exit_code: int,
        duration_ms: int,
        blocked: bool = False,
        timed_out: bool = False,
    ) -> None:
        self.command = command
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.duration_ms = duration_ms
        self.blocked = blocked
        self.timed_out = timed_out
        self.success = exit_code == 0 and not blocked and not timed_out

    @property
    def output(self) -> str:
        parts = []
        if self.stdout.strip():
            parts.append(self.stdout.strip())
        if self.stderr.strip():
            parts.append(f"[stderr] {self.stderr.strip()}")
        return "\n".join(parts) or "(no output)"

    def to_dict(self) -> dict:
        return {
            "command": self.command,
            "output": self.output,
            "exit_code": self.exit_code,
            "success": self.success,
            "blocked": self.blocked,
            "timed_out": self.timed_out,
            "duration_ms": self.duration_ms,
        }


def _is_blocked(command: str) -> bool:
    """Return True if the command matches any blocked pattern."""
    for pattern in _ALWAYS_BLOCKED:
        if re.search(pattern, command, re.IGNORECASE):
            return True
    cfg = get_config()
    user_blocked: list = cfg.settings.get("blocked_commands", [])
    cmd_lower = command.lower()
    return any(b.lower() in cmd_lower for b in user_blocked)


def execute_command(
    command: str,
    shell: str = "powershell",
    timeout: Optional[int] = None,
    triggered_by: str = "claude",
) -> CommandResult:
    """
    Execute a terminal command safely.

    Args:
        command:      The command string to run.
        shell:        'powershell' (default) or 'cmd'.
        timeout:      Seconds before killing the process. Defaults to settings value.
        triggered_by: 'user' | 'claude' — recorded in command log.

    Returns:
        CommandResult with stdout, stderr, exit_code, duration_ms.
    """
    cfg = get_config()

    if not cfg.settings.get("command_execution_enabled", True):
        return CommandResult(command, "", "Command execution is disabled in settings.", -1, 0, blocked=True)

    if _is_blocked(command):
        return CommandResult(
            command, "", f"Blocked by safety rules: {command!r}", -1, 0, blocked=True
        )

    timeout = timeout or int(cfg.settings.get("command_timeout_seconds", 30))

    if shell == "powershell":
        args = [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy", "Bypass",
            "-Command", command,
        ]
    else:
        args = ["cmd.exe", "/c", command]

    start = time.monotonic()
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        duration_ms = int((time.monotonic() - start) * 1000)
        return CommandResult(
            command=command,
            stdout=proc.stdout,
            stderr=proc.stderr,
            exit_code=proc.returncode,
            duration_ms=duration_ms,
        )
    except subprocess.TimeoutExpired:
        duration_ms = int((time.monotonic() - start) * 1000)
        return CommandResult(
            command, "", f"Timed out after {timeout}s.", -1, duration_ms, timed_out=True
        )
    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        return CommandResult(command, "", f"Execution error: {exc}", -1, duration_ms)
