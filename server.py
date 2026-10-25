"""Dashboard server (FINAL BUILD phase 5). Standard library only.

    python server.py [--host 127.0.0.1] [--port 8000]      (HOST and PORT in the environment also work)

Binds 127.0.0.1 by default. Serves only the files in web/ and a small JSON API over the cases in data/runs/:

    GET  /api/health
    GET  /api/cases                         saved cases, newest first
    GET  /api/cases/<id>                    one case: run record, Case File, rulings, briefing, trap report, ...
    GET  /api/cases/<id>/events             events.jsonl as a list (the live feed replays it in time order)
    GET  /api/source?doc_id=&p=[&table_id=&row=][&case=]   masked paragraph text + header metadata (+ the named table row)
    POST /api/cases                         {question, pack?, provider: "mock" | "replay", from?}   never live

A live model call cannot be started from here: the provider is limited to mock and replay.
"""
import argparse
import json
import mimetypes
import os
import shutil
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from backend.ingestion.pipeline import ingest_pack  # noqa: E402
from backend.llm.provider import make_provider  # noqa: E402
from backend.runtime.config import load_config  # noqa: E402
from backend.runtime.orchestrator import run_full_case  # noqa: E402

WEB = ROOT / "web"
RUNS = ROOT / "data" / "runs"
DEFAULT_PACK = Path(os.environ["RAGNAROK_PACK_DIR"]) if os.environ.get("RAGNAROK_PACK_DIR") else ROOT / "dev_pack_E5"
CASE_FILES = {"run_record": "run_record.json", "case_file": "case_file.json", "rulings": "rulings.json", "briefing": "briefing.json",
              "trap_report": "trap_report.json", "claims": "claim_ledger.json", "calcs": "calc_ledger.json",
              "cross_examination": "cross_examination.json", "search_log": "search_log.jsonl", "config": "config.json"}
RUN_LOCK = threading.Lock()
_CORPORA = {}


def _json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _jsonl(path):
    try:
        return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
    except (OSError, ValueError):
        return None


def safe_case_dir(case_id):
    """A case directory directly under data/runs/, never anything else (no traversal)."""
    if not case_id or "/" in case_id or "\\" in case_id or case_id.startswith("."):
        return None
    d = (RUNS / case_id).resolve()
    return d if d.parent == RUNS.resolve() and d.is_dir() else None


def list_cases():
    out = []
    if RUNS.exists():
        for d in RUNS.iterdir():
            rec = _json(d / "run_record.json") if d.is_dir() else None
            if rec:
                out.append({"id": d.name, "case_id": rec["case_id"], "question": rec["question"], "status": rec["status"],
                            "provider": rec["provider"], "completion": rec.get("briefing_completion"),
                            "briefing_hash": rec.get("briefing_hash"), "spend": rec["spend"], "ac": rec["ac"],
                            "modified": (d / "run_record.json").stat().st_mtime})
    return sorted(out, key=lambda c: -c["modified"])


def get_case(case_id):
    d = safe_case_dir(case_id)
    if d is None:
        return None
    body = {"id": d.name}
    for key, name in CASE_FILES.items():
        body[key] = _jsonl(d / name) if name.endswith(".jsonl") else _json(d / name)
    md = d / "briefing.md"
    body["briefing_md"] = md.read_text(encoding="utf-8") if md.exists() else None
    body["has_replay_log"] = (d / "llm_calls.jsonl").exists()
    return body


def corpus_for(case_id=None):
    pack = DEFAULT_PACK
    d = safe_case_dir(case_id) if case_id else None
    rec = _json(d / "run_record.json") if d else None
    if rec and rec.get("pack_paths"):
        p = Path(rec["pack_paths"][-1])
        pack = p if p.is_absolute() else ROOT / p
    key = str(pack.resolve())
    if key not in _CORPORA:
        _CORPORA[key] = ingest_pack(pack)
    return _CORPORA[key]


def source(doc_id, para, case_id=None, table_id=None, row=None):
    corpus = corpus_for(case_id)
    rec = corpus.records.get(doc_id)
    if rec is None:
        return None
    paragraph = next((p for p in rec["paragraphs"] if p["id"] == para), None)
    if paragraph is None:
        return None
    out = {"doc_id": doc_id, "paragraph": para, "text": paragraph["text_masked"], "masked": paragraph["masked"],
           "title": rec["agent_title"], "header": rec["agent_header"], "tier": rec["reliability"], "source_type": rec["source_type"],
           "source_name": rec["source_name"], "pub_date": rec["pub_date"], "pub_time": rec["pub_time"], "event_id": rec["event_id"],
           "flags": sorted(rec["flags"]), "evidence_family_id": rec["evidence_family_id"],
           "paragraphs": [p["id"] for p in rec["paragraphs"]], "highlight": None}
    rows = [r for r in rec["trade_rows"] if r["paragraph"] == para]
    if table_id or row:
        rows = [r for r in rows if (not table_id or r["table_id"] == table_id)
                and (not row or str(r["native_row_number"]) == str(row) or r["row_key"] == row)]
    if rows:
        out["highlight"] = [r["raw_text"] for r in rows]
        out["rows"] = [{"row_key": r["row_key"], "table_id": r["table_id"], "native_row_number": r["native_row_number"],
                        "month": r["month"], "flags": list(r["flags"])} for r in rows]
    return out


