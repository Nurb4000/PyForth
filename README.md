# PyForth

A FORTH interpreter written in Python, with both a command-line front-end and
a web front-end. It aims for a reasonably complete ANSI-FORTH-style core plus a
set of practical extensions (strings, arrays, structured control flow, and
extended and floating-point math).

## Features

- ~200 primary words covering the ANS FORTH core word set plus extensions.
- Full compilation of secondary definitions (`: ... ;`) that may span multiple
  lines, with `IMMEDIATE`, `DO`/`+LOOP`/`?DO`, `IF`/`ELSE`/`THEN`,
  `BEGIN`/`WHILE`/`REPEAT`/`UNTIL`/`AGAIN`, `CASE`/`OF`/`ENDOF`/`ENDCASE`,
  `LEAVE`, `CREATE`/`DOES>`, `VARIABLE`/`CONSTANT`, `STRUCT`/`FIELD`, and more.
- Strings (`S" ..."`, `CHAR`, `COUNT`, `TYPE`, `LEN`, `STR@`/`STR!`,
  `STRING=`/`STRING<`/`STRING>`), counted strings, and `\` line comments.
- Arrays (`ARRAYS`), bases (`HEX`/`DECIMAL`/`OCTAL`/`BINARY`, `16#`, `2#`),
  and extended math (`SQRT`, `POW`, `**`, `LN`, `LOG`, `EXP`, trig, `CEIL`,
  `FLOOR`, `TRUNC`, `FRAC`). The math words operate on integer cells and
  return integer results (fractional parts are truncated).
- Command-line REPL and source-file execution.
- Flask web server with a terminal-style browser UI.

## Requirements

- Python 3.8+
- Flask — only needed for the web front-end (`pip install flask`)

The command-line front-end and the interpreter core have no third-party
dependencies.

## Quick start

### Command line

Interactive REPL:

```
python -m forth
```

Run a source file and drop into the REPL:

```
python -m forth examples/fizzbuzz.fs
```

Run a file in batch mode (no REPL, exits when done):

```
python -m forth -b examples/hello.fs
```

At the prompt, type FORTH code and press Enter. Type `bye` (or `quit`) to
exit, or `"path/to/file.fs"` to load and run a file. The special word `?`
reads and runs a line from standard input.

A `: ... ;` definition may span several lines: continuation lines are
collected silently and a single `ok` is printed when the closing `;` is seen.
When input is piped (not an interactive terminal), no prompts are printed and
only the results plus `ok` markers appear.

### Web front-end

Start the Flask server:

```
python -m forth.web --port 8000
# or
FLASK_APP=forth/web.py flask run
```

Then open <http://127.0.0.1:8000/>. The page is a terminal-style UI where you
can type or paste FORTH code and run it; each browser session gets its own
interpreter instance. Use the **clear** button to wipe the screen and
**reset** to start a fresh interpreter.

API endpoints (used by the UI):

- `GET  /` — the UI page.
- `POST /api/run` — body `{"code": "..."}`; returns
  `{"output": "...", "error": null|"message"}`.
- `POST /api/reset` — discards the current session's interpreter.
- `GET  /api/health` — liveness check.

## Python API

```python
from forth import Forth

forth = Forth()
forth.run(
    ": SQUARE 2 ** ;\n"
    "1 10 DO I SQUARE . LOOP",
)
print(forth.output_text())   # -> ' 1  4  9  16  25  36  49  64  81 '
forth.clear_output()

# Interpret a single line (useful for REPLs):
forth.interpret("5 3 + .")
print(forth.output_text())   # -> ' 8 '

# Recover from an error and keep going:
try:
    forth.interpret(". ")    # empty stack -> underflow
except ForthError as err:
    print("error:", err)
forth.abort()                # discard stacks/control state, keep definitions
```

Key methods on `Forth`:

- `interpret(line)` — interpret a single line.
- `run(text)` — run possibly multi-line source (definitions and top-level
  statements); control structures may span lines.
