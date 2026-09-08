#!/usr/bin/env python3
"""Command-line front-end for the PyForth interpreter.

Run interactively::

    python -m forth

Or execute one or more source files and then drop into the REPL::

    python -m forth examples/hello.fs

Use ``-b`` / ``--batch`` to run the file(s) and exit without opening the
interactive prompt, and ``-i`` / ``--interactive`` to always open the prompt
even when no source files are given.
"""

import select
import sys

from .machine import Forth, ForthError


PROMPT = "ok> "
CONT_PROMPT = "...> "
WELCOME = (
    "PyForth - a FORTH interpreter.  Type 'bye' to exit, "
    "'\\\"include file.fs\\\"' to load a file."
)


def _write(out, text):
    if not text.endswith("\n"):
        text += "\n"
    out.write(text)


def _interactive(infile, outfile):
    """True when input is a real terminal (so we can show a prompt)."""
    try:
        return bool(infile.isatty())
    except Exception:
        return False


def _input_pending(infile):
    """True when input lines are already waiting (e.g. a pasted block).

    The REPL uses this to avoid printing ``ok> `` between the lines of a
    multi-line paste: the prompt is only useful when the user has to type the
    next line by hand.
    """
    try:
        ready, _, _ = select.select([infile], [], [], 0.0)
        return bool(ready)
    except (OSError, ValueError, TypeError):
        return False


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
    interactive = _interactive(infile, out)
    if interactive:
        _write(out, WELCOME + "\n")
    while True:
        try:
            # While a ": ... ;" definition is open (or more pasted input is
            # already waiting) we read silently so no prompts clutter the
            # screen: only the closing ";" announces "ok".
            if interactive and not _input_pending(infile):
                line = input(CONT_PROMPT if forth.compiling else PROMPT)
            else:
                line = infile.readline()
                if line == "":
                    raise EOFError
                line = line.rstrip("\r\n")
        except EOFError:
            _write(out, "")
            break
        stripped = line.strip()
        if stripped.lower() in ("bye", "quit"):
            break
        if not stripped:
            continue
        if stripped.startswith("\"") and stripped.endswith("\""):
            path = stripped[1:-1].strip()
            _run_source(forth, path, out)
            continue
        was_compiling = forth.compiling
        # Make the typed line available to KEY / EXPECT.
        forth.feed_input(line + "\n")
        forth.clear_output()
        try:
            forth.interpret(line)
        except (ForthError, RuntimeError) as error:
            _write(out, "{}\n".format(error))
            forth.abort()
            _write(out, "ok")
            continue
        text = forth.output_text()
        forth.clear_output()
        if forth.compiling:
            # One line of a multi-line ": ... ;" definition: keep collecting
            # lines and only announce "ok" when the closing ";" is seen.
            continue
        if text:
            out.write(text)
        meaningful = stripped and not stripped.startswith("\\")
        finished_definition = was_compiling and not forth.compiling
        if meaningful or finished_definition:
            _write(out, "ok")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)

    batch = "-b" in argv or "--batch" in argv
    files = [arg for arg in argv if arg not in ("-i", "--interactive", "-b", "--batch")]

    forth = Forth()
    for path in files:
        _run_source(forth, path, sys.stdout)
    if batch:
        return 0

    repl(forth)
    return 0


if __name__ == "__main__":
    sys.exit(main())
