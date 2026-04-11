import os
import signal
import subprocess
import tempfile
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel, Field


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _log_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


MAX_BODY_BYTES = int(os.getenv("EXEC_MAX_BODY_BYTES", "1048576"))
DEFAULT_TIMEOUT_SECONDS = int(os.getenv("EXEC_TIMEOUT_SECONDS_DEFAULT", "600"))
MAX_TIMEOUT_SECONDS = int(os.getenv("EXEC_MAX_TIMEOUT_SECONDS", "1800"))
HEALTH_AUTH_CHECK_ENABLED = _env_bool("HEALTH_AUTH_CHECK_ENABLED", False)
ARTIFACT_DOWNLOAD_TIMEOUT_SECONDS = int(
    os.getenv("ARTIFACT_DOWNLOAD_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))
)
ARTIFACT_TMP_DIR = Path(os.getenv("ARTIFACT_TMP_DIR", tempfile.gettempdir()))
LOG_OUTPUT_MAX_CHARS = int(os.getenv("LOG_OUTPUT_MAX_CHARS", "500"))


class ExecRequest(BaseModel):
    script: str = Field(..., min_length=1)
    timeout_seconds: int | None = Field(default=None, ge=1)
    env: dict[str, str] | None = None


def _run_subprocess(
    command: list[str], timeout_seconds: int, env: dict[str, str] | None = None
) -> dict[str, Any]:
    started_at = _utc_now_iso()
    started_ts = time.perf_counter()
    timed_out = False

    proc_env = os.environ.copy()
    if env:
        proc_env.update(env)

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=proc_env,
        preexec_fn=os.setsid,
    )

    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
        exit_code = process.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(process.pid, signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
        exit_code = 124

    finished_at = _utc_now_iso()
    duration_ms = int((time.perf_counter() - started_ts) * 1000)
    ts = _log_ts()
    print(
        f"{ts} [exec] command={command[0]} exit_code={exit_code} "
        f"duration_ms={duration_ms} timed_out={timed_out}",
        flush=True,
    )
    for label, text in (("stdout", stdout), ("stderr", stderr)):
        stripped = text.strip()
        if stripped:
            preview = stripped if len(stripped) <= LOG_OUTPUT_MAX_CHARS else stripped[:LOG_OUTPUT_MAX_CHARS] + "…"
            print(f"{ts} [exec] {label}: {preview}", flush=True)

    return {
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "duration_ms": duration_ms,
        "started_at": started_at,
        "finished_at": finished_at,
        "timed_out": timed_out,
    }


@asynccontextmanager
async def lifespan(_: FastAPI):
    ts = _log_ts()
    try:
        ver = subprocess.run(
            ["nlm", "--version"], capture_output=True, text=True, timeout=10
        ).stdout.strip()
    except Exception:
        ver = "unknown"
    auth_check = "enabled" if HEALTH_AUTH_CHECK_ENABLED else "disabled"
    print(f"{ts} [startup] {ver}", flush=True)
    print(
        f"{ts} [startup] DEFAULT_TIMEOUT={DEFAULT_TIMEOUT_SECONDS}s "
        f"MAX_TIMEOUT={MAX_TIMEOUT_SECONDS}s "
        f"HEALTH_AUTH_CHECK={auth_check} "
        f"LOG_OUTPUT_MAX_CHARS={LOG_OUTPUT_MAX_CHARS}",
        flush=True,
    )
    yield


app = FastAPI(lifespan=lifespan)


@app.middleware("http")
async def body_size_limit(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_BODY_BYTES:
                return JSONResponse(
                    status_code=413,
                    content={"detail": f"Request body too large (max={MAX_BODY_BYTES} bytes)"},
                )
        except ValueError:
            pass
    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"detail": exc.errors()})


_reauth_lock = Lock()
_reauth_proc: subprocess.Popen | None = None


