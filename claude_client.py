"""
Claude API client with:
  - Smart model routing (Haiku default, Sonnet on demand)
  - Tool use for Windows terminal command execution
  - API usage tracking logged to the database
"""
import ctypes
import ctypes.wintypes
import time
from pathlib import Path
from typing import Optional

import anthropic

from config_manager import get_config
from database import Database, calculate_cost

# Tools exposed to Claude
_TOOLS = [
    {
        "name": "run_command",
        "description": (
            "Execute a Windows command and return the output. "
            "Use PowerShell by default. Use this to help the user with system tasks, "
            "file operations, getting system information, or automating anything on Windows."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The command to execute.",
                },
                "shell": {
                    "type": "string",
                    "enum": ["powershell", "cmd"],
                    "description": "Which shell to use. Default: powershell.",
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "set_reminder",
        "description": (
            "Set a reminder that will be delivered to the user via Telegram at the specified time. "
            "Use this when the user says things like 'remind me in 10 minutes', 'remind me at 9pm', "
            "'remind me every day at 8am', 'wake me up in 30 minutes'. "
            "Calculate remind_at yourself based on the current time provided in your system prompt."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The reminder message to send to the user.",
                },
                "remind_at": {
                    "type": "string",
                    "description": "ISO 8601 datetime when to fire the reminder, e.g. '2026-04-30T21:00:00'.",
                },
                "recurring": {
                    "type": "string",
                    "description": (
                        "Optional. How often to repeat: 'daily', 'weekly', 'hourly', "
                        "or 'minutes:N' for every N minutes (e.g. 'minutes:30'). "
                        "Omit for a one-time reminder."
                    ),
                },
            },
            "required": ["message", "remind_at"],
        },
    },
    {
        "name": "manage_task",
        "description": (
            "Create, update, complete, cancel or list tasks/to-dos. "
            "Use when the user says 'add a task', 'my priorities', 'what do I need to do', "
            "'mark that done', 'what tasks are due', 'log a job'. "
            "Tasks support priorities (low/medium/high/urgent) and optional due dates."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "list", "complete", "cancel", "update"],
                    "description": "What to do.",
                },
                "title": {"type": "string", "description": "Task title (required for create)."},
                "description": {"type": "string", "description": "Extra detail about the task."},
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "urgent"],
                    "description": "Priority level. Default: medium.",
                },
                "due_date": {
                    "type": "string",
                    "description": "Due date as ISO string, e.g. '2026-05-01T09:00:00'. Optional.",
                },
                "task_id": {
                    "type": "integer",
                    "description": "Task ID for update/complete/cancel.",
                },
                "status_filter": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "done", "cancelled", "all"],
                    "description": "Filter tasks by status when listing. Default: pending.",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "log_farm_data",
        "description": (
            "Record farm data: paddock history (fertilizer, yield, soil tests, spray, grazing) "
            "or herd health (milk yield, SCC, weight, vet notes, treatments). "
            "Use whenever the user logs farm activities or health events."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "data_type": {
                    "type": "string",
                    "enum": ["paddock", "herd"],
                    "description": "Type of farm data.",
                },
                "name": {
                    "type": "string",
                    "description": "Paddock name (for paddock) or animal/group ID (for herd). Use 'herd' for whole-herd metrics.",
                },
                "date": {
                    "type": "string",
                    "description": "Date of the event (YYYY-MM-DD). Defaults to today.",
                },
                "record_type": {
                    "type": "string",
                    "description": (
                        "Paddock: fertilizer / yield / soil_test / spray / grazing / other. "
                        "Herd: milk_yield / scc / weight / vet_note / treatment / other."
                    ),
                },
                "value": {"type": "string", "description": "Measured value or short description."},
                "unit": {"type": "string", "description": "Unit of measurement, e.g. 'kg/ha', 'L/day', 'cells/mL'."},
                "notes": {"type": "string", "description": "Any additional notes."},
            },
            "required": ["data_type", "record_type"],
        },
    },
    {
        "name": "query_farm_data",
        "description": (
            "Retrieve historical farm records to review trends, check history, or support decisions. "
            "Use when the user asks 'what did I do to paddock X', 'milk yield this month', "
            "'show herd SCC history', 'what fertilizer did I use', 'my task history'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "data_type": {
                    "type": "string",
                    "enum": ["paddock", "herd", "tasks"],
                    "description": "What to query.",
                },
                "name": {"type": "string", "description": "Filter by paddock name or herd ID (optional)."},
                "record_type": {"type": "string", "description": "Filter by record type (optional)."},
                "days_back": {"type": "integer", "description": "How many days of history to include. Default: 30."},
                "limit": {"type": "integer", "description": "Max records to return. Default: 20."},
                "status_filter": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "done", "cancelled", "all"],
                    "description": "Task status filter (only used when data_type=tasks). Default: all.",
                },
            },
            "required": ["data_type"],
        },
    },
    {
        "name": "web_search",
        "description": (
            "Search the web for current information. "
            "Use when the user asks about news, prices, regulations, research, or anything "
            "that requires up-to-date information beyond your training data. "
            "Examples: 'current urea price NZ', 'Fonterra payout forecast', "
            "'grass staggers symptoms', 'NZ dairy SCC regulations'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Number of results to return (1-5). Default: 3.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_weather",
        "description": (
            "Fetch a farm weather forecast for the next 1-7 days. "
            "Shows temperature range, rainfall, wind speed. "
            "Flags frost risk, heavy rain warnings, and good spray/fertilizer windows. "
            "Use when the user asks about weather, 'is it safe to spray', 'when should I fertilize', "
            "'will it rain this week', 'any frost risk'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of forecast days (1-7). Default: 7.",
                },
            },
        },
    },
]


