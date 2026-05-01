"""
Code Editor tab — file browser + multi-tab editor + AI chat + terminal + debug.
"""
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import Qt, QModelIndex, QProcess, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import (
    QColor, QFont, QFontMetrics, QKeySequence,
    QSyntaxHighlighter, QTextCharFormat, QTextCursor,
)
from PyQt5.QtWidgets import (
    QFileDialog, QFileSystemModel, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QMenu, QMessageBox, QPlainTextEdit, QPushButton,
    QShortcut, QSplitter, QTabWidget, QTextEdit, QTreeView,
    QVBoxLayout, QWidget,
)

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config_manager import get_config
from terminal_executor import execute_command


# ── Syntax highlighter ─────────────────────────────────────────────────────────

class _Highlighter(QSyntaxHighlighter):
    """Lightweight multi-language syntax highlighter."""

    @staticmethod
    def _fmt(color: str, bold: bool = False, italic: bool = False) -> QTextCharFormat:
        f = QTextCharFormat()
        f.setForeground(QColor(color))
        if bold:
            f.setFontWeight(QFont.Bold)
        if italic:
            f.setFontItalic(True)
        return f

    _PY_KW = (
        r"\b(False|None|True|and|as|assert|async|await|break|class|continue|"
        r"def|del|elif|else|except|finally|for|from|global|if|import|in|is|"
        r"lambda|nonlocal|not|or|pass|raise|return|try|while|with|yield)\b"
    )
    _JS_KW = (
        r"\b(break|case|catch|class|const|continue|debugger|default|delete|do|"
        r"else|export|extends|finally|for|function|if|import|in|instanceof|let|"
        r"new|return|static|super|switch|this|throw|try|typeof|var|void|while|"
        r"with|yield|async|await|of|from|true|false|null|undefined)\b"
    )

    def __init__(self, parent, ext: str = "") -> None:
        super().__init__(parent)
        kw  = self._fmt("#569CD6", bold=True)
        st  = self._fmt("#CE9178")
        cmt = self._fmt("#6A9955", italic=True)
        num = self._fmt("#B5CEA8")
        dec = self._fmt("#DCDCAA")
        key = self._fmt("#9CDCFE")

        str_dq = r'"(?:[^"\\]|\\.)*"'
        str_sq = r"'(?:[^'\\]|\\.)*'"
        str_bt = r"`(?:[^`\\]|\\.)*`"

        if ext in (".py", ".pyw"):
            rules = [
                (self._PY_KW, kw),
                (str_dq, st), (str_sq, st),
                (r"#[^\n]*", cmt),
                (r"\b\d+\.?\d*\b", num),
                (r"@\w+", dec),
            ]
        elif ext in (".js", ".ts", ".jsx", ".tsx"):
            rules = [
                (self._JS_KW, kw),
                (str_dq, st), (str_sq, st), (str_bt, st),
                (r"//[^\n]*", cmt),
                (r"\b\d+\.?\d*\b", num),
            ]
        elif ext == ".json":
            rules = [
                (str_dq + r"\s*:", key),
                (str_dq, st),
                (r"\b(true|false|null)\b", kw),
                (r"\b\d+\.?\d*\b", num),
            ]
        else:
            rules = [
                (str_dq, st), (str_sq, st),
                (r"\b\d+\.?\d*\b", num),
            ]

        self._rules = [(re.compile(p), f) for p, f in rules]

    def highlightBlock(self, text: str) -> None:
        for pat, fmt in self._rules:
            for m in pat.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)


# ── Single editor pane ────────────────────────────────────────────────────────

class _LineNumberArea(QWidget):
    """Gutter widget that paints line numbers next to the editor."""

    def __init__(self, editor: "_EditorPane") -> None:
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self):
        from PyQt5.QtCore import QSize
        return QSize(self._editor._line_number_area_width(), 0)

    def paintEvent(self, event) -> None:
        self._editor._paint_line_numbers(event)


class _EditorPane(QPlainTextEdit):
    """A single editor instance bound to a file path."""

    modified_changed = pyqtSignal(object)
    request_review   = pyqtSignal(object)  # debounced — emits self when user pauses typing

    def __init__(self, path: Optional[str], content: str, parent=None) -> None:
        super().__init__(parent)
        font = QFont("Consolas", 11)
        font.setFixedPitch(True)
        self.setFont(font)
        self.setTabStopWidth(4 * QFontMetrics(font).width(" "))
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setStyleSheet(
            "QPlainTextEdit {"
            "  background: #1e1e1e; color: #d4d4d4;"
            "  border: 1px solid #3c3c3c; selection-background-color: #264f78;"
            "}"
        )
        self.path: Optional[str] = path
        self.modified: bool = False

        # Line number gutter
        self._line_area = _LineNumberArea(self)
        self.blockCountChanged.connect(self._update_line_area_width)
        self.updateRequest.connect(self._update_line_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self._update_line_area_width(0)
        self._highlight_current_line()

        self.blockSignals(True)
        self.setPlainText(content)
        self.blockSignals(False)

        ext = Path(path).suffix.lower() if path else ""
        self.highlighter = _Highlighter(self.document(), ext)
        self.textChanged.connect(self._on_changed)

        # Debounced live review trigger — fires ~2.5s after the user stops typing
        self._review_timer = QTimer(self)
        self._review_timer.setSingleShot(True)
        self._review_timer.setInterval(2500)
        self._review_timer.timeout.connect(lambda: self.request_review.emit(self))
        self.textChanged.connect(self._review_timer.start)

    # ── Line number gutter ─────────────────────────────────────────────────

    def _line_number_area_width(self) -> int:
        digits = max(3, len(str(max(1, self.blockCount()))))
        return 12 + QFontMetrics(self.font()).width("9") * digits

    def _update_line_area_width(self, _count: int) -> None:
        self.setViewportMargins(self._line_number_area_width(), 0, 0, 0)

    def _update_line_area(self, rect, dy: int) -> None:
        if dy:
            self._line_area.scroll(0, dy)
        else:
            self._line_area.update(
                0, rect.y(), self._line_area.width(), rect.height()
            )
        if rect.contains(self.viewport().rect()):
            self._update_line_area_width(0)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        cr = self.contentsRect()
        from PyQt5.QtCore import QRect
        self._line_area.setGeometry(
            QRect(cr.left(), cr.top(), self._line_number_area_width(), cr.height())
        )

    def _paint_line_numbers(self, event) -> None:
        from PyQt5.QtGui import QPainter, QColor
        painter = QPainter(self._line_area)
        painter.fillRect(event.rect(), QColor("#252526"))
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())
        cur_line = self.textCursor().blockNumber()
        width = self._line_area.width() - 4
        height = QFontMetrics(self.font()).height()
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                num = str(block_number + 1)
                painter.setPen(QColor("#dcdcaa") if block_number == cur_line else QColor("#858585"))
                painter.drawText(0, top, width, height, Qt.AlignRight, num)
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1

    def _highlight_current_line(self) -> None:
        from PyQt5.QtWidgets import QTextEdit
        from PyQt5.QtGui import QColor, QTextFormat
        sel = QTextEdit.ExtraSelection()
        sel.format.setBackground(QColor("#2a2d2e"))
        sel.format.setProperty(QTextFormat.FullWidthSelection, True)
        sel.cursor = self.textCursor()
        sel.cursor.clearSelection()
        self.setExtraSelections([sel])

    def _on_changed(self) -> None:
        if not self.modified:
            self.modified = True
            self.modified_changed.emit(self)

    def set_clean(self) -> None:
        self.modified = False
        self.modified_changed.emit(self)

    def reload_content(self, content: str) -> None:
        self.blockSignals(True)
        self.setPlainText(content)
        self.blockSignals(False)
        self.set_clean()


