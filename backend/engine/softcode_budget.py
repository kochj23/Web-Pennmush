"""
Web-Pennmush softcode evaluation budget
Author: Jordan Koch (GitHub: kochj23)

One budget covers a whole top-level evaluation (every nested eval, iter, u(),
loop, attribute call...). It bounds function calls, wall time, nesting depth
and output size so a single player's softcode can't wedge the event loop.

SoftcodeBudgetExceeded derives from BaseException on purpose: the interpreter
has many broad `except Exception`/bare excepts that would otherwise swallow it.
The budget is also sticky (every later tick re-raises), so even a bare except
can't keep a runaway evaluation going.
"""
import time
from contextvars import ContextVar
from typing import List, Optional


class SoftcodeBudgetExceeded(BaseException):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


_current: ContextVar[Optional["EvalBudget"]] = ContextVar("softcode_budget", default=None)

# Functions whose numeric arguments size their output or loop count.
SIZE_FUNCS = {
    "repeat", "space", "center", "ljust", "rjust", "lnum", "loop", "repeat_times", "dice", "die",
    "table", "box", "underline", "frame", "fill", "wrap", "wordwrap", "justify", "columnar",
    "tabular", "tab", "fold_text", "line", "hr", "pad",
}
MAX_SIZE_ARG = 4096


def check_size_args(func_name: str, args: List[str]) -> Optional[str]:
    """Reject absurd numeric size/count arguments before the function allocates."""
    if func_name not in SIZE_FUNCS:
        return None
    for arg in args:
        a = arg.strip()
        if a.lstrip("-").isdigit() and len(a) <= 32:
            if abs(int(a)) > MAX_SIZE_ARG:
                return "#-1 ARGUMENT TOO LARGE"
        elif a.lstrip("-").isdigit():
            return "#-1 ARGUMENT TOO LARGE"
    return None


class EvalBudget:
    def __init__(self, max_calls: int = 10000, max_ms: int = 250, max_depth: int = 50, max_output: int = 16384,
                 clock=time.monotonic):
        self.max_calls = max_calls
        self.max_s = max_ms / 1000.0
        self.max_depth = max_depth
        self.max_output = max_output
        self.clock = clock
        self.started = clock()
        self.calls = 0
        self.depth = 0
        self.exceeded: Optional[str] = None

    @classmethod
    def from_settings(cls) -> "EvalBudget":
        from backend.config import settings
        return cls(settings.SOFTCODE_MAX_CALLS, settings.SOFTCODE_MAX_MS,
                   settings.SOFTCODE_MAX_DEPTH, settings.SOFTCODE_MAX_OUTPUT)

    def _fail(self, reason: str):
        if self.exceeded is None:
            self.exceeded = reason
        raise SoftcodeBudgetExceeded(self.exceeded)

    def tick(self):
        if self.exceeded:
            self._fail(self.exceeded)
        self.calls += 1
        if self.calls > self.max_calls:
            self._fail("BUDGET EXCEEDED (function calls)")
        if self.clock() - self.started > self.max_s:
            self._fail("BUDGET EXCEEDED (time)")

    def enter(self):
        if self.exceeded:
            self._fail(self.exceeded)
        self.depth += 1
        if self.depth > self.max_depth:
            self._fail("BUDGET EXCEEDED (recursion)")

    def leave(self):
        self.depth = max(0, self.depth - 1)

    def check_output(self, text: str):
        if len(text) > self.max_output:
            self._fail("BUDGET EXCEEDED (output)")


def current_budget() -> Optional[EvalBudget]:
    return _current.get()


def activate_budget(budget: EvalBudget):
    return _current.set(budget)


def deactivate_budget(token):
    _current.reset(token)