def start_case(body):
    question = (body.get("question") or "").strip()
    provider_name = body.get("provider", "mock")
    if provider_name not in ("mock", "replay"):
        return 400, {"error": "the dashboard runs the mock or replay provider only; a live run is started by the budget owner from the command line"}
    config = load_config()
    if provider_name == "replay":
        src = safe_case_dir(body.get("from"))
        if src is None or not (src / "llm_calls.jsonl").exists():
            return 400, {"error": "replay needs `from`: a saved case with llm_calls.jsonl"}
        rec = _json(src / "run_record.json")
        cfg = load_config(src / "config.json") if (src / "config.json").exists() else config
        provider = make_provider("replay", cfg, path=src / "llm_calls.jsonl")
        with RUN_LOCK, tempfile.TemporaryDirectory(prefix="replay_mem_") as tmp:
            mem = Path(tmp) / "memory"
            if (src / "memory_before").exists():           # start from the memory the original case started from
                shutil.copytree(src / "memory_before", mem)
            res = run_full_case(rec["question"], rec["pack_paths"], cfg, provider, RUNS, mem,
                                case_id=rec["case_id"], created_at=rec["created_at"], out_name=f"{src.name}__replay")
        same = res["record"]["briefing_hash"] == rec.get("briefing_hash")
        return 200, {"id": res["out_dir"].name, "replay_matches_original": same, "spend": res["record"]["spend"]}
    if not question:
        return 400, {"error": "missing question"}
    pack = body.get("pack")
    pack_path = DEFAULT_PACK if not pack else (ROOT / pack).resolve()
    inside = pack_path == DEFAULT_PACK.resolve() or ROOT.resolve() in pack_path.parents
    if not inside or not (pack_path / "manifest.json").exists():
        return 400, {"error": "pack must be a folder inside the repository that holds manifest.json"}
    with RUN_LOCK:
        res = run_full_case(question, [pack_path], config, make_provider("mock", config), RUNS, ROOT / "data" / "memory")
    return 200, {"id": res["out_dir"].name, "status": res["case_file"]["status"], "completion": res["record"]["briefing_completion"]}


class Handler(BaseHTTPRequestHandler):
    server_version = "TrialDashboard/1"

    def log_message(self, fmt, *args):
        sys.stderr.write("[dashboard] " + (fmt % args) + "\n")

    def _send(self, code, payload, ctype="application/json; charset=utf-8"):
        data = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urlparse(self.path)
        path, q = unquote(url.path), parse_qs(url.query)
        if path == "/api/health":
            return self._send(200, {"ok": True, "cases": len(list_cases()), "providers": ["mock", "replay"]})
        if path == "/api/cases":
            return self._send(200, list_cases())
        if path.startswith("/api/cases/"):
            parts = path.split("/")[3:]
            case_id = parts[0] if parts else ""
            if len(parts) == 2 and parts[1] == "events":
                d = safe_case_dir(case_id)
                events = _jsonl(d / "events.jsonl") if d else None
                return self._send(200 if events is not None else 404, events if events is not None else {"error": "no events for this case"})
            body = get_case(case_id) if len(parts) == 1 else None
            return self._send(200 if body else 404, body or {"error": "no such case"})
        if path == "/api/source":
            try:
                out = source(q.get("doc_id", [""])[0], q.get("p", [""])[0], (q.get("case") or [None])[0],
                             (q.get("table_id") or [None])[0], (q.get("row") or [None])[0])
            except (OSError, ValueError) as e:
                return self._send(500, {"error": str(e)})
            return self._send(200 if out else 404, out or {"error": "no such paragraph in this pack"})
        return self._static(path)

    def _static(self, path):
        rel = "index.html" if path in ("", "/") else path.lstrip("/")
        f = (WEB / rel).resolve()
        if WEB.resolve() not in f.parents or not f.is_file():
            return self._send(404, {"error": "not found"})
        ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        self._send(200, f.read_bytes(), ctype)

    def do_POST(self):
        path = urlparse(self.path).path
        if path != "/api/cases":
            return self._send(404, {"error": "not found"})
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            code, payload = start_case(body)
        except ValueError:
            code, payload = 400, {"error": "invalid JSON body"}
        except Exception as e:                    # a failed run must not take the server down
            code, payload = 500, {"error": f"{type(e).__name__}: {e}"}
        self._send(code, payload)


def run_server(host, port):
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Dashboard on http://{host}:{port}  (cases in {RUNS}; mock and replay only)", flush=True)
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