# ── AI tools ───────────────────────────────────────────────────────────────────

_AI_TOOLS = [
    {
        "name": "run_command",
        "description": "Run a PowerShell command in the workspace folder and return its output.",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
    {
        "name": "read_file",
        "description": "Read the full contents of a file.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": (
            "Create or overwrite a file with the given full content. "
            "Use for new files or full rewrites. Parent directories are created automatically."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "edit_file",
        "description": (
            "Edit an existing file by replacing one exact text snippet with another. "
            "old_text must appear EXACTLY once. Prefer this for small targeted changes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path":     {"type": "string"},
                "old_text": {"type": "string"},
                "new_text": {"type": "string"},
            },
            "required": ["path", "old_text", "new_text"],
        },
    },
    {
        "name": "list_directory",
        "description": "List files and folders in a directory.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": [],
        },
    },
]


# ── AI worker thread ───────────────────────────────────────────────────────────

class _AiWorker(QThread):
    chat_text     = pyqtSignal(str, str)
    terminal_text = pyqtSignal(str)
    file_written  = pyqtSignal(str, str)
    tool_activity = pyqtSignal(str, str)  # (status, message) — status: start|done|thinking
    done          = pyqtSignal(bool)

    def __init__(
        self,
        history: list,
        cwd: str,
        open_file: str,
        open_content: str,
        all_open_files: list,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._history      = list(history)
        self._cwd          = cwd
        self._open_file    = open_file
        self._open_content = open_content
        self._all_open     = all_open_files

    def run(self) -> None:
        try:
            import anthropic
            cfg = get_config()
            api_key = cfg.config.get("anthropic_api_key", "")
            client = anthropic.Anthropic(api_key=api_key)

            sys_prompt = (
                "You are an expert coding assistant embedded in a code editor. "
                "You can read/write/edit files, run PowerShell commands, and list "
                "directories. Be concise. Use edit_file for small targeted changes "
                "and write_file for new files or full rewrites.\n"
                f"Workspace folder: {self._cwd}\n"
            )
            tree = self._project_tree(self._cwd, max_entries=200)
            if tree:
                sys_prompt += f"\nProject layout (top {len(tree.splitlines())} entries):\n{tree}\n"
            if self._all_open:
                sys_prompt += "Open editor tabs: " + ", ".join(self._all_open) + "\n"
            if self._open_file:
                sys_prompt += f"Currently focused file: {self._open_file}\n"
                if self._open_content:
                    preview = self._open_content[:6000]
                    if len(self._open_content) > 6000:
                        preview += "\n... [truncated]"
                    sys_prompt += f"\nFile contents:\n```\n{preview}\n```"

            messages = list(self._history)

            while True:
                self.tool_activity.emit("thinking", "Thinking…")
                resp = client.messages.create(
                    model="claude-opus-4-5",
                    max_tokens=4096,
                    system=sys_prompt,
                    tools=_AI_TOOLS,
                    messages=messages,
                )

                text_parts, tool_uses = [], []
                for block in resp.content:
                    if block.type == "text" and block.text.strip():
                        text_parts.append(block.text)
                    elif block.type == "tool_use":
                        tool_uses.append(block)

                if text_parts:
                    self.chat_text.emit("assistant", "\n".join(text_parts))

                if resp.stop_reason != "tool_use" or not tool_uses:
                    break

                messages.append({"role": "assistant", "content": resp.content})
                tool_results = []
                for tu in tool_uses:
                    self.tool_activity.emit("start", self._describe_tool(tu))
                    result = self._run_tool(tu)
                    summary = self._summarize_result(tu, result)
                    self.tool_activity.emit("done", summary)
                    tool_results.append(
                        {"type": "tool_result", "tool_use_id": tu.id, "content": result}
                    )
                messages.append({"role": "user", "content": tool_results})

            self.done.emit(True)

        except Exception as exc:
            self.chat_text.emit("error", f"Error: {exc}")
            self.done.emit(False)

    def _resolve(self, path: str) -> Path:
        p = Path(path)
        if not p.is_absolute():
            p = Path(self._cwd) / p
        return p

    def _project_tree(self, root: str, max_entries: int = 200) -> str:
        """Compact recursive listing of the workspace, skipping noise."""
        skip = {
            ".git", ".venv", "venv", "__pycache__", "node_modules",
            "dist", "build", ".idea", ".vscode", "installer_output",
        }
        try:
            base = Path(root)
            if not base.is_dir():
                return ""
            lines: list[str] = []
            count = 0

            def walk(p: Path, depth: int) -> bool:
                nonlocal count
                if depth > 3:
                    return True
                try:
                    entries = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
                except Exception:
                    return True
                for e in entries:
                    if e.name.startswith(".") and e.name not in (".env", ".gitignore"):
                        continue
                    if e.name in skip:
                        continue
                    if count >= max_entries:
                        return False
                    indent = "  " * depth
                    suffix = "/" if e.is_dir() else ""
                    lines.append(f"{indent}{e.name}{suffix}")
                    count += 1
                    if e.is_dir():
                        if not walk(e, depth + 1):
                            return False
                return True

            walk(base, 0)
            return "\n".join(lines)
        except Exception:
            return ""

    def _describe_tool(self, tu) -> str:
        inp = tu.input or {}
        if tu.name == "run_command":
            return f"$ {inp.get('command','')}"
        if tu.name == "read_file":
            return f"Reading {inp.get('path','')}"
        if tu.name == "write_file":
            size = len(inp.get("content", "") or "")
            return f"Writing {inp.get('path','')} ({size} chars)"
        if tu.name == "edit_file":
            return f"Editing {inp.get('path','')}"
        if tu.name == "list_directory":
            return f"Listing {inp.get('path') or self._cwd}"
        return f"{tu.name}({inp})"

    def _summarize_result(self, tu, result: str) -> str:
        first = (result or "").splitlines()[0] if result else ""
        if len(first) > 120:
            first = first[:120] + "…"
        if tu.name in ("run_command", "list_directory", "read_file"):
            line_count = len((result or "").splitlines())
            return f"✓ {tu.name} — {line_count} lines"
        return f"✓ {first or tu.name}"

    def _run_tool(self, tu) -> str:
        name = tu.name
        inp  = tu.input or {}

        if name == "run_command":
            cmd = inp.get("command", "")
            full_cmd = f"Set-Location '{self._cwd}'; {cmd}"
            self.terminal_text.emit(f"\n❯ {cmd}\n")
            result = execute_command(full_cmd)
            out = result.output
            self.terminal_text.emit(out + "\n")
            return out or "(no output)"

        if name == "read_file":
            try:
                return self._resolve(inp.get("path", "")).read_text(
                    encoding="utf-8", errors="replace"
                )
            except Exception as exc:
                return f"Error reading file: {exc}"

        if name == "write_file":
            try:
                p = self._resolve(inp.get("path", ""))
                content = inp.get("content", "")
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content, encoding="utf-8")
                self.file_written.emit(str(p), content)
                return f"Written {len(content)} chars to {p}"
            except Exception as exc:
                return f"Error writing file: {exc}"

        if name == "edit_file":
            try:
                p = self._resolve(inp.get("path", ""))
                old_text = inp.get("old_text", "")
                new_text = inp.get("new_text", "")
                if not p.is_file():
                    return f"Error: file does not exist: {p}"
                content = p.read_text(encoding="utf-8", errors="replace")
                count = content.count(old_text)
                if count == 0:
                    return "Error: old_text not found in file."
                if count > 1:
                    return f"Error: old_text appears {count} times — must be unique."
                new_content = content.replace(old_text, new_text, 1)
                p.write_text(new_content, encoding="utf-8")
                self.file_written.emit(str(p), new_content)
                return f"Edited {p}"
            except Exception as exc:
                return f"Error editing file: {exc}"

        if name == "list_directory":
            try:
                p = self._resolve(inp.get("path") or self._cwd)
                entries = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
                lines = [("  " if e.is_file() else "📁 ") + e.name for e in entries]
                return "\n".join(lines) or "(empty)"
            except Exception as exc:
                return f"Error listing directory: {exc}"

        return f"Unknown tool: {name}"


