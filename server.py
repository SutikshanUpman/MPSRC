"""Trial of the Nine Realms: the web console and its API. Standard library only.

    python server.py [--host 127.0.0.1] [--port 8000]      (HOST and PORT in the environment also work)

Serves the console (web/, built from ui/) and the API it was designed around, on top of the Python trial engine:

    GET  /api/health  /api/meta
    GET  /api/runs                       saved and running trials, newest first
    POST /api/runs                       {question, as_of_date?, runemark_path?, provider: "ollama" | "anthropic",
                                          model?, odin_model?, base_url?}   or   {provider: "replay", from}
    GET  /api/runs/<id>                  summary + the trial record (null while it runs)
    GET  /api/runs/<id>/events?after=N   the event log, as it is written
    GET  /api/runs/<id>/feed             the sealed archive as of the case's date
    GET  /api/runs/<id>/sources/<sid>    a document, one paragraph (DOC:P#) or a trade row (DOC|YYYY-MM)

Deployment (see docs/DEPLOY.md): HOST=0.0.0.0 to listen on every interface, PORT (platforms inject it), DATA_DIR for the
volume that holds runs, private memory and the ledger, CONSOLE_PASSWORD for HTTP Basic auth on everything but /api/health
(required whenever the server listens beyond localhost), MAX_QUEUED_RUNS, FINAL_ROUND=1 for the final-round ledger ceiling.
Variables may come from the platform or from a gitignored .env file; the platform's always win.

Binds 127.0.0.1 by default. The console runs the trial on a model you choose: a local one through Ollama (free), an
or Claude. Keys come from the server's environment only, never from a page. Claude is metered and also needs LIVE=1, BUDGET_OWNER and verified prices in the server's environment;
the per-case cap, the Odin reserve and the project ledger apply to it as on the command line.
"""
import argparse
import base64
import hmac
import json
import mimetypes
import os
import shutil
import sys
import tempfile
import threading
import traceback
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from backend.agents.heimdall import parse_as_of  # noqa: E402
from backend.ingestion.pipeline import ingest_pack  # noqa: E402
from backend.llm.factory import SpecError, build_provider, provider_status  # noqa: E402
from backend.llm.provider import ProviderError, ReplayProvider, ollama_models  # noqa: E402
from backend.runtime import trial_view  # noqa: E402
from backend.runtime.config import ConfigError, load_config  # noqa: E402
from backend.runtime.env import data_dir, load_dotenv  # noqa: E402
from backend.runtime.orchestrator import run_full_case  # noqa: E402

load_dotenv()                                  # a gitignored .env, never overriding the platform's own variables

WEB = ROOT / "web"
DATA = data_dir()
RUNS = DATA / "runs"
MEMORY = DATA / "memory"
DEFAULT_PACK = Path(os.environ["RAGNAROK_PACK_DIR"]) if os.environ.get("RAGNAROK_PACK_DIR") else ROOT / "dev_pack_E5"
VERSION = "1.0"
JOBS = {}                      # run id -> {"status", "events", "question", "created_at", "error", "provider", "pack"}
JOBS_LOCK = threading.Lock()
RUN_LOCK = threading.Lock()    # one trial at a time: they share the private-memory folder
_CORPORA = {}


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def safe_run_dir(run_id):
    """A run directory directly under data/runs/, never anything else (no traversal)."""
    if not run_id or "/" in run_id or "\\" in run_id or run_id.startswith("."):
        return None
    d = (RUNS / run_id).resolve()
    return d if d.parent == RUNS.resolve() and d.is_dir() else None


def corpus_for(pack):
    key = str(Path(pack).resolve())
    if key not in _CORPORA:
        _CORPORA[key] = ingest_pack(pack)
    return _CORPORA[key]


def pack_of(run_id):
    d = safe_run_dir(run_id)
    rec = trial_view._read(d / "run_record.json") if d else None
    if rec and rec.get("pack_paths"):
        p = Path(rec["pack_paths"][-1])
        return p if p.is_absolute() else ROOT / p
    job = JOBS.get(run_id)
    return Path(job["pack"]) if job else DEFAULT_PACK


def summary(run_id):
    job = JOBS.get(run_id)
    d = safe_run_dir(run_id)
    rec = trial_view._read(d / "run_record.json") if d else None
    if rec:
        b = trial_view._read(d / "briefing.json")
        cf = trial_view._read(d / "case_file.json") or {}
        status = ("completed" if b and b.get("header", {}).get("completion_status") == "COMPLETE" and "event_status" not in b
                  else "partial" if b and "event_status" not in b else "unverified" if cf.get("status") != "OPEN" else "failed")
        return {"run_id": run_id, "question": rec["question"], "mode": "trial", "status": status, "created_at": cf.get("created_at", ""),
                "error": None, "provider": rec["provider"], "briefing_hash": rec.get("briefing_hash"), "spend": rec["spend"]}
    if job:
        return {"run_id": run_id, "question": job["question"], "mode": "trial", "status": job["status"], "created_at": job["created_at"],
                "error": job["error"], "provider": job["provider"]}
    return None