@app.post("/reauth/start")
def reauth_start() -> dict[str, Any]:
    global _reauth_proc
    with _reauth_lock:
        if _reauth_proc is not None and _reauth_proc.poll() is None:
            return {"status": "already_running", "message": "nlm login is already in progress. Open VNC at :6080 to complete."}
        ts = _log_ts()
        # PRESTART_CHROMIUM=1 で起動済みの Chrome (CDP :9222) を openclaw で使うと
        # Google がブラウザを記憶しておりパスワード入力が省略される場合がある
        prestart = _env_bool("NLM_PRESTART_CHROMIUM", False)
        cdp_port = os.getenv("NLM_CDP_PORT", "9222")
        if prestart:
            cmd = ["nlm", "login", "--provider", "openclaw", "--cdp-url", f"http://localhost:{cdp_port}"]
        else:
            cmd = ["nlm", "login"]
        print(f"{ts} [reauth] starting: {' '.join(cmd)} (complete via VNC :6080)", flush=True)
        _reauth_proc = subprocess.Popen(
            cmd,
            env=os.environ.copy(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    return {"status": "started", "pid": _reauth_proc.pid, "message": "Open VNC at :6080 to complete Google authentication."}


@app.get("/reauth/status")
def reauth_status() -> dict[str, Any]:
    proc_status: str
    with _reauth_lock:
        if _reauth_proc is None:
            proc_status = "not_started"
        elif _reauth_proc.poll() is None:
            proc_status = "running"
        else:
            proc_status = f"exited:{_reauth_proc.returncode}"

    result = _run_subprocess(["nlm", "login", "--check"], timeout_seconds=15)
    auth_ok = result["exit_code"] == 0 and not result["timed_out"]
    ts = _log_ts()
    print(f"{ts} [reauth] status check: auth_ok={auth_ok} proc={proc_status}", flush=True)
    return {
        "auth_ok": auth_ok,
        "login_proc": proc_status,
        "stdout": result["stdout"],
    }


@app.get("/health")
def health() -> dict[str, Any]:
    response: dict[str, Any] = {"ok": True}
    if not HEALTH_AUTH_CHECK_ENABLED:
        response["auth_check"] = {"enabled": False}
        return response

    result = _run_subprocess(["nlm", "login", "--check"], timeout_seconds=15)
    response["auth_check"] = {
        "enabled": True,
        "exit_code": result["exit_code"],
        "auth_ok": result["exit_code"] == 0 and not result["timed_out"],
        "duration_ms": result["duration_ms"],
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "timed_out": result["timed_out"],
    }
    return response


@app.post("/exec")
def exec_script(req: ExecRequest) -> dict[str, Any]:
    timeout_seconds = req.timeout_seconds or DEFAULT_TIMEOUT_SECONDS
    timeout_seconds = min(timeout_seconds, MAX_TIMEOUT_SECONDS)
    return _run_subprocess(
        ["bash", "-lc", req.script], timeout_seconds=timeout_seconds, env=req.env
    )


def _validate_token(value: str, label: str) -> str:
    if not value:
        raise HTTPException(status_code=400, detail=f"{label} is required")
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
    if any(ch not in allowed for ch in value):
        raise HTTPException(status_code=400, detail=f"invalid {label}")
    return value


def _is_not_found_error(result: dict[str, Any]) -> bool:
    text = f"{result['stdout']}\n{result['stderr']}".lower()
    markers = ("not found", "no such", "does not exist", "404")
    return any(marker in text for marker in markers)


def _detect_media_type(path: Path) -> tuple[str, str]:
    # Detect by file signature first, then by extension as fallback.
    with path.open("rb") as f:
        header = f.read(64)

    if header.startswith(b"%PDF-"):
        return "application/pdf", ".pdf"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"

    if len(header) >= 12 and header[4:8] == b"ftyp":
        brand = header[8:12]
        if brand in {b"M4A ", b"isom", b"mp41", b"mp42"}:
            return "audio/mp4", ".m4a"

    if header.startswith(b"ID3"):
        return "audio/mpeg", ".mp3"
    if len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0:
        return "audio/mpeg", ".mp3"

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "application/pdf", ".pdf"
    if suffix == ".png":
        return "image/png", ".png"
    if suffix == ".mp3":
        return "audio/mpeg", ".mp3"
    if suffix in {".m4a", ".mp4"}:
        return "audio/mp4", ".m4a"
    return "application/octet-stream", ""


@app.get("/artifacts/download")
def download_artifact(notebook_id: str, artifact_id: str, kind: str):
    safe_notebook_id = _validate_token(notebook_id, "notebook_id")
    safe_artifact_id = _validate_token(artifact_id, "artifact_id")
    safe_kind = _validate_token(kind, "kind")

    ARTIFACT_TMP_DIR.mkdir(parents=True, exist_ok=True)
    outfile = ARTIFACT_TMP_DIR / f"nlm-artifact-{safe_artifact_id}-{uuid4().hex}"
    command = [
        "nlm",
        "download",
        safe_kind,
        safe_notebook_id,
        "--id",
        safe_artifact_id,
        "--output",
        str(outfile),
    ]
    result = _run_subprocess(command, timeout_seconds=ARTIFACT_DOWNLOAD_TIMEOUT_SECONDS)

    if result["exit_code"] != 0 or result["timed_out"]:
        if outfile.exists():
            outfile.unlink(missing_ok=True)
        if _is_not_found_error(result):
            raise HTTPException(status_code=404, detail="artifact not found")
        raise HTTPException(
            status_code=500,
            detail={
                "message": "artifact download failed",
                "exit_code": result["exit_code"],
                "timed_out": result["timed_out"],
                "stderr": result["stderr"],
            },
        )

    if not outfile.exists():
        raise HTTPException(status_code=500, detail="artifact output not created")

    media_type, suggested_ext = _detect_media_type(outfile)
    download_name = safe_artifact_id
    if suggested_ext:
        download_name = f"{safe_artifact_id}{suggested_ext}"

    return FileResponse(
        path=outfile,
        filename=download_name,
        media_type=media_type,
        background=BackgroundTask(outfile.unlink, missing_ok=True),
    )
