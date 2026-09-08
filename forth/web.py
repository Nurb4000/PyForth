"""Web front-end for PyForth.

Runs a small Flask application that exposes the interpreter over HTTP so it
can be driven from a browser.  The routes are:

``GET  /``
    Serves the terminal-style UI.
``POST /api/run``
    Accepts ``{"code": "..."}`` (a single line or several lines) and returns
    ``{"output": "...", "error": null|message}``.
``POST /api/reset``
    Discards the current interpreter for the session.
``GET  /api/health``
    Liveness check.

Each browser session gets its own :class:`forth.machine.Forth` instance, kept
in a server-side dictionary keyed by a per-user session token.

Run with::

    python -m forth.web            # http://127.0.0.1:5000
    python -m forth.web --port 8000
    FLASK_APP=forth/web.py flask run
"""

import argparse
import os
import secrets
import uuid

from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    session,
)

from .machine import Forth, ForthError


def _new_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get("PYFORTH_SECRET_KEY") or secrets.token_hex(32)
    app.config["forth_instances"] = {}
    app.config["template_folder"] = "templates"
    app.config["static_folder"] = "static"

    def forth_for_session():
        token = session.get("token")
        instances = app.config["forth_instances"]
        if token is None:
            token = uuid.uuid4().hex
            session["token"] = token
        if len(instances) > 1000:
            # Bound memory: drop the oldest session's interpreter.
            instances.pop(next(iter(instances)))
        if token not in instances:
            instances[token] = Forth()
        return instances[token]

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/run", methods=["POST"])
    def run():
        data = request.get_json(silent=True) or {}
        code = data.get("code", "")
        forth = forth_for_session()
        forth.clear_output()
        # Expose the incoming text to KEY / EXPECT as well.
        forth.feed_input(code + "\n")
        try:
            forth.run(code)
        except (ForthError, RuntimeError) as error:
            forth.abort()
            text = forth.output_text()
            forth.clear_output()
            message = str(error)
            if text:
                message = text + "\n" + message
            return jsonify({"output": "", "error": message})
        output = forth.output_text()
        return jsonify({"output": output, "error": None})

    @app.route("/api/reset", methods=["POST"])
    def reset():
        token = session.get("token")
        if token:
            app.config["forth_instances"].pop(token, None)
        session.clear()
        return jsonify({"ok": True})

    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok"})

    return app


app = _new_app()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the PyForth web server.")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to.")
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("PORT", "5000")),
        help="Port to listen on.",
    )
    parser.add_argument(
        "--debug", action="store_true", help="Enable Flask debug mode."
    )
    args = parser.parse_args(argv)
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