def list_runs():
    ids = set(JOBS)
    if RUNS.exists():
        ids |= {d.name for d in RUNS.iterdir() if d.is_dir() and (d / "run_record.json").exists()}
    rows = [s for s in (summary(i) for i in ids) if s]
    return sorted(rows, key=lambda r: r["created_at"], reverse=True)


def get_run(run_id):
    s = summary(run_id)
    if s is None:
        return None
    d = safe_run_dir(run_id)
    result = None
    if d and (d / "run_record.json").exists():
        bundle = trial_view.load_bundle(d)
        result = trial_view.trial_result(run_id, bundle, corpus_for(pack_of(run_id)))
    return dict(s, result=result)


def get_events(run_id, after):
    job = JOBS.get(run_id)
    d = safe_run_dir(run_id)
    if d and (d / "run_record.json").exists():
        return trial_view.run_events(trial_view.load_bundle(d), after)
    if job:
        with JOBS_LOCK:
            return [e for e in job["events"] if e["seq"] > after]
    return None


def _push(job, e):
    with JOBS_LOCK:
        job["events"].append({"seq": len(job["events"]) + 1, "type": e["event_type"], "timestamp": e["timestamp"], "step": None,
                              "agent": e["actor"], "data": e["payload"], "level": e["level"]})


def _run_job(run_id, question, pack, provider, config, src, as_of):
    job = JOBS[run_id]
    try:
        if job["provider"] == "replay":
            rec = trial_view._read(src / "run_record.json")
            with RUN_LOCK, tempfile.TemporaryDirectory(prefix="replay_mem_") as tmp:
                mem = Path(tmp) / "memory"
                if (src / "memory_before").exists():
                    shutil.copytree(src / "memory_before", mem)
                job["status"] = "running"
                run_full_case(rec["question"], rec["pack_paths"], config, provider, RUNS, mem, case_id=rec["case_id"],
                              created_at=rec["created_at"], out_name=run_id, on_event=lambda e: _push(job, e),
                              ledger_path=DATA / "ledger.json")
        else:
            if as_of and parse_as_of(question) is None:          # the question's own date wins; the field only fills a gap
                question = f"As of {as_of}: {question}"
            with RUN_LOCK:
                job["status"] = "running"
                run_full_case(question, [pack], config, provider, RUNS, MEMORY, out_name=run_id, on_event=lambda e: _push(job, e),
                              final_round=os.environ.get("FINAL_ROUND") == "1", ledger_path=DATA / "ledger.json")
        job["status"] = "done"
    except Exception as e:                       # a failed run must not take the server down
        job["status"], job["error"] = "failed", f"{type(e).__name__}: {e}"
        traceback.print_exc()                    # the page shows the one-line error; the server log keeps the whole trace
    finally:
        if job["status"] == "done":
            JOBS.pop(run_id, None)               # from here on the run is read from its files


def start_run(body):
    name = (body.get("provider") or body.get("profile") or "").lower()
    run_id = f"run-{uuid.uuid4().hex[:10]}"
    try:
        if name == "replay":
            src = safe_run_dir(body.get("from"))
            if src is None or not (src / "llm_calls.jsonl").exists():
                return 400, {"detail": "replay needs `from`: a saved run with its recorded model calls"}
            rec = trial_view._read(src / "run_record.json")
            config = load_config(src / "config.json") if (src / "config.json").exists() else load_config()
            provider = ReplayProvider(config, src / "llm_calls.jsonl")
            question, pack = rec["question"], pack_of(src.name)
        else:
            question = (body.get("question") or "").strip()
            if not question or len(question) > 4000:
                return 400, {"detail": "a question of 1 to 4,000 characters is required"}
            raw = body.get("runemark_path")
            pack = DEFAULT_PACK if not raw else (ROOT / raw).resolve()
            inside = pack == DEFAULT_PACK.resolve() or ROOT.resolve() in pack.parents
            if not inside or not (pack / "manifest.json").exists():
                return 400, {"detail": "the evidence folder must be a Runemark pack inside the repository (it holds manifest.json)"}
            src = None
            provider, config = PROVIDER_FACTORY({k: body.get(k) for k in ("provider", "model", "odin_model", "base_url")})
    except (SpecError, ProviderError, ConfigError) as e:
        return 400, {"detail": str(e)}
    active = sum(1 for j in JOBS.values() if j["status"] in ("queued", "running"))
    if active >= int(os.environ.get("MAX_QUEUED_RUNS", "3")):
        return 429, {"detail": f"{active} trials are already queued or running; wait for one to finish"}
    JOBS[run_id] = {"status": "queued", "events": [], "question": question, "created_at": now(), "error": None,
                    "provider": name, "pack": str(pack)}
    threading.Thread(target=_run_job, args=(run_id, question, pack, provider, config, src, body.get("as_of_date")), daemon=True).start()
    return 202, summary(run_id)


PROVIDER_FACTORY = build_provider      # tests swap this for an offline stand-in


