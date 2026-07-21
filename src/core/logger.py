"""
RAG2Prod — Unified Logging & Progress System

Architecture
────────────
Two output channels, one API:

1. Terminal (rich)   → Coloured, progress bars, spinners — for the developer.
2. JSON log file     → Structured, machine-parseable — for AI agents & log aggregators.

Both are driven by Python's stdlib `logging` + `structlog`.

Usage
─────
    from core.logger import get_logger, pipeline, timer_step

    log = get_logger("chunker")
    log.info("Splitting document", doc_id="doc_123", chars=4500)

    with pipeline("Ingestion", total_steps=3) as p:
        with p.step("parser", "Parsing PDFs"):
            ...

    with timer_step("ocr", "OCR page 3"):
        ...
"""
import os
import sys
import json
import time
import logging
from logging import StreamHandler
import datetime
import threading
from typing import Optional, Any
from contextlib import contextmanager
from pythonjsonlogger import jsonlogger

import structlog
from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    MofNCompleteColumn,
)

# ─── Global State ────────────────────────────────────────────────────
_CURRENT_LOG_DIR: Optional[str] = None
_CONFIGURED = False
_DIR_LOCK = threading.Lock()
_FILE_LOCK = threading.Lock()

# Suppress rich output during pytest
_IS_TESTING = "pytest" in sys.modules
console = Console(quiet=_IS_TESTING)


# ─── Directory Management ────────────────────────────────────────────

def _init_dirs():
    global _CURRENT_LOG_DIR
    with _DIR_LOCK:
        if _CURRENT_LOG_DIR is None:
            date_str = datetime.datetime.now().strftime("%Y-%m-%d")
            time_str = datetime.datetime.now().strftime("%H-%M-%S")

            _CURRENT_LOG_DIR = os.path.join("logs", date_str, time_str)
            os.makedirs(_CURRENT_LOG_DIR, exist_ok=True)


def get_log_dir() -> str:
    _init_dirs()
    return _CURRENT_LOG_DIR


# ─── Logging Configuration ───────────────────────────────────────────

def _write_json_line(entry: dict) -> None:
    """Thread-safe write of a single JSON line to the execution log."""
    with _FILE_LOCK:
        log_file = os.path.join(get_log_dir(), "execution.log")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")


def _render_to_terminal(module: str, message: str, level: str,
                        duration_ms: Optional[float] = None,
                        status: Optional[str] = None) -> None:
    """Render a human-friendly line to the terminal via rich."""
    if _IS_TESTING:
        return

    # Suppress starting logs in terminal to avoid visual clutter.
    # They remain fully preserved in the structured JSON log file.
    if status == "starting":
        return

    ts = datetime.datetime.now().strftime("%H:%M:%S")

    # Duration formatting
    if duration_ms is not None:
        time_part = f"[bold cyan]{duration_ms:.1f}ms[/]"
    else:
        time_part = "[dim]·[/]"

    # Icon based on level/status
    if level == "ERROR":
        icon = "[bold red]✗[/]"
    elif status == "done":
        icon = "[bold green]✓[/]"
    else:
        icon = "[dim]·[/]"

    console.print(
        f"  {icon} [dim]{ts}[/] [bold magenta]{module:>12}[/] {time_part}  {message}"
    )


def _structlog_renderer(logger: Any, method_name: str, event_dict: dict) -> str:
    """
    Final structlog processor.
    Writes structured JSON to file AND renders to terminal.
    Returns the plain message string for stdlib's LogRecord.
    """
    module = event_dict.pop("_module", "system")
    event = event_dict.pop("event", "")
    level = event_dict.pop("level", method_name).upper()

    # Remove structlog internal keys
    event_dict.pop("_from_structlog", None)

    # Build the structured JSON entry for the log file
    json_entry = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "level": level,
        "module": module,
        "message": event,
    }
    # Add all remaining context fields (doc_id, duration_ms, status, etc.)
    json_entry.update(event_dict)

    # Write to JSON log file
    try:
        _write_json_line(json_entry)
    except Exception:
        pass

    # Render to terminal
    try:
        _render_to_terminal(
            module=module,
            message=event,
            level=level,
            duration_ms=event_dict.get("duration_ms"),
            status=event_dict.get("status"),
        )
    except Exception:
        pass

    # Return plain string for stdlib (not used by our handlers, but required)
    return event


