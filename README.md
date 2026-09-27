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

Options:

```
python -m forth [-b] [-i] [--max-steps N] [file.fs ...]
```

- `-b`, `--batch` — run the files and exit instead of opening the REPL.
- `-i`, `--interactive` — always open the REPL, even with no files given.
- `--max-steps N` — stop a line after N executed words (`0` = no limit,
  default 10,000,000). Useful when a program loops forever.
- `-h`, `--help` — usage summary.

At the prompt, type FORTH code and press Enter. Type `bye` (or `quit`) to
exit, or `"path/to/file.fs"` to load and run a file (the quotes are part of the
syntax). The special word `?` reads and runs a line from standard input.
Pressing Ctrl-C aborts the current line — including a runaway loop — and drops
back to the prompt with the dictionary intact.

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
from forth.machine import Forth, ForthError

forth = Forth()
forth.run(
    ": SQUARE DUP * ;\n"
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
    print("error:", err)     # ForthError is a RuntimeError subclass
forth.abort()                # discard stacks/control state, keep definitions

# Bound the work a single run may do (None = no limit):
forth.max_steps = 1_000_000
```

`forth.max_steps` counts executed words and raises `ForthError` when the cap is
passed, so a runaway loop reports an error instead of hanging. Both front-ends
set it (`--max-steps` on the command line, 10 million per request in the browser).

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
- **Comparison**: `=` `<>` `<` `>` `<=` `>=` `0=` `0<` `0>` `1<` `2>`
  `WITHIN` and family. Relational words use the standard stack order, so
  `3 5 <` is false (it asks "is 5 below 3?") and `3 5 >` is true.
- **Bitwise**: `AND` `OR` `XOR` `NOT` `LSHIFT` `RSHIFT` `?LSHIFT` `?RSHIFT`.
- **Memory**: `@` `!` `+!` `@+` `@-` `C@` `C!` `CHAIN` `SP@` `SP!` `RS@`.
- **Control**: `IF`/`ELSE`/`THEN`, `DO`/`+LOOP`/`?DO`/`LOOP`/`UNDO`,
  `BEGIN`/`WHILE`/`REPEAT`/`UNTIL`/`AGAIN`, `CASE`/`OF`/`ENDOF`/`ENDCASE`,
  `LEAVE`, `'` (tick, for `EXECUTE`), and recursion by direct self-reference.
- **Definitions**: `:` `;` `VARIABLE` `CONSTANT` `CREATE` `ALLOT` `DOES>`
  `IMMEDIATE` `ALIAS` `STRUCT` `FIELD` `ENDSTRUCT` `ARRAYS`. The size comes
  *before* the word, and a struct's first field shares the struct's own address:
  ```
  3 STRUCT POINT  FIELD X  FIELD Y  FIELD Z  ENDSTRUCT
  11 X !  22 Y !  33 Z !   X @ . Y @ . Z @ .   \ prints  11  22  33
  6 ARRAYS SQUARES           \ six zeroed cells, SQUARES pushes the address
  7 SQUARES 2 + !            \ stores into the third element
  ```
- **Strings**: `S" ..."` `." ..."` `CHAR` `COUNT` `TYPE` `LEN` `STR@` `STR!`
  `STRING=` `STRING<` `STRING>` `WORD` `SOURCE`.
- **I/O**: `EMIT` `.` `?.` `.S` `SPACE` `SPACES` `CR` `PAGE` `KEY` `EXPECT`
  `ACCEPT` `READLINE` `ABORT` `ABORT"`.
- **Bases**: `HEX` `DECIMAL` `OCTAL` `BINARY` `16#` `8#` `2#`
  `BASE` `BASE@` `BASE!` (which rejects anything outside 2 .. 36).
- **Pictured numeric output**: `<#` `HOLD` `#` `#S` `SIGN` `#>`, which build a
  counted string in `PAD`:
  ```
  : UD.  <# #S #> TYPE ;
  1234 UD.            \ prints 1234
  -45 UD.             \ prints -45
  HEX 1F UD.          \ prints 1F
  <# 65 HOLD 66 HOLD #> COUNT TYPE   \ prints BA (first held char ends up right)
  ```
  `<#` is optional in PyForth, so `1234 #S #>` also works. `#` converts a
  single digit and takes the low cell from the top of the stack, so put the
  high half underneath: `<# 0 12345 # # # # # #> COUNT TYPE`.
- **System**: `TIB` `SPAN` `SPAN@` `SPAN!` `>IN` `>IN@` `>IN!` `BLK` `BLK@`
  `BLK!` `STATE` `SOURCE` `WORD` `WORDS` `INCLUDE`.

`BASE`, `>IN`, `SPAN`, `BLK` push the current *value* of the system variable;
the `@`/`!` variants read and write the raw cell (e.g. `16 BASE!` selects hex).
Note that `S" ..."` leaves a counted string, so use `S" hi" COUNT TYPE` (or
`S." "` / `S.`) rather than `S" hi" TYPE`.

This is not an exhaustive ANSI-FORTH implementation, but it covers the core plus
the extensions most useful for examples and scripting.

### Deviations worth knowing

- **`DO` takes `( start limit -- )`**, i.e. the start is pushed first, which is
  the opposite of the ANSI `( limit start -- )`. This is PyForth's long-standing
  convention and the examples rely on it. Plain `LOOP` therefore always counts
  *towards* the limit: `1 10 DO ... LOOP` runs 1 .. 9, and `10 1 DO ... LOOP`
  counts 10 down to 2 instead of doing nothing.
- **`+LOOP` with a runtime increment** (`n +LOOP`) reads its increment from the
  data stack at the end of every pass, so the body has to leave a value behind
  each time: `0 10 DO I . 1 +LOOP` counts 0 .. 9. A constant step written
  literally in front of `+LOOP` (`2 +LOOP`) is compiled in, as usual.
- **Numbers are converted when the line is read**, so changing the base halfway
  through a line does not affect the numbers already on it. Use a separate line
  (or a word) after `HEX` / `DECIMAL`.
- **`>NUMBER` uses `( #in #out a# -- #in' #out' a# )`** — the order of the
  original implementation rather than the ANS `( ud a# u -- )`. It converts the
  whole leading run of valid digits in the current base.
- **`DOES>` only works at the top level**: `CREATE NAME ... DOES> ... ;`. Inside
  a colon definition it reports a clear error instead of building a broken
  defining word.
- **`CREATE` names the cell at `HERE`** and does not reserve it, so a following
  `,` or `ALLOT` fills it: `CREATE A 42 , A @ .` prints 42.
- **`ALLOT` reserves cells, not bytes**, so reserve generously.
- Single-cell machine: there is no double-cell arithmetic, so `#` / `#S` convert
  single cells and `FM/`-style words return quotient and remainder.
- **`WORD` re-reads the parse area** (`SOURCE` buffer) rather than the token
  stream, so put the delimiter on the stack *before* `WORD` and remember that
  the text it consumed is still interpreted normally afterwards:
  ```
  32 WORD my-token COUNT TYPE   \ print the next space-delimited token
  ```
- **`:NONAME` is not implemented**; compile-time words such as `POSTPONE`,
  `[']` and `LITERAL` only work inside a colon definition, as intended.

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

It covers arithmetic, stack words, comparison order, bases, control structures
(including `LEAVE`, `CASE` and control-flow state cleanup after errors),
strings, pictured output, `CREATE`/`DOES>`, I/O, error handling, and both
front-ends.

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
Web interface screenshot:
<img width="967" height="934" alt="image" src="https://github.com/user-attachments/assets/d6792072-6e81-4dd9-872a-9418de815a84" />
