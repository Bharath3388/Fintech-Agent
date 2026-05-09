"""
Structured logger with step tracking, timing, and colour-coded output.
Every agent step is logged with: step number, step name, duration, and status.
Supports thread-local SSE queue for real-time streaming.
"""

import logging
import time
import sys
import threading
from functools import wraps


# ── Colour codes for terminal ─────────────────────────────────────────────
class _C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    CYAN   = "\033[96m"
    GREY   = "\033[90m"
    BLUE   = "\033[94m"
    MAGENTA = "\033[95m"


# ── Thread-local SSE queue ────────────────────────────────────────────────
_tls = threading.local()


def set_sse_queue(q):
    """Set a queue for the current thread to receive SSE events."""
    _tls.sse_queue = q


def _push_sse(event: dict):
    """Push an event to the current thread's SSE queue (if set)."""
    q = getattr(_tls, 'sse_queue', None)
    if q is not None:
        q.put(event)


# ── Step counter (global per agent) ───────────────────────────────────────
_step_counters: dict[str, int] = {}


def _next_step(agent: str) -> int:
    _step_counters.setdefault(agent, 0)
    _step_counters[agent] += 1
    return _step_counters[agent]


def reset_steps(agent: str | None = None):
    if agent:
        _step_counters[agent] = 0
    else:
        _step_counters.clear()


# ── Main logger setup ────────────────────────────────────────────────────
def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
    return logger


# ── Logging helpers ───────────────────────────────────────────────────────
def log_banner(agent_name: str):
    """Print a bold banner for agent start."""
    line = "=" * 70
    print(f"\n{_C.BOLD}{_C.CYAN}{line}")
    print(f"  AGENT: {agent_name}")
    print(f"{line}{_C.RESET}\n")
    _push_sse({"type": "agent_start", "agent": agent_name})


def log_step_start(agent: str, description: str) -> tuple[int, float]:
    """Log the start of a step. Returns (step_number, start_time)."""
    step = _next_step(agent)
    print(f"{_C.BLUE}[{agent}] Step {step}: {description} ...{_C.RESET}")
    _push_sse({"type": "step_start", "agent": agent, "description": description, "step": step})
    return step, time.time()


def log_step_end(agent: str, step: int, start_time: float, summary: str = ""):
    """Log the end of a step with duration."""
    elapsed = time.time() - start_time
    status = f"{_C.GREEN}DONE{_C.RESET}"
    detail = f" → {summary}" if summary else ""
    print(
        f"{_C.GREEN}[{agent}] Step {step}: {status} "
        f"({elapsed:.2f}s){detail}{_C.RESET}"
    )
    _push_sse({"type": "step_end", "agent": agent, "step": step, "duration": round(elapsed, 2), "summary": summary})


def log_step_fail(agent: str, step: int, start_time: float, error: str):
    """Log a failed step."""
    elapsed = time.time() - start_time
    print(
        f"{_C.RED}[{agent}] Step {step}: FAILED "
        f"({elapsed:.2f}s) → {error}{_C.RESET}"
    )
    _push_sse({"type": "step_fail", "agent": agent, "step": step, "duration": round(elapsed, 2), "error": error})


def log_info(agent: str, message: str):
    print(f"{_C.GREY}[{agent}]   ℹ {message}{_C.RESET}")
    _push_sse({"type": "info", "agent": agent, "message": message.strip()})


def log_warn(agent: str, message: str):
    print(f"{_C.YELLOW}[{agent}]   ⚠ {message}{_C.RESET}")
    _push_sse({"type": "warning", "agent": agent, "message": message.strip()})


def log_error(agent: str, message: str):
    print(f"{_C.RED}[{agent}]   ✖ {message}{_C.RESET}")
    _push_sse({"type": "error", "agent": agent, "message": message.strip()})


def log_success(agent: str, message: str):
    print(f"{_C.GREEN}[{agent}]   ✔ {message}{_C.RESET}")
    _push_sse({"type": "success", "agent": agent, "message": message.strip()})


def log_data(agent: str, label: str, value):
    """Log a key-value data point."""
    print(f"{_C.GREY}[{agent}]     {label}: {_C.BOLD}{value}{_C.RESET}")


def log_table(agent: str, headers: list[str], rows: list[list]):
    """Print a simple aligned table."""
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    header_line = " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    sep_line = "-+-".join("-" * w for w in widths)
    print(f"{_C.GREY}[{agent}]     {header_line}{_C.RESET}")
    print(f"{_C.GREY}[{agent}]     {sep_line}{_C.RESET}")
    for row in rows:
        line = " | ".join(str(c).ljust(widths[i]) for i, c in enumerate(row))
        print(f"{_C.GREY}[{agent}]     {line}{_C.RESET}")


def log_metric_result(agent: str, result):
    """Log metric computation result. Accepts a MetricResult object."""
    mid = getattr(result, 'metric_id', '?')
    name = getattr(result, 'name', '')
    status = getattr(result, 'status', 'error')
    if status == "ok":
        icon = f"{_C.GREEN}✔{_C.RESET}"
    elif status == "partial":
        icon = f"{_C.YELLOW}~{_C.RESET}"
    elif status == "not_available":
        icon = f"{_C.YELLOW}✗{_C.RESET}"
    else:
        icon = f"{_C.RED}✖{_C.RESET}"
    print(f"{_C.GREY}[{agent}]   {icon} {mid} — {name}: {status.upper()}{_C.RESET}")


# ── Timer decorator for functions ─────────────────────────────────────────
def timed(agent_name: str, step_desc: str):
    """Decorator that logs step start/end with timing."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            step, t0 = log_step_start(agent_name, step_desc)
            try:
                result = func(*args, **kwargs)
                log_step_end(agent_name, step, t0)
                return result
            except Exception as e:
                log_step_fail(agent_name, step, t0, str(e))
                raise
        return wrapper
    return decorator