def meta():
    providers = provider_status()
    return {"version": VERSION, "modes": ["trial"], "profiles": [p["name"] for p in providers], "tools": [],
            "providers": providers + [{"name": "replay", "label": "Replay", "configured": True, "free": True,
                                       "description": "Re-runs a saved trial from its recorded model calls. $0, byte-identical.",
                                       "hint": None, "models": [], "needs_model": False, "default_model": None}],
            "models": [{"value": m, "label": f"{p['label']} · {m}", "spec": f"{p['name']}:{m}", "default": False}
                       for p in providers for m in p["models"]]}


class Handler(BaseHTTPRequestHandler):
    server_version = "NineRealms/1"

    def log_message(self, fmt, *args):
        sys.stderr.write("[console] " + (fmt % args) + "\n")

    def _authorised(self):
        """HTTP Basic auth with CONSOLE_PASSWORD (any user name) on everything except /api/health."""
        password = os.environ.get("CONSOLE_PASSWORD")
        if not password or urlparse(self.path).path == "/api/health":
            return True
        header = self.headers.get("Authorization") or ""
        if header.startswith("Basic "):
            try:
                given = base64.b64decode(header[6:]).decode("utf-8").partition(":")[2]
            except (ValueError, UnicodeDecodeError):
                given = ""
            if hmac.compare_digest(given.encode(), password.encode()):
                return True
        data = b'{"detail": "sign in: the console needs its password"}'
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Trial of the Nine Realms", charset="UTF-8"')
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        return False

    def _send(self, code, payload, ctype="application/json; charset=utf-8"):
        data = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                         "font-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def _err(self, code, detail):
        self._send(code, {"detail": detail})

    def do_GET(self):
        if not self._authorised():
            return
        url = urlparse(self.path)
        path, q = unquote(url.path), parse_qs(url.query)
        if path == "/api/health":
            return self._send(200, {"status": "ok", "version": VERSION, "runs": len(list_runs()), "ollama": ollama_models() is not None})
        if path == "/api/meta":
            return self._send(200, meta())
        if path == "/api/runs":
            return self._send(200, list_runs())
        if path.startswith("/api/runs/"):
            parts = path.split("/")[3:]
            run_id = parts[0] if parts else ""
            rest = parts[1:]
            if not rest:
                body = get_run(run_id)
                return self._send(200, body) if body else self._err(404, "no such run")
            if rest == ["events"]:
                try:
                    after = int((q.get("after") or ["0"])[0])
                except ValueError:
                    after = 0
                events = get_events(run_id, after)
                return self._send(200, events) if events is not None else self._err(404, "no such run")
            if rest == ["feed"]:
                return self._feed(run_id)
            if rest[0] == "sources" and len(rest) >= 2:
                return self._source(run_id, "/".join(rest[1:]))
            return self._err(404, "not found")
        if path.startswith("/api/"):
            return self._err(404, "not found")
        return self._static(path)

    def _feed(self, run_id):
        d = safe_run_dir(run_id)
        cf = trial_view._read(d / "case_file.json") if d else None
        if not cf or not cf.get("as_of_date"):
            return self._err(404, "this run has no case file yet")
        try:
            items = trial_view.feed(corpus_for(pack_of(run_id)), cf["as_of_date"], cf["event_id"] or "")
        except (OSError, ValueError) as e:
            return self._err(500, str(e))
        self._send(200, items)

    def _source(self, run_id, source_id):
        if summary(run_id) is None:
            return self._err(404, "no such run")
        try:
            out = trial_view.source(corpus_for(pack_of(run_id)), source_id)
        except (OSError, ValueError) as e:
            return self._err(500, str(e))
        self._send(200, out) if out else self._err(404, "no such source in this pack")

    def _static(self, path):
        rel = "index.html" if path in ("", "/") else path.lstrip("/")
        f = (WEB / rel).resolve()
        if WEB.resolve() not in f.parents or not f.is_file():
            if "." not in Path(rel).name and ".." not in rel and (WEB / "index.html").is_file():     # a console route (/app, /demo, ...)
                f = WEB / "index.html"
            else:
                return self._err(404, "not found")
        ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        self._send(200, f.read_bytes(), ctype)

    def do_POST(self):
        if not self._authorised():
            return
        if urlparse(self.path).path != "/api/runs":
            return self._err(404, "not found")
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length > 1_000_000:
                return self._err(413, "request too large")
            code, payload = start_run(json.loads(self.rfile.read(length) or b"{}"))
        except ValueError:
            code, payload = 400, {"detail": "invalid JSON body"}
        except Exception as e:
            code, payload = 500, {"detail": f"{type(e).__name__}: {e}"}
        self._send(code, payload)


def is_loopback_host(host):
    return host in ("127.0.0.1", "localhost", "::1")


def run_server(host, port):
    if not is_loopback_host(host) and not os.environ.get("CONSOLE_PASSWORD") and os.environ.get("CONSOLE_ALLOW_OPEN") != "1":
        sys.exit("refusing to listen on " + host + " without CONSOLE_PASSWORD: anyone who can reach the server could start runs "
                 "on your API key. Set CONSOLE_PASSWORD (or CONSOLE_ALLOW_OPEN=1 on a private network).")
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Trial of the Nine Realms on http://{host}:{port}  (runs in {RUNS})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    args = ap.parse_args()
    run_server(args.host, args.port)
