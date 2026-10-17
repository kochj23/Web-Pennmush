"""
Web-Pennmush <-> Nova Games LLM relay (pull model)
Author: Jordan Koch (GitHub: kochj23)

The game never talks to an LLM. It queues template jobs; the relay (on the
internal Docker network) long-polls GET /relay/jobs, runs the fixed template
and POSTs the result back. Both relay endpoints require an HMAC signature
(CONTRACT.md section 9). If the relay is down, slow or busy, callers get None
and fall back to scripted lines.
"""
import asyncio
import hashlib
import hmac
import logging
import re
import secrets
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, Optional

from fastapi import APIRouter, HTTPException, Request, Response

log = logging.getLogger("webpennmush.relay")

MAX_SKEW_S = 60
JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_RESULT_BYTES = 16384


def sign(secret: str, ts: str, method: str, path_with_query: str, body: bytes) -> str:
    """hex(HMAC_SHA256(secret, ts \\n METHOD \\n path?query \\n hex(sha256(body))))"""
    msg = "\n".join([ts, method.upper(), path_with_query, hashlib.sha256(body).hexdigest()])
    return hmac.new(secret.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).hexdigest()


def verify(secret: str, ts: str, sig: str, method: str, path_with_query: str, body: bytes,
           now: Optional[float] = None) -> bool:
    if not secret or not ts or not sig:
        return False
    try:
        ts_int = int(ts)
    except ValueError:
        return False
    if abs((time.time() if now is None else now) - ts_int) > MAX_SKEW_S:
        return False
    return hmac.compare_digest(sign(secret, ts, method, path_with_query, body), sig)


@dataclass
class _Pending:
    job: Dict[str, Any]
    future: asyncio.Future
    created: float = field(default_factory=time.monotonic)
    handed_out: bool = False


class RelayJobQueue:
    """Bounded in-memory job queue with per-job futures."""

    def __init__(self, max_pending: int = 20):
        self.max_pending = max_pending
        self._pending: Dict[str, _Pending] = {}
        self._ready: Deque[str] = deque()
        self._cond: Optional[asyncio.Condition] = None
        self.stats = {"submitted": 0, "completed": 0, "fallback": 0, "timeouts": 0, "rejected_full": 0}

    def _condition(self) -> asyncio.Condition:
        if self._cond is None:
            self._cond = asyncio.Condition()
        return self._cond

    @property
    def depth(self) -> int:
        return len(self._pending)

    async def submit(self, template_id: str, vars: Dict[str, Any], player_id: str,
                     max_tokens: int, timeout: float = 60.0) -> Optional[Dict[str, Any]]:
        """Queue a job and wait for its result. None = use the scripted fallback."""
        if len(self._pending) >= self.max_pending:
            self.stats["rejected_full"] += 1
            return None
        job_id = secrets.token_hex(12)
        job = {"job_id": job_id, "template_id": template_id, "player_id": str(player_id)[:64],
               "vars": vars, "max_tokens": int(max_tokens)}
        fut = asyncio.get_running_loop().create_future()
        self._pending[job_id] = _Pending(job, fut)
        self.stats["submitted"] += 1
        cond = self._condition()
        async with cond:
            self._ready.append(job_id)
            cond.notify(1)
        try:
            result = await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            self.stats["timeouts"] += 1
            return None
        finally:
            self._pending.pop(job_id, None)
        if result.get("status") == "ok":
            self.stats["completed"] += 1
        else:
            self.stats["fallback"] += 1
        return result

    def _pop_ready(self) -> Optional[Dict[str, Any]]:
        while self._ready:
            job_id = self._ready.popleft()
            p = self._pending.get(job_id)
            if p and not p.future.done():
                p.handed_out = True
                return p.job
        return None

    async def next_job(self, wait: float) -> Optional[Dict[str, Any]]:
        """Long-poll for the next undelivered job (None after `wait` seconds)."""
        deadline = time.monotonic() + max(0.0, wait)
        cond = self._condition()
        async with cond:
            while True:
                job = self._pop_ready()
                if job is not None:
                    return job
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                try:
                    await asyncio.wait_for(cond.wait(), remaining)
                except asyncio.TimeoutError:
                    return self._pop_ready()

    def complete(self, job_id: str, result: Dict[str, Any]) -> bool:
        p = self._pending.get(job_id)
        if not p or p.future.done():
            return False
        p.future.set_result(result)
        return True


def build_router(queue: RelayJobQueue, secret_getter) -> APIRouter:
    """Signed relay endpoints. secret_getter() returns the shared secret ('' = disabled)."""
    router = APIRouter(prefix="/relay", include_in_schema=False)

    async def _check(request: Request, body: bytes):
        secret = secret_getter()
        if not secret:
            raise HTTPException(status_code=404)
        path = request.url.path + (f"?{request.url.query}" if request.url.query else "")
        if not verify(secret, request.headers.get("x-relay-ts", ""), request.headers.get("x-relay-sig", ""),
                      request.method, path, body):
            raise HTTPException(status_code=401, detail="bad signature")

    @router.get("/jobs")
    async def get_job(request: Request, wait: float = 20.0):
        await _check(request, b"")
        job = await queue.next_job(min(max(wait, 0.0), 30.0))
        if job is None:
            return Response(status_code=204)
        return job

    @router.post("/jobs/{job_id}/result")
    async def post_result(job_id: str, request: Request):
        body = await request.body()
        if len(body) > MAX_RESULT_BYTES:
            raise HTTPException(status_code=413)
        await _check(request, body)
        if not JOB_ID_RE.match(job_id):
            raise HTTPException(status_code=400)
        import json
        try:
            result = json.loads(body or b"{}")
            assert isinstance(result, dict)
        except Exception:
            raise HTTPException(status_code=400, detail="bad json")
        queue.complete(job_id, result)
        return Response(status_code=204)

    return router