def configure_logging():
    """
    Sets up structlog with a custom renderer that outputs to both
    the terminal (rich) and the JSON log file simultaneously.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    _init_dirs()

    # Configure standard python logging with JSON formatter
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        
    json_handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter('%(asctime)s %(levelname)s %(name)s %(message)s')
    json_handler.setFormatter(formatter)
    root_logger.addHandler(json_handler)

    # Silence the stdlib logger output — we handle everything in our renderer
    stdlib_logger = logging.getLogger("rag2prod")
    stdlib_logger.setLevel(logging.INFO)

    class _NullLogger:
        def msg(self, message: str) -> None:
            pass
        def err(self, message: str) -> None:
            pass
        log = debug = info = warn = warning = error = critical = fatal = msg

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer() if os.environ.get("ENV") == "production" else _structlog_renderer,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=lambda *args: logging.getLogger(args[0]) if os.environ.get("ENV") == "production" else _NullLogger(),
        cache_logger_on_first_use=True,
    )


# ─── Public API ───────────────────────────────────────────────────────

def get_logger(module: str) -> structlog.stdlib.BoundLogger:
    """
    Returns a structured logger bound to a module name.

    Usage:
        log = get_logger("chunker")
        log.info("Splitting document", doc_id="doc_123", chars=4500)
        log.warning("Chunk too small", tokens=12)
        log.error("Failed to parse", error=str(e))
    """
    configure_logging()
    return structlog.get_logger("rag2prod", _module=module)


# Legacy convenience functions (thin wrappers for existing module integrations)
def info(module: str, message: str, **kwargs):
    get_logger(module).info(message, **kwargs)


def error(module: str, message: str, **kwargs):
    get_logger(module).error(message, **kwargs)


def success(module: str, message: str, elapsed_ms: float = None, **kwargs):
    get_logger(module).info(message, status="done", duration_ms=elapsed_ms, **kwargs)


# ─── Progress Bar (uv / npm style) ───────────────────────────────────

def create_progress() -> Progress:
    """
    Creates a rich Progress bar matching the uv/npm aesthetic:
      ⠋ Ingestion  ━━━━━━━━━━━━━━━━━━━━  45%  3/7  0:00:12  ETA 0:00:15
    """
    return Progress(
        SpinnerColumn("dots", style="bold cyan"),
        TextColumn("[bold]{task.description}[/]", justify="left"),
        BarColumn(bar_width=30, style="bar.back", complete_style="bar.complete",
                  finished_style="bar.finished"),
        TaskProgressColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TextColumn("[dim]ETA[/]"),
        TimeRemainingColumn(),
        console=console,
        transient=False,
    )


@contextmanager
def pipeline(name: str, total_steps: int):
    """
    Top-level context manager for a multi-step pipeline.
    Shows a live progress bar in the terminal.
    Writes structured JSON for each step to the log file.

    Usage:
        with pipeline("Ingestion", total_steps=4) as p:
            with p.step("parser", "Parsing PDFs"):
                ...
            with p.step("chunker", "Chunking"):
                ...
    """
    configure_logging()
    progress = create_progress()
    task_id = progress.add_task(name, total=total_steps)
    pipeline_log = get_logger("pipeline")
    pipeline_log.info(f"Pipeline started: {name}", pipeline=name, total_steps=total_steps)

    class PipelineContext:
        def __init__(self):
            self._progress = progress
            self._task_id = task_id

        @contextmanager
        def step(self, module: str, description: str, **extra):
            """Wrap a single pipeline step to time it and advance the bar."""
            self._progress.update(self._task_id, description=f"{name} → {description}")
            step_log = get_logger(module)
            step_log.info(f"Starting: {description}", step=description, status="starting", **extra)
            start = time.perf_counter()
            try:
                yield
                elapsed_ms = (time.perf_counter() - start) * 1000
                self._progress.advance(self._task_id)
                step_log.info(
                    f"Completed: {description}",
                    step=description, status="done",
                    duration_ms=round(elapsed_ms, 1), **extra
                )
            except Exception as e:
                elapsed_ms = (time.perf_counter() - start) * 1000
                step_log.error(
                    f"Failed: {description}",
                    step=description, status="failed",
                    duration_ms=round(elapsed_ms, 1), error=str(e), **extra
                )
                raise

    ctx = PipelineContext()
    if not _IS_TESTING:
        progress.start()
    try:
        yield ctx
    finally:
        pipeline_log.info(f"Pipeline finished: {name}", pipeline=name, status="done")
        if not _IS_TESTING:
            progress.update(task_id, description=f"{name} → [bold green]Done[/]")
            progress.stop()


# ─── Standalone Timer ─────────────────────────────────────────────────

@contextmanager
def timer_step(module: str, step_name: str, **extra_context):
    """
    Lightweight context manager to time a single block of work.
    Logs structured JSON with duration_ms.

    Usage:
        with timer_step("ocr", "OCR page 3", page=3):
            ...
    """
    configure_logging()
    log = get_logger(module)
    log.info(f"Starting: {step_name}", step=step_name, status="starting", **extra_context)
    start = time.perf_counter()
    try:
        yield
        elapsed_ms = (time.perf_counter() - start) * 1000
        log.info(
            f"Completed: {step_name}",
            step=step_name, status="done",
            duration_ms=round(elapsed_ms, 1), **extra_context
        )
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        log.error(
            f"Failed: {step_name}",
            step=step_name, status="failed",
            duration_ms=round(elapsed_ms, 1), error=str(e), **extra_context
        )
        raise
