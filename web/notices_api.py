"""Notice inbox endpoints; all requests use the application's access policy."""
from flask import Blueprint, jsonify, send_file
from io import BytesIO

from config import settings as s
from core.notice_archive import NoticeArchive

notices_bp = Blueprint("notices_api", __name__)
# Share one archive lock between the worker and API without importing workers.
archive = NoticeArchive(s.TEMP_DIR / "notices")


@notices_bp.get("/api/notices")
def list_notices():
    try:
        entries = archive.entries()
        return jsonify({"entries": entries, "unreadable": archive.unreadable_count})
    except (OSError, ValueError, KeyError) as exc:
        return jsonify({"error": f"Cannot read notice archive: {exc}"}), 503


@notices_bp.get("/api/notices/<identifier>/image")
def notice_image(identifier):
    try:
        return send_file(BytesIO(archive.read(identifier)), mimetype="image/png", max_age=0)
    except ValueError:
        return jsonify({"error": "Invalid notice ID"}), 400
    except FileNotFoundError:
        return jsonify({"error": "Notice no longer exists"}), 404
    except OSError:
        return jsonify({"error": "Cannot read notice image"}), 503


@notices_bp.delete("/api/notices/<identifier>")
def delete_notice(identifier):
    try:
        archive.delete(identifier)
        return jsonify({"ok": True})
    except ValueError:
        return jsonify({"error": "Invalid notice ID"}), 400
    except OSError:
        return jsonify({"error": "Cannot delete notice image"}), 503


@notices_bp.post("/api/notices/test")
def test_detection():
    # Cache first, then an isolated fresh capture; never dismiss or archive.
    from core.screen_cache import get_cached_screen, get_screen
    from core.notice_detection import detect_notice
    try:
        image, _, _ = get_cached_screen("game_scr", max_age=s.NOTICES_SCREEN_REUSE_AGE_S, color=True)
        if image is None:
            image, _, _ = get_screen("notices_test_scr", max_age=0, force=True, color=True)
        if image is None:
            return jsonify({"error": "Notice test screenshot capture failed; see screenshot log"}), 503
        return jsonify(detect_notice(image, s.NOTICES_DETECT_ROI, s.BASE_DIR / "images",
                                     s.NOTICES_TEMPLATE_GLOB, s.NOTICES_MATCH_THRESHOLD))
    except (OSError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 503