- `output_text()` / `clear_output()` — read/clear captured output.
- `feed_input(text)` — feed text available to `KEY`/`EXPECT`.
- `abort()` — reset stacks and control-flow state after an error while
  preserving the dictionary.
- `find(name)`, `register(name, primary)`, `set_immediate(name)` — introspection
  and extension hooks.

## Word reference

Run `.S` or `DEPTH` interactively to inspect the stack, and use the built-in
words to explore. Categories include:

- **Stack**: `DUP` `DROP` `SWAP` `ROT` `-ROT` `OVER` `TUCK` `NIP` `PICK`
  `2DUP` `2SWAP` `2OVER` `2DROP` `3DUP` `DEPTH` `CLEAR` and the numeric
  `n.PICK` / `n.ROT` families.
- **Arithmetic**: `+` `-` `*` `/` `MOD` `NEGATE` `ABS` `1+` `1-` `2*` `2/`
  `FM/` `UM/M` `UM/DP` `/+` `-/` `SQRT` `POW` `**` `EXP` `LN` `LOG` `SIN` `COS`
  `TAN` `ATAN` `AT2` `CEIL` `FLOOR` `TRUNC` `FRAC`.
- **Comparison**: `=` `<>` `<` `>` `<=` `>=` `0=` `0<` `0>` `1<` `2>` and family.
- **Bitwise**: `AND` `OR` `XOR` `NOT` `LSHIFT` `RSHIFT` `?LSHIFT` `?RSHIFT`.
- **Memory**: `@` `!` `+!` `@+` `@-` `C@` `C!` `CHAIN` `SP@` `SP!` `RS@`.
- **Control**: `IF`/`ELSE`/`THEN`, `DO`/`+LOOP`/`?DO`/`LOOP`/`UNDO`,
  `BEGIN`/`WHILE`/`REPEAT`/`UNTIL`/`AGAIN`, `CASE`/`OF`/`ENDOF`/`ENDCASE`,
  `LEAVE`, and recursion by direct self-reference.
- **Definitions**: `:` `;` `VARIABLE` `CONSTANT` `CREATE` `ALLOT` `DOES>`
  `IMMEDIATE` `ALIAS` `STRUCT` `FIELD` `ENDSTRUCT` `ARRAYS`.
- **Strings**: `S" ..."` `." ..."` `CHAR` `COUNT` `TYPE` `LEN` `STR@` `STR!`
  `STRING=` `STRING<` `STRING>` `WORD` `SOURCE`.
- **I/O**: `EMIT` `.` `?.` `.S` `SPACE` `SPACES` `CR` `PAGE` `KEY` `EXPECT`
  `ACCEPT` `READLINE` `ABORT` `ABORT"`.
- **Bases**: `HEX` `DECIMAL` `OCTAL` `BINARY` `16#` `8#` `2#`
  `#` `#S` `#>` `>NUMBER` `NUMBER?` `BASE`.

This is not an exhaustive ANSI-FORTH implementation, but it covers the core plus
the extensions most useful for examples and scripting.

## Examples

The `examples/` directory contains runnable programs:

- `hello.fs` — Hello World.
- `factorial.fs` — iterative factorial with `DO`/`LOOP`.
- `fibonacci.fs` — recursive Fibonacci.
- `fizzbuzz.fs` — FizzBuzz using strings and conditionals.
- `strings.fs` — string comparison and formatting.
- `arrays.fs` — declaring and indexing arrays.
- `temperature.fs` — Fahrenheit-to-Celsius converter.

Run any of them with `python -m forth -b examples/<name>.fs`.

## Tests

The test suite uses only the standard library:

```
python -m unittest discover -s tests
# or
python tests/test_forth.py
```

It covers arithmetic, stack words, bases, control structures, strings, arrays,
I/O, error handling, and both front-ends.

## Project layout

```
forth/            interpreter package
  machine.py      core: stacks, memory, tokenizer, compiler, interpreter
  words.py        primary word catalogue
  cli.py          command-line front-end (REPL + file execution)
  web.py          Flask web front-end
  templates/      terminal UI page
  static/         UI CSS/JS
examples/         runnable .fs programs
tests/            unittest suite
```
