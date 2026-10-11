"""Serve the v2 static export with the original templates as a fallback."""
import os
from pathlib import Path
from urllib.parse import urlencode

from flask import Blueprint, abort, redirect, render_template, request, send_from_directory

bp = Blueprint("pages", __name__)
NEXT_OUT = Path(__file__).resolve().parents[1] / "next-app" / "out"


def _has_v2():
    return os.environ.get("YIGRAPH_WEB_VERSION", "2") != "1" and (NEXT_OUT / "index.html").is_file()


def _export(path):
    if path == "api" or path.startswith(("api/", "socket.io/")):
        abort(404)
    candidate = (NEXT_OUT / path).resolve()
    if not candidate.is_relative_to(NEXT_OUT.resolve()):
        abort(404)
    for name in (path, path + ".html", path.rstrip("/") + "/index.html"):
        if (NEXT_OUT / name).is_file():
            return send_from_directory(str(NEXT_OUT), name)
    abort(404)


@bp.route("/")
def index():
    if _has_v2():
        return send_from_directory(str(NEXT_OUT), "index.html")
    return render_template("template-chatbot-s2-convo.html")


@bp.route("/overview")
def overview():
    return redirect("/") if _has_v2() else render_template("overview.html")


@bp.route("/documents")
def documents():
    return redirect("/datasets") if _has_v2() else render_template("documents.html")


@bp.route("/manage_dataset")
def manage_dataset_page():
    if _has_v2():
        params = request.args.to_dict(flat=True)
        if "kb_id" in params:
            params["dataset"] = params.pop("kb_id")
        return redirect("/files" + ("?" + urlencode(params) if params else ""))
    return render_template("manage_dataset.html")


@bp.route("/model_manager")
def model_manager_page():
    return redirect("/models") if _has_v2() else render_template("model-manager.html")


@bp.route("/<path:path>")
def frontend_export(path):
    if not _has_v2():
        abort(404)
    return _export(path)
