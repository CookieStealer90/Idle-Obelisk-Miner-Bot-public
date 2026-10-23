"""Atomic whole-document JSON storage; in-process writes are serialized."""
import json
import os
from pathlib import Path
import tempfile
import threading

_write_lock = threading.Lock()


def read_json(path: Path):
    # Windows can refuse replacement while another thread has an open reader.
    with _write_lock:
        return json.loads(path.read_text(encoding="utf-8"))


def atomic_write_json(path: Path, data):
    # Serialize before touching disk, including rejection of NaN and Infinity.
    payload = json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    with _write_lock:
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                             prefix=f".{path.stem}_", suffix=".tmp", delete=False) as staging:
                temporary_path = Path(staging.name)
                staging.write(payload)
                staging.flush()
                os.fsync(staging.fileno())
            os.replace(temporary_path, path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
