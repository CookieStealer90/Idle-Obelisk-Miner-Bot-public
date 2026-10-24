"""Persistent, atomic PNG inbox and conservative pending-click tracking."""
import hashlib
import math
import os
from pathlib import Path
import re
import threading
import time
import uuid
from io import BytesIO

import cv2
from PIL import Image, PngImagePlugin, UnidentifiedImageError

from config.json_store import atomic_write_json, read_json

_archive_lock = threading.RLock()

class NoticeArchive:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.lock = _archive_lock
        self._entries_cache = {}

    def _path(self, identifier):
        if not isinstance(identifier, str) or not re.fullmatch(r"[0-9a-f]{32}", identifier):
            raise ValueError("Invalid notice ID")
        return self.directory / (identifier + ".png")

    def entries(self):
        return self.snapshot()[0]

    def snapshot(self):
        """Stat files on refresh; verify/read PNG metadata only when changed."""
        with self.lock:
            result = []
            self.unreadable_count = 0
            current = {}
            for path in self.directory.glob("*.png"):
                try:
                    stat = path.stat()
                    signature = (stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size, stat.st_ino)
                    cached = self._entries_cache.get(path.name)
                    if cached is not None and cached[0] == signature:
                        entry = cached[1]
                    else:
                        entry = self._entry(path)
                    current[path.name] = (signature, entry)
                    if entry is None:
                        self.unreadable_count += 1
                    else:
                        result.append(dict(entry))
                except (OSError, ValueError, KeyError):
                    self.unreadable_count += 1
            self._entries_cache = current
            return sorted(result, key=lambda entry: (entry["created_ts"], entry["id"])), self.unreadable_count

    def _entry(self, path):
        try:
            self._path(path.stem)
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                created = float(image.info["created_ts"])
                if not math.isfinite(created):
                    raise ValueError("Invalid notice timestamp")
                return {"id": path.stem, "created_ts": created,
                        "variant": image.info.get("variant", "notice"),
                        "width": image.width, "height": image.height}
        except (UnidentifiedImageError, ValueError, KeyError, SyntaxError):
            return None

    def read(self, identifier):
        with self.lock:
            return self._path(identifier).read_bytes()

    def delete(self, identifier):
        with self.lock:
            # Idempotent, including concurrent acknowledgement by two clients.
            self._path(identifier).unlink(missing_ok=True)

    def _pending(self):
        path = self.directory / "pending.json"
        return read_json(path) if path.exists() else {}

    def clear_pending(self):
        with self.lock:
            (self.directory / "pending.json").unlink(missing_ok=True)

    def prepare(self, crop, variant, max_mb, identity=None):
        """Return (id, already_attempted). Saving must succeed before any tap."""
        fingerprint = hashlib.sha256((crop if identity is None else identity).tobytes()).hexdigest()
        with self.lock:
            self.directory.mkdir(parents=True, exist_ok=True)
            pending = self._pending()
            if pending.get("fingerprint") == fingerprint:
                return pending["id"], bool(pending.get("attempted"))
            identifier = uuid.uuid4().hex
            metadata = PngImagePlugin.PngInfo()
            metadata.add_text("created_ts", str(time.time()))
            metadata.add_text("variant", variant)
            image = Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
            buffer = BytesIO()
            image.save(buffer, format="PNG", pnginfo=metadata)
            data = buffer.getvalue()
            used = sum(path.stat().st_size for path in self.directory.iterdir() if path.is_file())
            if used + len(data) > max_mb * 1024 * 1024:
                raise OSError("Notice archive is full; acknowledge saved notices to continue")
            destination = self._path(identifier)
            staging = self.directory / (identifier + ".part")
            try:
                with staging.open("xb") as output:
                    output.write(data)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(staging, destination)
                try:
                    atomic_write_json(self.directory / "pending.json",
                                      {"id": identifier, "fingerprint": fingerprint, "attempted": False})
                except Exception:
                    destination.unlink(missing_ok=True)
                    raise
            finally:
                staging.unlink(missing_ok=True)
            return identifier, False

    def mark_attempted(self, identifier):
        with self.lock:
            pending = self._pending()
            if pending.get("id") != identifier:
                raise ValueError("Pending notice changed before tap")
            # Persist BEFORE ADB, so a crash or ambiguous ADB error cannot cause
            # blind repeated clicks against the exact same unchanged image.
            pending["attempted"] = True
            atomic_write_json(self.directory / "pending.json", pending)
