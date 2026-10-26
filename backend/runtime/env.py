"""Environment for a deployment: an optional .env file (gitignored) and the data folder.

`load_dotenv()` reads KEY=VALUE lines from <repo>/.env when it exists and sets only the variables that are not already in the
environment, so a platform's own secrets always win. It never prints a value. `data_dir()` is where runs, private memory
and the project ledger live: DATA_DIR if set (mount a volume there), else <repo>/data.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_dotenv(path=None):
    p = Path(path) if path else ROOT / ".env"
    if not p.is_file():
        return []
    loaded = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return loaded


def data_dir():
    return Path(os.environ.get("DATA_DIR") or ROOT / "data")
