#!/usr/bin/env python3
"""Command-line front-end for the PyForth interpreter.

Run interactively::

    python -m forth

Or execute one or more source files and then drop into the REPL::

    python -m forth examples/hello.fs

Use ``-b`` / ``--batch`` to run the file(s) and exit without opening the
interactive prompt, and ``-i`` / ``--interactive`` to always open the prompt
even when no source files are given.

``--max-steps N`` caps how many words a single line (or file) may execute, so a
runaway loop reports an error instead of hanging; 0 switches the cap off.
"""

import select
import sys

from .machine import Forth


PROMPT = "ok> "
CONT_PROMPT = "...> "
WELCOME = (
    "PyForth - a FORTH interpreter.  Type 'bye' to exit, "
    "or type \"include file.fs\" (with the quotes) to load a file."
)
DEFAULT_MAX_STEPS = 10_000_000


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
    except KeyboardInterrupt:
        _write(out, "^C\n")
        forth.abort()
        _write(out, " ok\n")
        return False
    except Exception as error:
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
        except KeyboardInterrupt:
            _write(out, "^C")
            continue
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
        except KeyboardInterrupt:
            # Ctrl-C during a runaway loop: drop the partial work and keep going
            _write(out, "^C")
            forth.abort()
            continue
        except Exception as error:
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


def parse_args(argv):
    """Split ``argv`` into (options, files).

    ``--max-steps`` takes its value either as the next argument or after an
    ``=``; a value of 0 means "no limit".
    """
    options = {"batch": False, "interactive": False,
               "max_steps": DEFAULT_MAX_STEPS}
    files = []
    rest = list(argv)
    while rest:
        arg = rest.pop(0)
        if arg in ("-b", "--batch"):
            options["batch"] = True
        elif arg in ("-i", "--interactive"):
            options["interactive"] = True
        elif arg == "--max-steps" or arg.startswith("--max-steps="):
            if arg.startswith("--max-steps="):
                value = arg.split("=", 1)[1]
            elif rest:
                value = rest.pop(0)
            else:
                raise ValueError("--max-steps needs a value")
            try:
                options["max_steps"] = int(value)
            except ValueError:
                raise ValueError("--max-steps needs a number, not "
                                 "{!r}".format(value))
        elif arg in ("-h", "--help"):
            options["help"] = True
        else:
            files.append(arg)
    return options, files


USAGE = """usage: python -m forth [-b] [-i] [--max-steps N] [file.fs ...]

  -b, --batch        run the files and exit instead of opening the REPL
  -i, --interactive  always open the REPL
  --max-steps N      stop a line after N words (0 = no limit, default {0})
  -h, --help         show this message
""".format(DEFAULT_MAX_STEPS)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        options, files = parse_args(argv)
    except ValueError as error:
        sys.stderr.write("python -m forth: {}\n".format(error))
        sys.stderr.write(USAGE)
        return 2
    if options.get("help"):
        sys.stdout.write(USAGE)
        return 0

    forth = Forth()
    forth.max_steps = options["max_steps"] or None
    failed = False
    for path in files:
        if not _run_source(forth, path, sys.stdout):
            failed = True
    if options["batch"]:
        return 1 if failed else 0

    repl(forth)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