# ── Live review worker ────────────────────────────────────────────────────────

class _ReviewWorker(QThread):
    """Sends the current file to Claude (cheap model) and returns issues."""

    review_ready = pyqtSignal(str, list, str)  # (file_path, issues, summary)
    failed       = pyqtSignal(str)

    _SYS_PROMPT = (
        "You are a senior code reviewer watching a developer type. "
        "Look at the file and flag REAL problems only (bugs, likely runtime "
        "errors, off-by-ones, security issues, broken logic, wrong API "
        "usage). Skip nitpicks and style. Be terse.\n\n"
        "Respond ONLY with a JSON object, no prose, no code fences:\n"
        '{"issues": [{"line": <int|null>, "severity": "bug"|"warn"|"info", '
        '"message": "..."}], "summary": "one short sentence"}\n\n'
        "Maximum 5 issues. If the code looks fine, return "
        '{"issues": [], "summary": "Looks good."}.'
    )

    def __init__(self, path: str, content: str, parent=None) -> None:
        super().__init__(parent)
        self._path    = path
        self._content = content

    def run(self) -> None:
        try:
            import anthropic
            cfg = get_config()
            api_key = cfg.config.get("anthropic_api_key", "")
            if not api_key:
                self.failed.emit("No API key.")
                return
            client = anthropic.Anthropic(api_key=api_key)

            lines = self._content.splitlines()
            numbered = "\n".join(
                f"{i+1:>4}: {ln}" for i, ln in enumerate(lines[:800])
            )
            if len(lines) > 800:
                numbered += f"\n... [truncated {len(lines) - 800} more lines]"
            user_msg = f"File: {self._path}\n\n```\n{numbered}\n```"

            try:
                cheap_model = cfg.get_cheap_model()
            except Exception:
                cheap_model = cfg.settings.get("cheap_model", "claude-haiku-4-5")

            resp = client.messages.create(
                model=cheap_model,
                max_tokens=600,
                system=self._SYS_PROMPT,
                messages=[{"role": "user", "content": user_msg}],
            )
            text = ""
            for blk in resp.content:
                if hasattr(blk, "text"):
                    text += blk.text

            stripped = text.strip()
            if stripped.startswith("```"):
                stripped = re.sub(
                    r"^```(?:json)?\s*|\s*```$", "", stripped, flags=re.MULTILINE
                ).strip()
            try:
                data = json.loads(stripped)
            except Exception:
                m = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
                if not m:
                    self.failed.emit("Bad review response.")
                    return
                data = json.loads(m.group(0))

            issues = data.get("issues") or []
            if not isinstance(issues, list):
                issues = []
            self.review_ready.emit(
                self._path, issues, str(data.get("summary", ""))
            )
        except Exception as exc:
            self.failed.emit(f"Review error: {exc}")


