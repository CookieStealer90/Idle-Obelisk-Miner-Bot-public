"""Persistent, installation-specific Flask signing key."""
import json
import os
from pathlib import Path
import re
import secrets
import tempfile


def load_or_create_secret_key(path: Path) -> str:
    """Publish a complete key atomically; concurrent starts reuse the winner."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent,
                prefix=".web_secret_", suffix=".tmp", delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                json.dump({"secret_key": secrets.token_hex(32)}, temporary)
                temporary.flush()
                os.fsync(temporary.fileno())
            try:
                # Windows rename refuses to overwrite an existing destination.
                # On POSIX, use a hard link for the same atomic no-replace behavior.
                if os.name == "nt":
                    os.rename(temporary_path, path)
                else:
                    os.link(temporary_path, path)
            except FileExistsError:
                pass
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        key = data.get("secret_key") if isinstance(data, dict) else None
        if not isinstance(key, str) or re.fullmatch(r"[0-9a-f]{64}", key) is None:
            raise ValueError("invalid key format")
    except (OSError, ValueError) as exc:
        # Never silently rotate a damaged key or fall back to a shared default.
        raise RuntimeError(f"Cannot load Flask secret key from {path}") from exc
    return key