class ClaudeClient:
    def __init__(self) -> None:
        cfg = get_config()
        api_key = cfg.get_anthropic_key()
        if not api_key:
            raise ValueError(
                "anthropic_api_key not set in config/config.json (or ANTHROPIC_API_KEY in .env)"
            )
        self.client = anthropic.Anthropic(api_key=api_key)
        self._db = Database()

    async def chat(
        self,
        message: str,
        history: list,
        memory_context: str = "",
        use_smart: bool = False,
        session_id: Optional[str] = None,
    ) -> str:
        """
        Send a message to Claude, handling tool-use (command execution) loops.
        Returns the final text response.
        """
        cfg = get_config()
        model = cfg.get_smart_model() if use_smart else cfg.get_cheap_model()

        system = cfg.get_system_prompt()

        # Inject current time so Claude can calculate relative reminder times
        from datetime import datetime as _dt
        system += f"\n\nCurrent date/time: {_dt.now().strftime('%Y-%m-%d %H:%M:%S')}"

        # Inject the real files folder path so Claude always knows where to save files
        _buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
        ctypes.windll.shell32.SHGetFolderPathW(0, 5, 0, 0, _buf)
        files_dir = str(Path(_buf.value) / "GTclaw Documents")
        system += f"\nYour files folder (use this when creating any file): `{files_dir}`"

        if memory_context:
            system += f"\n\n---\nUser context:\n{memory_context}\n---"

        messages = list(history)
        messages.append({"role": "user", "content": message})

        start_time = time.monotonic()
        try:
            response = self.client.messages.create(
                model=model,
                max_tokens=int(cfg.settings.get("max_tokens_response", 1024)),
                system=system,
                tools=_TOOLS,
                messages=messages,
            )
        except anthropic.RateLimitError:
            return "⚠️ Rate limit hit — try again in a moment."
        except anthropic.APIError as exc:
            return f"⚠️ API error: {str(exc)[:100]}"
        except Exception as exc:
            return f"⚠️ Something went wrong: {str(exc)[:100]}"

        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        self._log_usage(response, model, elapsed_ms, session_id, "chat")

        # Agentic tool-use loop
        while response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_result = self._execute_tool(block)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": tool_result,
                    })

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

            start_time = time.monotonic()
            try:
                response = self.client.messages.create(
                    model=model,
                    max_tokens=int(cfg.settings.get("max_tokens_response", 1024)),
                    system=system,
                    tools=_TOOLS,
                    messages=messages,
                )
            except Exception as exc:
                return f"⚠️ Error after tool execution: {str(exc)[:100]}"

            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            self._log_usage(response, model, elapsed_ms, session_id, "chat+tool")

        return self._extract_text(response)

    async def quick_extract(self, prompt: str) -> str:
        """Low-cost Haiku call for background extraction. Returns raw text."""
        cfg = get_config()
        try:
            response = self.client.messages.create(
                model=cfg.get_cheap_model(),
                max_tokens=256,
                messages=[{"role": "user", "content": prompt}],
            )
            self._log_usage(response, cfg.get_cheap_model(), 0, None, "extraction")
            return response.content[0].text.strip()
        except Exception:
            return "[]"

    async def generate_text(self, prompt: str, max_tokens: int = 512) -> str:
        """General-purpose Haiku call (briefings, summaries). Returns text."""
        cfg = get_config()
        try:
            response = self.client.messages.create(
                model=cfg.get_cheap_model(),
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            self._log_usage(response, cfg.get_cheap_model(), 0, None, "generation")
            return response.content[0].text.strip()
        except Exception as exc:
            return f"⚠️ Generation error: {str(exc)[:80]}"

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _execute_tool(self, block) -> str:
        """Dispatch tool calls to the appropriate handler."""
        if block.name == "run_command":
            return self._run_command(block.input)
        elif block.name == "set_reminder":
            return self._set_reminder(block.input)
        elif block.name == "manage_task":
            return self._manage_task(block.input)
        elif block.name == "log_farm_data":
            return self._log_farm_data(block.input)
        elif block.name == "query_farm_data":
            return self._query_farm_data(block.input)
        elif block.name == "web_search":
            return self._web_search(block.input)
        elif block.name == "get_weather":
            return self._get_weather(block.input)
        return f"Unknown tool: {block.name}"

    def _run_command(self, tool_input: dict) -> str:
        """Execute a run_command tool call; log result; return output string."""
        from terminal_executor import execute_command

        command = tool_input.get("command", "")
        shell = tool_input.get("shell", "powershell")
        result = execute_command(command, shell=shell, triggered_by="claude")

        self._db.log_command(
            command=command,
            output=result.output,
            exit_code=result.exit_code,
            shell=shell,
            duration_ms=result.duration_ms,
            triggered_by="claude",
        )

        if result.blocked:
            return f"BLOCKED: {result.stderr}"
        if result.timed_out:
            return f"TIMEOUT after {result.duration_ms // 1000}s"
        return (
            f"Exit code: {result.exit_code}\n"
            f"Duration: {result.duration_ms}ms\n\n"
            f"{result.output}"
        )

    def _set_reminder(self, tool_input: dict) -> str:
        """Save a reminder to the database."""
        from datetime import datetime as _dt
        message = tool_input.get("message", "")
        remind_at_str = tool_input.get("remind_at", "")
        recurring = tool_input.get("recurring") or None
        try:
            remind_at = _dt.fromisoformat(remind_at_str)
            self._db.add_reminder(message, remind_at, recurring)
            recur_label = f" (repeats: {recurring})" if recurring else ""
            return f"✅ Reminder set for {remind_at.strftime('%Y-%m-%d %H:%M')}{recur_label}."
        except Exception as e:
            return f"Failed to set reminder: {e}"

    def _manage_task(self, tool_input: dict) -> str:
        """Create, list, complete, cancel or update tasks."""
        action = tool_input.get("action", "list")

        if action == "create":
            title = tool_input.get("title", "").strip()
            if not title:
                return "Error: title is required to create a task."
            task_id = self._db.create_task(
                title=title,
                description=tool_input.get("description"),
                priority=tool_input.get("priority", "medium"),
                due_date=tool_input.get("due_date"),
            )
            return f"✅ Task #{task_id} created: '{title}'"

        elif action == "list":
            status = tool_input.get("status_filter", "pending")
            tasks = self._db.get_tasks(status=status, limit=20)
            if not tasks:
                return f"No {status} tasks found."
            lines = [f"Tasks ({status}):"]
            for t in tasks:
                due = f" — due {t['due_date']}" if t.get("due_date") else ""
                lines.append(f"  #{t['id']} [{t['priority'].upper()}] {t['title']}{due} ({t['status']})")
            return "\n".join(lines)

        elif action in ("complete", "cancel"):
            task_id = tool_input.get("task_id")
            if not task_id:
                return "Error: task_id required."
            new_status = "done" if action == "complete" else "cancelled"
            ok = self._db.update_task(task_id, status=new_status)
            return f"✅ Task #{task_id} marked {new_status}." if ok else f"Task #{task_id} not found."

        elif action == "update":
            task_id = tool_input.get("task_id")
            if not task_id:
                return "Error: task_id required."
            kwargs = {k: tool_input.get(k) for k in ("title", "description", "priority", "status", "due_date")}
            kwargs = {k: v for k, v in kwargs.items() if v is not None}
            ok = self._db.update_task(task_id, **kwargs)
            return f"✅ Task #{task_id} updated." if ok else f"Task #{task_id} not found."

        return f"Unknown action: {action}"

    def _log_farm_data(self, tool_input: dict) -> str:
        """Log paddock or herd records."""
        data_type = tool_input.get("data_type", "")
        record_type = tool_input.get("record_type", "")
        date = tool_input.get("date") or None
        value = tool_input.get("value") or None
        unit = tool_input.get("unit") or None
        notes = tool_input.get("notes") or None

        if data_type == "paddock":
            name = tool_input.get("name", "unknown")
            rec_id = self._db.log_paddock(
                paddock_name=name, record_type=record_type,
                date=date, value=value, unit=unit, notes=notes,
            )
            val_str = f" — {value}{' ' + unit if unit else ''}" if value else ""
            return f"✅ Logged paddock '{name}' {record_type}{val_str} (record #{rec_id})."

        elif data_type == "herd":
            rec_id = self._db.log_herd(
                metric=record_type, date=date, value=value, unit=unit, notes=notes,
            )
            val_str = f" — {value}{' ' + unit if unit else ''}" if value else ""
            return f"✅ Logged herd {record_type}{val_str} (record #{rec_id})."

        return f"Unknown data_type: {data_type}"

    def _query_farm_data(self, tool_input: dict) -> str:
        """Retrieve farm records and format for Claude."""
        data_type = tool_input.get("data_type", "")
        days_back = int(tool_input.get("days_back", 30))
        limit = int(tool_input.get("limit", 20))

        if data_type == "paddock":
            rows = self._db.get_paddock_records(
                paddock_name=tool_input.get("name"),
                record_type=tool_input.get("record_type"),
                days_back=days_back, limit=limit,
            )
            if not rows:
                return "No paddock records found for those filters."
            lines = [f"Paddock records (last {days_back} days):"]
            for r in rows:
                val = f" {r['value']}{' ' + r['unit'] if r['unit'] else ''}" if r.get("value") else ""
                note = f" | {r['notes']}" if r.get("notes") else ""
                lines.append(f"  {r['date']} [{r['paddock_name']}] {r['record_type']}{val}{note}")
            return "\n".join(lines)

        elif data_type == "herd":
            rows = self._db.get_herd_records(
                metric=tool_input.get("record_type"),
                days_back=days_back, limit=limit,
            )
            if not rows:
                return "No herd records found for those filters."
            lines = [f"Herd records (last {days_back} days):"]
            for r in rows:
                val = f" {r['value']}{' ' + r['unit'] if r['unit'] else ''}" if r.get("value") else ""
                note = f" | {r['notes']}" if r.get("notes") else ""
                lines.append(f"  {r['date']} [{r['metric']}]{val}{note}")
            return "\n".join(lines)

        elif data_type == "tasks":
            status = tool_input.get("status_filter", "all")
            rows = self._db.get_tasks(status=status, limit=limit)
            if not rows:
                return "No tasks found."
            lines = [f"Tasks ({status}):"]
            for t in rows:
                due = f" — due {t['due_date']}" if t.get("due_date") else ""
                lines.append(f"  #{t['id']} [{t['priority'].upper()}] {t['title']}{due} ({t['status']})")
            return "\n".join(lines)

        return f"Unknown data_type: {data_type}"

    def _web_search(self, tool_input: dict) -> str:
        """Search the web via Tavily."""
        try:
            from tavily import TavilyClient
        except ImportError:
            return "⚠️ tavily-python not installed. Run: pip install tavily-python"

        cfg = get_config()
        api_key = cfg.config.get("tavily_api_key", "")
        if not api_key:
            return "⚠️ tavily_api_key not set in config/config.json."

        query = tool_input.get("query", "")
        max_results = min(int(tool_input.get("max_results", 3)), 5)
        try:
            client = TavilyClient(api_key=api_key)
            response = client.search(query=query, max_results=max_results, include_answer=True)
            # Log to api_usage so the dashboard tracks search calls
            self._db.log_api_call(
                model="tavily-search",
                input_tokens=0, output_tokens=0,
                cost_usd=0.0, response_time_ms=0,
                purpose="web_search",
            )
            lines = [f"Search: {query}"]
            if response.get("answer"):
                lines.append(f"\nSummary: {response['answer']}")
            lines.append("\nSources:")
            for r in response.get("results", []):
                lines.append(f"  • {r.get('title', 'No title')} — {r.get('url', '')}")
                if r.get("content"):
                    lines.append(f"    {r['content'][:200]}...")
            return "\n".join(lines)
        except Exception as e:
            return f"⚠️ Search failed: {e}"

    def _get_weather(self, tool_input: dict) -> str:
        """Fetch weather from Open-Meteo (free, no API key required)."""
        import httpx
        cfg = get_config()
        lat = cfg.settings.get("farm_lat", -37.78)
        lon = cfg.settings.get("farm_lon", 175.28)
        days = max(1, min(int(tool_input.get("days", 7)), 7))

        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,"
            f"wind_speed_10m_max,precipitation_probability_max"
            f"&wind_speed_unit=kmh&timezone=Pacific%2FAuckland&forecast_days={days}"
        )
        try:
            resp = httpx.get(url, timeout=10)
            resp.raise_for_status()
            daily = resp.json()["daily"]
            lines = [f"Farm weather forecast ({days} days):"]
            for i in range(days):
                date = daily["time"][i]
                tmax = daily["temperature_2m_max"][i] or "?"
                tmin = daily["temperature_2m_min"][i] or "?"
                rain = daily["precipitation_sum"][i] or 0
                wind = daily["wind_speed_10m_max"][i] or 0
                rain_prob = daily["precipitation_probability_max"][i] or 0

                flags = []
                if isinstance(tmin, (int, float)) and tmin < 2:
                    flags.append("❄️ FROST RISK")
                if rain > 20:
                    flags.append("🌧 HEAVY RAIN")
                elif rain < 2 and wind < 20 and rain_prob < 30:
                    flags.append("✅ Good spray/fert window")
                flag_str = "  " + " ".join(flags) if flags else ""

                lines.append(
                    f"  {date}: {tmin}–{tmax}°C | Rain: {rain:.1f}mm ({rain_prob}%) | "
                    f"Wind: {wind:.0f}km/h{flag_str}"
                )
            return "\n".join(lines)
        except Exception as e:
            return f"⚠️ Weather fetch failed: {e}"

    def _extract_text(self, response) -> str:
        """Pull text from a Claude response object."""
        for block in response.content:
            if hasattr(block, "text"):
                return block.text
        return ""

    def _log_usage(
        self,
        response,
        model: str,
        elapsed_ms: int,
        session_id: Optional[str],
        purpose: str,
    ) -> None:
        """Log token usage and cost to the database."""
        try:
            usage = response.usage
            cost = calculate_cost(model, usage.input_tokens, usage.output_tokens)
            self._db.log_api_call(
                model=model,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cost_usd=cost,
                response_time_ms=elapsed_ms,
                purpose=purpose,
                session_id=session_id,
            )
            self._check_budget()
        except Exception:
            pass  # Never crash on logging

    def _check_budget(self) -> None:
        """Log budget alerts when daily/monthly limits are exceeded."""
        try:
            cfg = get_config()
            if not cfg.settings.get("budget_alerts_enabled", True):
                return
            daily_limit = float(cfg.settings.get("budget_daily_usd", 1.0))
            monthly_limit = float(cfg.settings.get("budget_monthly_usd", 20.0))
            today = self._db.get_usage_summary("today")
            month = self._db.get_usage_summary("this_month")
            if today["cost_usd"] >= daily_limit:
                self._db.log_budget_alert(
                    "daily_exceeded", daily_limit, today["cost_usd"], "today"
                )
            if month["cost_usd"] >= monthly_limit:
                self._db.log_budget_alert(
                    "monthly_exceeded", monthly_limit, month["cost_usd"], "this_month"
                )
        except Exception:
            pass