# ── Code Editor tab ────────────────────────────────────────────────────────────

class CodeEditorTab(QWidget):
    """File browser + multi-tab editor + AI chat + terminal + run/debug."""

    _SESSION_FILE = (
        Path(os.environ.get("APPDATA", str(Path.home())))
        / "GTclaw" / "code_editor_session.json"
    )

    def __init__(self) -> None:
        super().__init__()
        self._chat_history: list = []
        self._worker:       Optional[_AiWorker] = None
        self._cwd:          str                 = str(Path.home())
        self._debug_proc:   Optional[QProcess]  = None
        self._restoring:    bool                = False
        # Live AI watcher state
        self._watch_enabled:  bool = False
        self._review_worker:  Optional[_ReviewWorker] = None
        self._last_reviewed:  dict[str, str] = {}  # path -> last reviewed content
        self._build_ui()
        self._restore_session()
        # Save state when tabs change
        self._tabs.currentChanged.connect(lambda _i: self._save_session())
        self._tabs.tabCloseRequested.connect(lambda _i: QTimer.singleShot(0, self._save_session))

    # ── UI assembly ────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        outer = QSplitter(Qt.Vertical)

        top = QSplitter(Qt.Horizontal)
        top.addWidget(self._make_file_browser())
        top.addWidget(self._make_editor_area())
        top.addWidget(self._make_chat())
        top.setSizes([220, 600, 280])
        top.setStretchFactor(0, 0)
        top.setStretchFactor(1, 1)
        top.setStretchFactor(2, 0)

        outer.addWidget(top)
        outer.addWidget(self._make_terminal())
        outer.setSizes([520, 220])

        root.addWidget(outer)

    # ── File browser ───────────────────────────────────────────────────────────

    def _make_file_browser(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(6, 6, 4, 6)
        v.setSpacing(4)

        lbl = QLabel("📁  Files")
        lbl.setStyleSheet("font-weight: bold; font-size: 12px;")
        v.addWidget(lbl)

        path_row = QHBoxLayout()
        self._path_edit = QLineEdit(self._cwd)
        self._path_edit.setPlaceholderText("Workspace folder…")
        self._path_edit.returnPressed.connect(self._change_root)
        path_row.addWidget(self._path_edit)
        browse_btn = QPushButton("…")
        browse_btn.setFixedWidth(28)
        browse_btn.clicked.connect(self._browse_root)
        path_row.addWidget(browse_btn)
        v.addLayout(path_row)

        self._fs_model = QFileSystemModel()
        self._fs_model.setRootPath(self._cwd)
        self._fs_model.setNameFilterDisables(False)

        self._tree = QTreeView()
        self._tree.setModel(self._fs_model)
        self._tree.setRootIndex(self._fs_model.index(self._cwd))
        for col in (1, 2, 3):
            self._tree.setColumnHidden(col, True)
        self._tree.header().hide()
        self._tree.setAnimated(True)
        self._tree.setIndentation(14)
        self._tree.clicked.connect(self._on_file_click)
        self._tree.doubleClicked.connect(self._on_file_double_click)
        self._tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_tree_context_menu)
        v.addWidget(self._tree)
        return w

    # ── Editor area ────────────────────────────────────────────────────────────

    def _make_editor_area(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(4, 6, 4, 6)
        v.setSpacing(4)

        hdr = QHBoxLayout()
        new_btn = QPushButton("📄 New")
        new_btn.setFixedWidth(70)
        new_btn.clicked.connect(self._new_file)
        hdr.addWidget(new_btn)

        save_btn = QPushButton("💾 Save")
        save_btn.setFixedWidth(70)
        save_btn.setToolTip("Save current file (Ctrl+S)")
        save_btn.clicked.connect(self._save_current)
        hdr.addWidget(save_btn)

        save_all_btn = QPushButton("Save All")
        save_all_btn.setFixedWidth(70)
        save_all_btn.clicked.connect(self._save_all)
        hdr.addWidget(save_all_btn)

        hdr.addStretch()

        self._run_btn = QPushButton("▶ Run")
        self._run_btn.setFixedWidth(70)
        self._run_btn.setToolTip("Run current file in terminal (F5)")
        self._run_btn.clicked.connect(self._run_current)
        hdr.addWidget(self._run_btn)

        self._debug_btn = QPushButton("🐞 Debug")
        self._debug_btn.setFixedWidth(80)
        self._debug_btn.setToolTip("Run current Python file with pdb — type pdb commands in the terminal")
        self._debug_btn.clicked.connect(self._debug_current)
        hdr.addWidget(self._debug_btn)

        self._stop_btn = QPushButton("⏹ Stop")
        self._stop_btn.setFixedWidth(70)
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._stop_proc)
        hdr.addWidget(self._stop_btn)

        v.addLayout(hdr)

        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.setMovable(True)
        self._tabs.setDocumentMode(True)
        self._tabs.tabCloseRequested.connect(self._close_tab)
        v.addWidget(self._tabs)

        QShortcut(QKeySequence.Save, self).activated.connect(self._save_current)
        QShortcut(QKeySequence.New, self).activated.connect(self._new_file)
        QShortcut(QKeySequence("Ctrl+W"), self).activated.connect(
            lambda: self._close_tab(self._tabs.currentIndex())
        )
        QShortcut(QKeySequence("F5"), self).activated.connect(self._run_current)
        return w

    # ── Chat panel ─────────────────────────────────────────────────────────────

    def _make_chat(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(4, 6, 6, 6)
        v.setSpacing(4)

        hdr = QHBoxLayout()
        lbl = QLabel("🤖  AI Assistant")
        lbl.setStyleSheet("font-weight: bold; font-size: 12px;")
        hdr.addWidget(lbl)
        hdr.addStretch()
        self._watch_btn = QPushButton("👁  Watch: OFF")
        self._watch_btn.setCheckable(True)
        self._watch_btn.setToolTip(
            "When ON, the AI reviews your file ~2.5s after you stop typing\n"
            "and posts any bugs/warnings into this chat panel."
        )
        self._watch_btn.toggled.connect(self._on_watch_toggled)
        hdr.addWidget(self._watch_btn)
        clear_btn = QPushButton("Clear")
        clear_btn.setFixedWidth(50)
        clear_btn.clicked.connect(self._clear_chat)
        hdr.addWidget(clear_btn)
        v.addLayout(hdr)

        self._chat_display = QTextEdit()
        self._chat_display.setReadOnly(True)
        self._chat_display.setStyleSheet(
            "QTextEdit { background: #252526; color: #d4d4d4;"
            " border: 1px solid #3c3c3c; font-size: 12px; }"
        )
        v.addWidget(self._chat_display)

        self._chat_input = QLineEdit()
        self._chat_input.setPlaceholderText("Ask the AI anything…")
        self._chat_input.returnPressed.connect(self._send_chat)
        v.addWidget(self._chat_input)

        self._send_btn = QPushButton("Send")
        self._send_btn.clicked.connect(self._send_chat)
        v.addWidget(self._send_btn)
        return w

    # ── Terminal ───────────────────────────────────────────────────────────────

    def _make_terminal(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(6, 4, 6, 6)
        v.setSpacing(4)

        hdr = QHBoxLayout()
        lbl = QLabel("⌨  Terminal")
        lbl.setStyleSheet("font-weight: bold; font-size: 12px;")
        hdr.addWidget(lbl)
        self._cwd_label = QLabel(f"  {self._cwd}")
        self._cwd_label.setStyleSheet("color: #6A9955; font-size: 10px; font-family: Consolas;")
        hdr.addWidget(self._cwd_label)
        hdr.addStretch()
        clear_term_btn = QPushButton("Clear")
        clear_term_btn.setFixedWidth(50)
        clear_term_btn.clicked.connect(lambda: self._term_output.clear())
        hdr.addWidget(clear_term_btn)
        v.addLayout(hdr)

        font = QFont("Consolas", 10)
        self._term_output = QPlainTextEdit()
        self._term_output.setReadOnly(True)
        self._term_output.setFont(font)
        self._term_output.setStyleSheet(
            "QPlainTextEdit { background: #0c0c0c; color: #cccccc; border: 1px solid #333; }"
        )
        v.addWidget(self._term_output)

        inp_row = QHBoxLayout()
        prompt_lbl = QLabel("❯")
        prompt_lbl.setFont(font)
        prompt_lbl.setStyleSheet("color: #569CD6;")
        inp_row.addWidget(prompt_lbl)
        self._term_input = QLineEdit()
        self._term_input.setFont(font)
        self._term_input.setPlaceholderText("PowerShell command (or input/pdb command for running program)…")
        self._term_input.setStyleSheet(
            "QLineEdit { background: #0c0c0c; color: #cccccc; border: 1px solid #333; }"
        )
        self._term_input.returnPressed.connect(self._run_terminal_command)
        inp_row.addWidget(self._term_input)
        run_btn = QPushButton("Run")
        run_btn.setFixedWidth(46)
        run_btn.clicked.connect(self._run_terminal_command)
        inp_row.addWidget(run_btn)
        v.addLayout(inp_row)
        return w

    # ── File browser slots ─────────────────────────────────────────────────────

    def _browse_root(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Workspace Folder", self._cwd)
        if path:
            self._set_root(path)

    def _change_root(self) -> None:
        self._set_root(self._path_edit.text().strip())

    def _set_root(self, path: str) -> None:
        p = Path(path)
        if not p.is_dir():
            return
        new_cwd = str(p)
        if new_cwd == self._cwd and not self._restoring:
            return
        # Save chat that belongs to the OLD folder before switching
        if not self._restoring and self._cwd:
            self._save_chat()
        self._cwd = new_cwd
        self._path_edit.setText(self._cwd)
        self._cwd_label.setText(f"  {self._cwd}")
        self._fs_model.setRootPath(self._cwd)
        self._tree.setRootIndex(self._fs_model.index(self._cwd))
        # Load the chat for the NEW folder (skip during initial restore — handled there)
        if not self._restoring:
            self._load_chat_for_current_folder()
            self._save_session()

    def _on_file_click(self, index: QModelIndex) -> None:
        path = self._fs_model.filePath(index)
        if Path(path).is_file():
            self._open_file(path)

    def _on_file_double_click(self, index: QModelIndex) -> None:
        path = self._fs_model.filePath(index)
        if Path(path).is_dir():
            # Make this folder the workspace root
            self._set_root(path)

    # ── Tree context menu ──────────────────────────────────────────────────────

    def _on_tree_context_menu(self, point) -> None:
        index = self._tree.indexAt(point)
        if index.isValid():
            target_path = self._fs_model.filePath(index)
        else:
            target_path = self._cwd

        target = Path(target_path)
        # Folder for create operations: target if it's a directory, else its parent
        parent_dir = target if target.is_dir() else target.parent

        menu = QMenu(self._tree)

        if target.is_dir():
            menu.addAction("Open Folder as Workspace",
                           lambda: self._set_root(str(target)))
            menu.addAction("Open in File Explorer",
                           lambda: self._reveal_in_explorer(target))
            menu.addSeparator()
        else:
            menu.addAction("Open", lambda: self._open_file(str(target)))
            menu.addAction("Reveal in File Explorer",
                           lambda: self._reveal_in_explorer(target))
            menu.addSeparator()

        menu.addAction("📄 New File…",
                       lambda: self._ctx_new_file(parent_dir))
        menu.addAction("📁 New Folder…",
                       lambda: self._ctx_new_folder(parent_dir))

        if index.isValid():
            menu.addSeparator()
            menu.addAction("Rename…",
                           lambda: self._ctx_rename(target))
            menu.addAction("Delete",
                           lambda: self._ctx_delete(target))
            menu.addSeparator()
            menu.addAction("Copy Path",
                           lambda: self._copy_to_clipboard(str(target)))

        menu.exec_(self._tree.viewport().mapToGlobal(point))

    def _ctx_new_file(self, parent_dir: Path) -> None:
        name, ok = QInputDialog.getText(self, "New File", "File name:")
        if not ok or not name.strip():
            return
        target = parent_dir / name.strip()
        if target.exists():
            QMessageBox.warning(self, "Already Exists", f"{target} already exists.")
            return
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("", encoding="utf-8")
        except Exception as exc:
            QMessageBox.warning(self, "Create Failed", str(exc))
            return
        self._open_file(str(target))

    def _ctx_new_folder(self, parent_dir: Path) -> None:
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if not ok or not name.strip():
            return
        target = parent_dir / name.strip()
        if target.exists():
            QMessageBox.warning(self, "Already Exists", f"{target} already exists.")
            return
        try:
            target.mkdir(parents=True)
        except Exception as exc:
            QMessageBox.warning(self, "Create Failed", str(exc))

    def _ctx_rename(self, target: Path) -> None:
        new_name, ok = QInputDialog.getText(
            self, "Rename", "New name:", text=target.name
        )
        if not ok or not new_name.strip() or new_name.strip() == target.name:
            return
        new_path = target.parent / new_name.strip()
        if new_path.exists():
            QMessageBox.warning(self, "Already Exists", f"{new_path} already exists.")
            return
        try:
            target.rename(new_path)
        except Exception as exc:
            QMessageBox.warning(self, "Rename Failed", str(exc))
            return
        # Update any open editor tabs that pointed to the renamed file
        if target.is_file() or new_path.is_file():
            idx = self._find_tab_by_path(str(target))
            if idx >= 0:
                pane: _EditorPane = self._tabs.widget(idx)
                pane.path = str(new_path)
                self._tabs.setTabText(idx, new_path.name)
                self._tabs.setTabToolTip(idx, str(new_path))

    def _ctx_delete(self, target: Path) -> None:
        kind = "folder" if target.is_dir() else "file"
        reply = QMessageBox.question(
            self, "Delete",
            f"Permanently delete {kind} '{target.name}'?\n\n{target}",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            if target.is_dir():
                import shutil
                shutil.rmtree(target)
            else:
                target.unlink()
        except Exception as exc:
            QMessageBox.warning(self, "Delete Failed", str(exc))
            return
        # Close any open tab for the deleted file
        idx = self._find_tab_by_path(str(target))
        if idx >= 0:
            pane: _EditorPane = self._tabs.widget(idx)
            self._tabs.removeTab(idx)
            pane.deleteLater()

    def _reveal_in_explorer(self, target: Path) -> None:
        try:
            import subprocess
            if target.is_dir():
                subprocess.Popen(["explorer.exe", str(target)])
            else:
                subprocess.Popen(["explorer.exe", "/select,", str(target)])
        except Exception as exc:
            QMessageBox.warning(self, "Open Failed", str(exc))

    def _copy_to_clipboard(self, text: str) -> None:
        from PyQt5.QtWidgets import QApplication
        QApplication.clipboard().setText(text)

    # ── Tab management ─────────────────────────────────────────────────────────

    def _find_tab_by_path(self, path: str) -> int:
        try:
            target = str(Path(path).resolve())
        except Exception:
            return -1
        for i in range(self._tabs.count()):
            pane: _EditorPane = self._tabs.widget(i)
            if pane.path:
                try:
                    if str(Path(pane.path).resolve()) == target:
                        return i
                except Exception:
                    pass
        return -1

    def _open_file(self, path: str) -> None:
        existing = self._find_tab_by_path(path)
        if existing >= 0:
            self._tabs.setCurrentIndex(existing)
            return
        try:
            content = Path(path).read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            QMessageBox.warning(self, "Open Failed", str(exc))
            return
        pane = _EditorPane(path, content)
        pane.modified_changed.connect(self._update_tab_title)
        pane.request_review.connect(self._on_review_requested)
        idx = self._tabs.addTab(pane, Path(path).name)
        self._tabs.setTabToolTip(idx, path)
        self._tabs.setCurrentIndex(idx)
        if not self._restoring:
            self._save_session()

    def _new_file(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "New File", self._cwd)
        if not path:
            return
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text("", encoding="utf-8")
        except Exception as exc:
            QMessageBox.warning(self, "Create Failed", str(exc))
            return
        self._open_file(path)

    def _close_tab(self, idx: int) -> None:
        if idx < 0 or idx >= self._tabs.count():
            return
        pane: _EditorPane = self._tabs.widget(idx)
        if pane.modified:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                f"Save changes to {Path(pane.path).name if pane.path else 'untitled'}?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            )
            if reply == QMessageBox.Cancel:
                return
            if reply == QMessageBox.Yes:
                self._save_pane(pane)
        self._tabs.removeTab(idx)
        pane.deleteLater()

    def _update_tab_title(self, pane: _EditorPane) -> None:
        idx = self._tabs.indexOf(pane)
        if idx < 0 or not pane.path:
            return
        name = Path(pane.path).name
        self._tabs.setTabText(idx, ("● " + name) if pane.modified else name)

    def _current_pane(self) -> Optional[_EditorPane]:
        w = self._tabs.currentWidget()
        return w if isinstance(w, _EditorPane) else None

    def _save_pane(self, pane: _EditorPane) -> bool:
        if not pane.path:
            return False
        try:
            Path(pane.path).write_text(pane.toPlainText(), encoding="utf-8")
            pane.set_clean()
            return True
        except Exception as exc:
            QMessageBox.warning(self, "Save Failed", str(exc))
            return False

    def _save_current(self) -> None:
        pane = self._current_pane()
        if pane:
            self._save_pane(pane)

    def _save_all(self) -> None:
        for i in range(self._tabs.count()):
            pane: _EditorPane = self._tabs.widget(i)
            if pane.modified:
                self._save_pane(pane)

    # ── Run / Debug ────────────────────────────────────────────────────────────

    def _run_current(self) -> None:
        pane = self._current_pane()
        if not pane or not pane.path:
            return
        if pane.modified:
            self._save_pane(pane)
        self._run_file(pane.path, debug=False)

    def _debug_current(self) -> None:
        pane = self._current_pane()
        if not pane or not pane.path:
            return
        if pane.modified:
            self._save_pane(pane)
        self._run_file(pane.path, debug=True)

    def _run_file(self, path: str, debug: bool) -> None:
        if self._debug_proc and self._debug_proc.state() != QProcess.NotRunning:
            QMessageBox.information(self, "Already Running", "Stop the current process first.")
            return

        ext = Path(path).suffix.lower()
        proc = QProcess(self)
        proc.setWorkingDirectory(self._cwd)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(lambda: self._on_proc_output(proc))
        proc.finished.connect(self._on_proc_finished)

        if ext in (".py", ".pyw"):
            python_exe = self._find_python()
            args = ["-u"]
            if debug:
                args += ["-m", "pdb"]
            args.append(path)
            label = f"{Path(python_exe).name} {'-m pdb ' if debug else ''}{Path(path).name}"
            self._append_terminal(f"\n❯ {label}\n")
            proc.start(python_exe, args)
        elif ext == ".ps1":
            self._append_terminal(f"\n❯ powershell {Path(path).name}\n")
            proc.start("powershell.exe", [
                "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", path,
            ])
        elif ext in (".js", ".mjs"):
            self._append_terminal(f"\n❯ node {Path(path).name}\n")
            proc.start("node", [path])
        elif ext in (".bat", ".cmd"):
            self._append_terminal(f"\n❯ {Path(path).name}\n")
            proc.start("cmd.exe", ["/c", path])
        else:
            QMessageBox.information(
                self, "Unsupported", f"Don't know how to run {ext} files."
            )
            return

        self._debug_proc = proc
        self._stop_btn.setEnabled(True)
        self._run_btn.setEnabled(False)
        self._debug_btn.setEnabled(False)

    def _find_python(self) -> str:
        # Prefer venv python in workspace, else current interpreter
        venv_py = Path(self._cwd) / ".venv" / "Scripts" / "python.exe"
        if venv_py.is_file():
            return str(venv_py)
        return sys.executable or "python.exe"

    def _stop_proc(self) -> None:
        if self._debug_proc and self._debug_proc.state() != QProcess.NotRunning:
            self._debug_proc.kill()
            self._debug_proc.waitForFinished(2000)

    def _on_proc_output(self, proc: QProcess) -> None:
        data = bytes(proc.readAllStandardOutput()).decode("utf-8", errors="replace")
        self._append_terminal(data)

    def _on_proc_finished(self, exit_code: int, _status) -> None:
        self._append_terminal(f"\n[process exited with code {exit_code}]\n")
        self._stop_btn.setEnabled(False)
        self._run_btn.setEnabled(True)
        self._debug_btn.setEnabled(True)
        self._debug_proc = None

    # ── Chat ───────────────────────────────────────────────────────────────────

    def _append_chat(self, role: str, text: str) -> None:
        colors = {
            "user": "#569CD6", "assistant": "#d4d4d4", "error": "#f44747",
            "thinking": "#c586c0", "tool": "#4ec9b0", "tool_done": "#6a9955",
        }
        labels = {
            "user": "You", "assistant": "AI", "error": "Error",
            "thinking": "· AI", "tool": "▸ Tool", "tool_done": "✓ Tool",
        }
        color = colors.get(role, "#d4d4d4")
        label = labels.get(role, role.title())
        escaped = (
            text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                .replace("\n", "<br>")
        )
        if role in ("thinking", "tool", "tool_done"):
            html = (
                f'<p style="margin:2px 0; font-size:11px;">'
                f'<span style="color:{color}">{label}: {escaped}</span></p>'
            )
        else:
            html = (
                f'<p style="margin:4px 0;"><b style="color:{color}">{label}:</b>&nbsp;'
                f'<span style="color:{color}">{escaped}</span></p>'
            )
        self._chat_display.append(html)
        sb = self._chat_display.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_ai_tool_activity(self, status: str, message: str) -> None:
        role = {"thinking": "thinking", "start": "tool", "done": "tool_done"}.get(status, "tool")
        self._append_chat(role, message)

    def _clear_chat(self) -> None:
        self._chat_history.clear()
        self._chat_display.clear()
        self._save_chat()
        self._save_session()

    # ── Live AI watcher ────────────────────────────────────────────────────────

    def _on_watch_toggled(self, checked: bool) -> None:
        self._watch_enabled = checked
        self._watch_btn.setText("👁  Watch: ON" if checked else "👁  Watch: OFF")
        if checked:
            self._append_chat(
                "tool",
                "Live review enabled — I'll comment ~2.5s after you stop typing.",
            )
            # Trigger an immediate review of the current file
            pane = self._current_pane()
            if pane is not None:
                self._on_review_requested(pane)
        else:
            self._append_chat("tool_done", "Live review disabled.")

    def _on_review_requested(self, pane: "_EditorPane") -> None:
        if not self._watch_enabled:
            return
        if not pane or not pane.path:
            return
        if self._review_worker and self._review_worker.isRunning():
            return
        content = pane.toPlainText()
        if not content.strip():
            return
        # Skip if unchanged since last review
        if self._last_reviewed.get(pane.path) == content:
            return
        self._last_reviewed[pane.path] = content
        self._review_worker = _ReviewWorker(pane.path, content)
        self._review_worker.review_ready.connect(self._on_review_ready)
        self._review_worker.failed.connect(
            lambda msg: self._append_chat("error", f"Review: {msg}")
        )
        self._review_worker.start()

    def _on_review_ready(self, path: str, issues: list, summary: str) -> None:
        name = Path(path).name
        if not issues:
            self._append_chat("tool_done", f"✅  {name}: {summary or 'Looks good.'}")
            return
        sev_icon = {"bug": "🐞", "warn": "⚠️", "info": "ℹ️"}
        lines = [f"<b>Review of {name}:</b>"]
        for it in issues[:5]:
            if not isinstance(it, dict):
                continue
            sev = str(it.get("severity", "info")).lower()
            icon = sev_icon.get(sev, "•")
            line_no = it.get("line")
            loc = f" (line {line_no})" if isinstance(line_no, int) else ""
            msg = str(it.get("message", "")).strip()
            lines.append(f"  {icon}{loc}: {msg}")
        self._append_chat("tool", "\n".join(lines))

    # ── Per-folder chat persistence ───────────────────────────────────────────

    def _chat_file_for(self, cwd: str) -> Path:
        return Path(cwd) / ".gtclaw" / "chat.json"

    def _save_chat(self) -> None:
        if self._restoring or not self._cwd:
            return
        try:
            target = self._chat_file_for(self._cwd)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                json.dumps({"chat_history": self._chat_history[-200:]}, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _load_chat_for_current_folder(self) -> None:
        """Replace in-memory chat + display with whatever is saved for self._cwd."""
        self._chat_history.clear()
        self._chat_display.clear()
        chat_file = self._chat_file_for(self._cwd)
        if not chat_file.is_file():
            return
        try:
            data = json.loads(chat_file.read_text(encoding="utf-8"))
        except Exception:
            return
        history = data.get("chat_history", [])
        if not isinstance(history, list):
            return
        prev = self._restoring
        self._restoring = True
        try:
            for msg in history:
                if not isinstance(msg, dict):
                    continue
                role = msg.get("role", "")
                content = msg.get("content", "")
                if isinstance(content, str) and content.strip():
                    self._chat_history.append({"role": role, "content": content})
                    self._append_chat(
                        "user" if role == "user" else "assistant", content
                    )
        finally:
            self._restoring = prev

    # ── Session persistence ────────────────────────────────────────────────────────

    def _save_session(self) -> None:
        if self._restoring:
            return
        try:
            open_files = []
            for i in range(self._tabs.count()):
                pane: _EditorPane = self._tabs.widget(i)
                if pane.path and Path(pane.path).is_file():
                    open_files.append(pane.path)
            current = self._tabs.currentIndex()
            current_path = ""
            if current >= 0:
                cp: _EditorPane = self._tabs.widget(current)
                if cp.path:
                    current_path = cp.path
            data = {
                "cwd": self._cwd,
                "open_files": open_files,
                "current": current_path,
            }
            self._SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
            self._SESSION_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass
        # Chat lives in a per-folder file alongside the project
        self._save_chat()

    def _restore_session(self) -> None:
        if not self._SESSION_FILE.is_file():
            return
        try:
            data = json.loads(self._SESSION_FILE.read_text(encoding="utf-8"))
        except Exception:
            return
        self._restoring = True
        try:
            cwd = data.get("cwd")
            if cwd and Path(cwd).is_dir():
                self._set_root(cwd)
            for fp in data.get("open_files", []):
                if Path(fp).is_file():
                    self._open_file(fp)
            current = data.get("current")
            if current:
                idx = self._find_tab_by_path(current)
                if idx >= 0:
                    self._tabs.setCurrentIndex(idx)
            # Per-folder chat (current folder)
            self._load_chat_for_current_folder()
            # Backwards-compat: migrate legacy global chat_history into the
            # current folder's chat file the first time we restore.
            legacy = data.get("chat_history", [])
            if legacy and not self._chat_history and isinstance(legacy, list):
                for msg in legacy:
                    if not isinstance(msg, dict):
                        continue
                    role = msg.get("role", "")
                    content = msg.get("content", "")
                    if isinstance(content, str) and content.strip():
                        self._chat_history.append({"role": role, "content": content})
                        self._append_chat(
                            "user" if role == "user" else "assistant", content
                        )
        finally:
            self._restoring = False
        # Persist migrated legacy chat into the per-folder file
        if self._chat_history:
            self._save_chat()

    def _send_chat(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        msg = self._chat_input.text().strip()
        if not msg:
            return
        self._chat_input.clear()
        self._append_chat("user", msg)
        self._chat_history.append({"role": "user", "content": msg})
        self._save_chat()

        pane = self._current_pane()
        all_open = []
        for i in range(self._tabs.count()):
            p: _EditorPane = self._tabs.widget(i)
            if p.path:
                all_open.append(p.path)

        self._worker = _AiWorker(
            history=self._chat_history,
            cwd=self._cwd,
            open_file=pane.path if pane and pane.path else "",
            open_content=pane.toPlainText() if pane else "",
            all_open_files=all_open,
        )
        self._worker.chat_text.connect(self._on_ai_text)
        self._worker.terminal_text.connect(self._append_terminal)
        self._worker.file_written.connect(self._on_file_written)
        self._worker.tool_activity.connect(self._on_ai_tool_activity)
        self._worker.done.connect(self._on_ai_done)
        self._chat_input.setEnabled(False)
        self._send_btn.setEnabled(False)
        self._send_btn.setText("…")
        self._worker.start()

    def _on_ai_text(self, role: str, text: str) -> None:
        self._append_chat(role, text)
        if role == "assistant":
            self._chat_history.append({"role": "assistant", "content": text})
            self._save_chat()

    def _on_ai_done(self, _success: bool) -> None:
        self._chat_input.setEnabled(True)
        self._send_btn.setEnabled(True)
        self._send_btn.setText("Send")

    def _on_file_written(self, path: str, content: str) -> None:
        idx = self._find_tab_by_path(path)
        if idx >= 0:
            pane: _EditorPane = self._tabs.widget(idx)
            pane.reload_content(content)
        else:
            # Auto-open files the AI just created
            try:
                if Path(path).is_file():
                    self._open_file(path)
            except Exception:
                pass

    # ── Terminal slots ─────────────────────────────────────────────────────────

    def _append_terminal(self, text: str) -> None:
        self._term_output.moveCursor(QTextCursor.End)
        self._term_output.insertPlainText(text)
        sb = self._term_output.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _run_terminal_command(self) -> None:
        cmd = self._term_input.text()
        if not cmd:
            return
        self._term_input.clear()

        # If a debug/run process is active, treat input as stdin (e.g. pdb commands)
        if self._debug_proc and self._debug_proc.state() != QProcess.NotRunning:
            self._append_terminal(f"{cmd}\n")
            self._debug_proc.write((cmd + "\n").encode("utf-8"))
            return

        cmd = cmd.strip()
        if not cmd:
            return
        self._append_terminal(f"\n❯ {cmd}\n")

        lower = cmd.lower()
        if lower.startswith("cd ") or lower.startswith("set-location "):
            arg = cmd.split(None, 1)[1].strip().strip("'\"")
            candidate = Path(arg) if Path(arg).is_absolute() else Path(self._cwd) / arg
            if candidate.is_dir():
                self._set_root(str(candidate.resolve()))
                self._append_terminal(f"(cwd → {self._cwd})\n")
                return

        full_cmd = f"Set-Location '{self._cwd}'; {cmd}"
        result = execute_command(full_cmd, triggered_by="user")
        self._append_terminal(result.output + "\n")
