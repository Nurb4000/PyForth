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

from .machine import Forth


#: Per-request execution cap, so a runaway loop cannot pin a worker.
MAX_STEPS = 10_000_000
#: Largest accepted source text, to keep one request from eating all memory.
MAX_CODE_BYTES = 64 * 1024


def _new_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.secret_key = os.environ.get("PYFORTH_SECRET_KEY") or secrets.token_hex(32)
    app.config["forth_instances"] = {}

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
            forth = Forth()
            forth.max_steps = MAX_STEPS
            instances[token] = forth
        return instances[token]

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/run", methods=["POST"])
    def run():
        data = request.get_json(silent=True) or {}
        code = data.get("code", "")
        if not isinstance(code, str):
            return jsonify({"output": "",
                            "error": "code must be a string"}), 400
        if len(code.encode("utf-8", "replace")) > MAX_CODE_BYTES:
            return jsonify({
                "output": "",
                "error": "source text is larger than {} bytes".format(
                    MAX_CODE_BYTES),
            }), 413
        forth = forth_for_session()
        forth.clear_output()
        # Expose the incoming text to KEY / EXPECT as well.
        forth.feed_input(code + "\n")
        try:
            forth.run(code)
        except Exception as error:
            forth.abort()
            text = forth.output_text()
            forth.clear_output()
            # The output produced before the error is still worth showing, so
            # it travels in "output" and the JS prints both in order.
            return jsonify({"output": text, "error": str(error)})
        finally:
            # KEY / EXPECT input is scoped to one request: drop whatever the
            # run did not consume so it cannot bleed into the next request.
            # (Pass the text a program should read in the same request.)
            forth.reset_input()
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
