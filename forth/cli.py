#!/usr/bin/env python3
"""Command-line front-end for the PyForth interpreter.

Run interactively::

    python -m forth.cli

Or execute one or more source files and then drop into the REPL::

    python -m forth.cli examples/hello.fs

Use ``-b`` / ``--batch`` to run the file(s) and exit without opening the
interactive prompt, and ``-i`` / ``--interactive`` to always open the prompt
even when no source files are given.
"""

import sys

from .machine import Forth, ForthError


PROMPT = "ok> "
WELCOME = (
    "PyForth - a FORTH interpreter.  Type 'bye' to exit, "
    "'\\\"include file.fs\\\"' to load a file."
)


def _write(out, text):
    if not text.endswith("\n"):
        text += "\n"
    out.write(text)


def _run_source(forth, path, out):
    try:
        with open(path, "r") as handle:
            source = handle.read()
    except OSError as error:
        _write(out, "cannot open {}: {}\n".format(path, error))
        return False
    forth.clear_output()
    try:
        forth.run(source)
    except (ForthError, RuntimeError) as error:
        _write(out, "{}\n".format(error))
        forth.abort()
        _write(out, " ok\n")
        return False
    text = forth.output_text()
    forth.clear_output()
    if text:
        out.write(text)
    _write(out, " ok\n")
    return True


def repl(forth, infile=None, outfile=None):
    out = outfile or sys.stdout
    infile = infile or sys.stdin
    _write(out, WELCOME + "\n")
    while True:
        try:
            line = input(PROMPT)
        except EOFError:
            _write(out, "")
            break
        stripped = line.strip()
        if stripped.lower() in ("bye", "quit"):
            break
        if stripped.startswith("\"") and stripped.endswith("\""):
            path = stripped[1:-1].strip()
            _run_source(forth, path, out)
            continue
        # Make the typed line available to KEY / EXPECT.
        forth.feed_input(line + "\n")
        forth.clear_output()
        try:
            forth.interpret(line)
        except (ForthError, RuntimeError) as error:
            _write(out, "{}\n".format(error))
            forth.abort()
            _write(out, " ok\n")
            continue
        text = forth.output_text()
        forth.clear_output()
        if text:
            out.write(text)
        _write(out, " ok\n")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)

    interactive = "-i" in argv or "--interactive" in argv
    batch = "-b" in argv or "--batch" in argv
    files = [arg for arg in argv if arg not in ("-i", "--interactive", "-b", "--batch")]

    forth = Forth()
    for path in files:
        _run_source(forth, path, sys.stdout)
        if batch:
            return 0

    if not batch:
        repl(forth)
    return 0


if __name__ == "__main__":
    sys.exit(main())
