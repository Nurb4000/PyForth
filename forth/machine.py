"""Core FORTH machine: stacks, memory, dictionary, tokenizer, compiler and
the outer/inner interpreter loop.

The implementation uses a threaded (index based) execution model for
secondary definitions.  Control structures are compiled at definition time
with back-patching, which keeps the runtime loop simple and correct.
"""

from __future__ import annotations

import string


CELL_BITS = 64
CELL_MASK = (1 << CELL_BITS) - 1
SIGN_BIT = 1 << (CELL_BITS - 1)


def to_cell(n):
    """Coerce an arbitrary integer into a signed ``CELL_BITS`` value."""
    n &= CELL_MASK
    if n & SIGN_BIT:
        n -= (1 << CELL_BITS)
    return n


class ForthError(Exception):
    """Raised to abort the current computation and return to the top level."""


# ---------------------------------------------------------------------------
# Stacks
# ---------------------------------------------------------------------------

class Stack:
    """A data/return stack with high/low water-mark tracking so that
    overflow and underflow can be reported like a real machine."""

    def __init__(self, name, size, growing_down=True):
        self.name = name
        self.size = size
        self.growing_down = growing_down
        self.data = []          # list of cells

    def push(self, value):
        value = to_cell(value)
        if len(self.data) >= self.size:
            raise ForthError(f"{self.name} stack overflow")
        self.data.append(value)

    def pop(self):
        if not self.data:
            raise ForthError(f"{self.name} stack underflow")
        return self.data.pop()

    def peek(self, n=0):
        idx = len(self.data) - 1 - n
        if idx < 0 or idx >= len(self.data):
            raise ForthError(f"{self.name} stack underflow")
        return self.data[idx]

    def depth(self):
        return len(self.data)

    def reset(self):
        self.data = []


class DataStack(Stack):
    pass


class ReturnStack(Stack):
    pass


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

class Memory:
    """A sparse integer-addressed memory shared by cell values and char
    strings.  ``@`` / ``!`` operate on cells, ``C@`` / ``C!`` on single
    bytes (values 0-255)."""

    def __init__(self):
        self.cells = {}
        self.next_cell_addr = 0x4000
        self.next_str_addr = 0x8000

    def cget(self, addr):
        return self.cells.get(addr, 0) & 0xFF

    def cset(self, addr, value):
        self.cells[addr] = value & 0xFF

    def cell_get(self, addr):
        return to_cell(self.cells.get(addr, 0))

    def cell_set(self, addr, value):
        self.cells[addr] = to_cell(value)

    def alloc_cell(self):
        a = self.next_cell_addr
        self.next_cell_addr += 1
        return a

    def alloc_string(self, n=1):
        a = self.next_str_addr
        self.next_str_addr += n
        return a


# ---------------------------------------------------------------------------
# Dictionary entry
# ---------------------------------------------------------------------------

class DictEntry:
    __slots__ = ("name", "body", "immediate", "primary")

    def __init__(self, name):
        self.name = name
        self.body = None            # list of cells for secondary words
        self.immediate = False
        self.primary = None         # Primary handler for core words


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

class Tok:
    __slots__ = ("kind", "value")

    def __init__(self, kind, value):
        self.kind = kind        # 'word' | 'num' | 'str' | 'paren'
        self.value = value

    def __repr__(self):
        return f"Tok({self.kind!r}, {self.value!r})"


_BASE_CHARS = list(string.digits + string.ascii_uppercase)


class Tokenizer:
    """Turn a line of FORTH source into tokens.

    Understands balanced ``(...)`` comments, ``"..."`` string literals and
    numeric literals in the current base (including ``16#`` / ``2#`` prefixes,
    ``0x`` suffixes and ``_`` digit separators).
    """

    def __init__(self, machine):
        self.m = machine

    def tokenize(self, line):
        toks = []
        i, n = 0, len(line)
        while i < n:
            c = line[i]
            if c in " \t\r\n":
                i += 1
                continue
            if c == "\\":
                # Backslash runs to the end of the line is a FORTH comment.
                break
            if c == "(":
                depth = 1
                i += 1
                while i < n and depth:
                    if line[i] == "(":
                        depth += 1
                    elif line[i] == ")":
                        depth -= 1
                    i += 1
                toks.append(Tok("paren", None))
                continue
            if c == "S" and i + 1 < n and line[i + 1] == '"':
                i += 2  # skip opening S"
                content, i = self._read_string(line, i, n)
                toks.append(Tok("str", content))
                continue
            if c == '"':
                i += 1  # skip opening quote
                content, i = self._read_string(line, i, n)
                toks.append(Tok("str", content))
                continue
            # Read a maximal run of non-separator characters as one token.
            start = i
            while i < n and line[i] not in " \t\r\n\";(":
                i += 1
            word = line[start:i]
            if word == "":
                # A lone separator character (e.g. ';') must still advance.
                toks.append(self._classify(line[i]))
                i += 1
            else:
                toks.append(self._classify(word))
        return toks

    def _read_string(self, line, i, n):
        """Read a double-quoted string starting at ``i``.

        Returns ``(content, new_index)`` where ``new_index`` points just past
        the closing quote.  A backslash escapes the following character so that
        ``S" he said \\"hi\\"\"`` yields ``he said "hi"``.
        """
        buf = []
        while i < n and line[i] != '"':
            ch = line[i]
            if ch == "\\" and i + 1 < n:
                buf.append(line[i + 1])
                i += 2
            else:
                buf.append(ch)
                i += 1
        i += 1  # skip closing quote
        return "".join(buf), i

    def _classify(self, word):
        up = word.upper()
        val = self._parse(up)
        if val is not None:
            return Tok("num", val)
        return Tok("word", word)

    def _parse(self, up):
        try:
            if "#" in up:
                prefix, _, rest = up.partition("#")
                base = int(prefix, 10)
                v = self._from_base(rest.replace("_", ""), base)
                return to_cell(v) if v is not None else None
            neg = False
            s = up
            if s.startswith("-"):
                neg, s = True, s[1:]
            elif s.startswith("+"):
                neg, s = False, s[1:]
            if s == "":
                return None
            if s[:2].upper() == "0X":
                v = self._from_base(s[2:].replace("_", ""), 16)
            else:
                base = self.m.mem.cell_get(self.m.uv["BASE"])
                v = self._from_base(s.replace("_", ""), base)
            if v is None:
                return None
            return to_cell(-v if neg else v)
        except Exception:
            return None

    @staticmethod
    def _from_base(s, base):
        if not s:
            return 0
        result = 0
        for ch in s:
            if ch not in _BASE_CHARS:
                return None
            d = _BASE_CHARS.index(ch)
            if d >= base:
                return None
            result = result * base + d
        return result


# ---------------------------------------------------------------------------
# Primary (built-in) words
# ---------------------------------------------------------------------------

class Primary:
    """A built-in word.  ``execute`` runs it in interpret mode; ``compile``
    (optional) runs it while compiling a secondary definition."""

    def __init__(self, execute=None, compile=None, compile_only=False,
                 is_control=False, defining=False):
        self.execute = execute
        self.compile = compile
        self.compile_only = compile_only
        self.is_control = is_control
        self.defining = defining

    def __repr__(self):
        return f"<Prim {'co' if self.compile_only else ''}>"


# ---------------------------------------------------------------------------
# Compiler scratch state
# ---------------------------------------------------------------------------

class _CompileState:
    def __init__(self):
        self.interpret_mode = False     # set by ] : execute next word now
        self.numbuf = []                # numbers seen while compiling, pending use
        self.advance_by = 0             # tokens consumed by a compile action
        self.plusloop_const = None      # constant step for "N +LOOP"

    def reset(self):
        self.interpret_mode = False
        self.numbuf = []
        self.advance_by = 0
        self.plusloop_const = None


# ---------------------------------------------------------------------------
# The machine
# ---------------------------------------------------------------------------

class Forth:
    def __init__(self):
        self.ds = DataStack("data", 8192, growing_down=False)
        self.rs = ReturnStack("return", 8192, growing_down=True)
        self.mem = Memory()
        self.dict = {}            # name -> DictEntry
        self.uv = {}              # user variable name -> address (stored in mem)
        self.user = {"BASE": 10, ">IN": 0, "BLK": 0, "SPAN": 0}
        self.loops = []           # DO/LOOP index stack for I/J/K: [i, nlim]
        self.while_stack = []     # flags for BEGIN/WHILE/THEN loops
        self.begin_stack = []     # indices of open BEGINs
        self.struct_stack = []    # stack of 'if'/'begin' markers for THEN
        self.compiling = False
        self.current = None
        self.last_word = None     # most recently defined word (for IMMEDIATE)
        self._pending_does = None # word being finished by a DOES> 
        self.compile_state = _CompileState()
        self.output = []          # captured output buffer
        self.ip = 0               # instruction pointer during body execution
        # input buffering for KEY / EXPECT
        self.input_buffer = ""
        self.input_index = 0
        self._setup_user_vars()
        self._register_core()

    def _setup_user_vars(self):
        # cell-sized user variables
        for name in (">IN", "BLK", "SPAN", "BASE"):
            self.uv[name] = self.mem.alloc_cell()
            self.mem.cell_set(self.uv[name], self.user[name])
        # char-buffer sized regions
        self.uv["TIB"] = self.mem.alloc_string(256)
        self.uv["PAD"] = self.mem.alloc_string(256)
        self.uv["KEYBUF"] = self.mem.alloc_string(256)
        self.mem.cell_set(self.uv["BASE"], 10)

    def feed_input(self, text):
        """Feed raw characters for KEY / EXPECT to consume."""
        self.input_buffer += text

    def reset_input(self):
        self.input_buffer = ""
        self.input_index = 0

    def get_key(self):
        if self.input_index < len(self.input_buffer):
            ch = self.input_buffer[self.input_index]
            self.input_index += 1
            return ord(ch)
        return -1

    def key_available(self):
        return self.input_index < len(self.input_buffer)

    # -- output helpers ----------------------------------------------------

    def emit(self, s=""):
        self.output.append(str(s))

    def emit_char(self, c):
        self.output.append(c)

    def clear_output(self):
        self.output = []

    def output_text(self):
        return "".join(self.output)

    # -- dictionary --------------------------------------------------------

    def find(self, name):
        return self.dict.get(name.upper())

    def new_secondary(self, name):
        e = DictEntry(name)
        self.dict[name.upper()] = e
        return e

    # -- core word registration --------------------------------------------

    def _register_core(self):
        from .words import register_words
        register_words(self)

    def register(self, name, primary):
        e = self.find(name)
        if e is None:
            e = DictEntry(name)
            self.dict[name.upper()] = e
        e.primary = primary
        e.body = None

    def set_immediate(self, name):
        e = self.find(name)
        if e is None:
            raise ForthError(f"{name} not defined")
        e.immediate = True

    # -- tokenizer ---------------------------------------------------------

    def tokenize(self, line):
        return Tokenizer(self).tokenize(line)

    def try_number(self, raw):
        """Attempt to parse ``raw`` as a number using the *current* base.

        Used as a runtime fallback for tokens that were classified as words at
        tokenize time (e.g. ``1F`` while BASE was still decimal) but are valid
        literals under a base changed later in the same line.
        """
        return Tokenizer(self)._parse(raw.upper())

    # -- compilation -------------------------------------------------------

    def start_compile(self, name):
        if self.compiling:
            raise ForthError("nested ':' definition")
        e = self.new_secondary(name)
        e.body = []
        self.current = e
        self.last_word = e
        self.compiling = True
        self.compile_state.reset()

    def end_compile(self):
        if not self.compiling:
            raise ForthError("; without :")
        # A DOES> temporary definition is being closed here.
        if self._pending_does is not None:
            word = self._pending_does
            temp = self.current
            self.current.body.append(["exit", 0, -1])
            self.compiling = False
            self.current = None
            self.compile_state.reset()
            word.body = [word.body[0]] + temp.body
            self.last_word = word
            self._pending_does = None
            return
        self.current.body.append(["exit", 0, -1])
        self.compiling = False
        self.current = None
        self.compile_state.reset()

    def emit_cell(self, tag, payload=0):
        idx = len(self.current.body)
        self.current.body.append([tag, payload, idx])
        return idx

    def emit_prim(self, name):
        return self.emit_cell("prim", name)

    def set_branch(self, idx, val):
        self.current.body[idx][1] = val

    @property
    def body(self):
        return self.current.body

    # -- top-level interpret / run -----------------------------------------

    def interpret(self, line):
        """Interpret a single line in interpret mode."""
        toks = self.tokenize(line)
        self._process(toks)

    def run(self, text):
        """Run possibly multi-line FORTH source.

        All lines are tokenized and fed to a single :meth:`_process` call so
        that control structures such as ``DO ... LOOP`` may span line
        boundaries.  Definitions that span several lines also work because the
        compilation state persists across the tokens.
        """
        all_toks = []
        for line in text.splitlines():
            all_toks.extend(self.tokenize(line))
        self._process(all_toks)

    def abort(self):
        """Discard all stack and control-flow state after an error while
        preserving the dictionary (definitions, variables, ...)."""
        self.ds.reset()
        self.rs.reset()
        self.loops.clear()
        self.while_stack.clear()
        self.begin_stack.clear()
        self.struct_stack.clear()
        self.compiling = False
        self.current = None
        self._pending_does = None
        self.compile_state.reset()

    def _process(self, toks):
        """Convert tokens to cells and either compile them into the current
        definition (compile mode) or execute them (interpret mode)."""
        cs = self.compile_state
        n = len(toks)
        i = 0
        temp = []                 # cells for the current interpret-mode context
        while i < n:
            t = toks[i]
            i += 1
            k = t.kind

            if k == "paren":
                continue
            if k == "num":
                cs.numbuf.append(t.value)
                continue
            if k == "str":
                cs.numbuf.append(self._make_static_string(t.value))
                continue

            name = t.value.upper()

            if name == ";":
                if self.compiling:
                    self._flush(self.current.body)
                    self.end_compile()
                # A stray ';' outside a definition is ignored; any tokens after
                # ';' on the same line continue in interpret mode.
                continue
            if name == ":":
                if self.compiling:
                    raise ForthError("nested ':'")
                self.start_compile(toks[i].value)
                i += 1
                continue
            if name == "]":
                cs.interpret_mode = False
                continue
            if name == "[":
                cs.interpret_mode = True
                continue

            if name == "CHAR":
                # CHAR consumes the following token as a single character.  It
                # needs lookahead, so handle it here rather than at runtime.
                dest = self.current.body if self.compiling else temp
                if i < n and toks[i].kind in ("word", "num", "str"):
                    value = toks[i].value or ""
                    ch = value[0] if value else " "
                    i += 1
                else:
                    ch = " "
                self._flush(dest)
                dest.append(["lit", to_cell(ord(ch))])
                continue

            entry = self.find(name)
            if entry is None:
                # Fall back to number parsing.  If it parses under the current
                # base, treat it as a literal now; otherwise emit a deferred
                # literal cell so the value can be resolved at execution time
                # (this makes ``HEX 1F`` work, since HEX runs before 1F is
                # resolved even though the whole line is built first).
                val = self.try_number(t.value)
                if val is not None:
                    cs.numbuf.append(val)
                    continue
                (self.current.body if self.compiling else temp).append(
                    ["litnum", t.value])
                continue
            p = entry.primary

            # Defining words run their compile action immediately (this is how
            # CREATE / VARIABLE / CONSTANT work even at the top level).
            if p is not None and p.defining and p.compile is not None:
                p.compile(self, toks, i)
                if cs.advance_by:
                    i = cs.advance_by
                    cs.advance_by = 0
                continue

            # Normal word: flush buffered numbers, then emit a cell into the
            # appropriate destination (current definition or temp list).
            if name == "+LOOP" and cs.numbuf:
                # A number immediately preceding +LOOP is its constant step.
                step = cs.numbuf.pop()
                dest.append(["ploop", to_cell(step)])
                continue
            dest = self.current.body if self.compiling else temp
            self._flush(dest)
            if entry.body is not None:
                dest.append(["sec", name])
            else:
                dest.append(["prim", name])

        # Execute any cells accumulated in interpret mode.
        if not self.compiling and temp:
            self.exec_tokens(temp, 0, len(temp))

    def _flush(self, dest):
        """Flush buffered numbers to ``dest`` as literal cells."""
        if not self.compile_state.numbuf:
            return
        for v in self.compile_state.numbuf:
            dest.append(["lit", to_cell(v)])
        self.compile_state.numbuf = []

    def _try_compile_number(self, s):
        toks = self.tokenize(s)
        if toks and toks[0].kind == "num":
            return toks[0].value
        return None

    # -- static strings ----------------------------------------------------

    def make_string(self, text):
        return self._make_static_string(text)

    def _make_static_string(self, text):
        n = len(text)
        if n > 255:
            raise ForthError("string too long")
        addr = self.mem.alloc_string(n + 1)
        self.mem.cset(addr, n)
        for idx, ch in enumerate(text):
            self.mem.cset(addr + 1 + idx, ord(ch))
        return addr

    # -- execution ---------------------------------------------------------

    def execute_word(self, name):
        entry = self.find(name)
        if entry is None:
            raise ForthError(f"?NAME? {name}")
        if entry.body is not None:
            self.execute_body(entry.body)
            return
        p = entry.primary
        if p is None or p.execute is None:
            raise ForthError(f"{name} has no execution semantics")
        p.execute(self)

    def execute_prim(self, name):
        entry = self.find(name)
        if entry is None or entry.primary is None or entry.primary.execute is None:
            raise ForthError(f"?NAME? {name}")
        entry.primary.execute(self)

    def execute_body(self, body):
        self.exec_tokens(body, 0, len(body))

    # -- unified token/cell executor --------------------------------------
    # A "cell" is a small list [tag, value] where tag is one of:
    #   'lit'  -> value is a number/string to push
    #   'prim' -> value is the word name (looked up at runtime)
    #   'sec'  -> value is a secondary word name (threaded call)
    # Control structures are executed by scanning this cell list at runtime,
    # which lets the same code path serve both top-level input and compiled
    # definitions.

    def exec_tokens(self, cells, i=0, end=None):
        if end is None:
            end = len(cells)
        while i < end:
            c = cells[i]
            tag = c[0]
            if tag == "lit":
                self.ds.push(c[1])
                i += 1
            elif tag == "litnum":
                val = self.try_number(c[1])
                if val is None:
                    raise ForthError(f"?NAME? {c[1]}")
                self.ds.push(val)
                i += 1
            elif tag == "sec":
                self.execute_word(c[1])
                i += 1
            elif tag == "exit":
                return i
            else:  # prim
                name = c[1]
                entry = self.find(name)
                if entry is None:
                    raise ForthError(f"?NAME? {name}")
                p = entry.primary
                if p is not None and p.is_control:
                    i = p.execute(self, cells, i)
                else:
                    p.execute(self)
                    i += 1
        return i

    # -- control-structure scanning helpers -------------------------------

    OPENERS = {"IF", "DO", "?DO", "BEGIN", "WHILE", "CASE", "OF"}
    CLOSERS = {"THEN", "LOOP", "+LOOP", "AGAIN", "UNTIL", "REPEAT", "ENDOF", "ENDCASE"}

    def find_match(self, cells, i, closer_names, start_depth=1, require_depth=True):
        """Scan forward from ``i`` for the first loop-terminator cell.

        A terminator is a ``["prim", "LOOP"/"+LOOP"]`` cell whose name is in
        ``closer_names``, or a ``["ploop", step]`` cell (constant-step +LOOP).
        When ``require_depth`` is true (the DO/LOOP case) the match must occur
        at nesting depth zero; LEAVE uses ``require_depth=False`` to jump to the
        nearest terminator regardless of nesting.
        """
        depth = start_depth
        n = len(cells)
        j = i + 1
        while j < n:
            c = cells[j]
            tag = c[0]
            if tag == "ploop":
                return j
            if tag != "prim":
                j += 1
                continue
            v = c[1]
            if require_depth:
                if v in self.OPENERS:
                    depth += 1
                elif v in self.CLOSERS:
                    depth -= 1
                    if depth == 0 and v in closer_names:
                        return j
            else:
                if v in closer_names:
                    return j
            j += 1
        return None

    def cur_loop(self):
        if not self.loops:
            raise ForthError("I without DO")
        return self.loops[-1]

    def loop_at(self, n):
        if len(self.loops) <= n:
            raise ForthError("J without enough DOs")
        return self.loops[-1 - n]


_DONE = object()

# Words that consume buffered numbers / tokens from the compilation stream.
_OPERAND_WORDS = {
    "CONSTANT", "LITERAL", "+LOOP", "ALIAS", "POSTPONE",
    "VARIABLE", "CREATE", "DOES>", "ALLOT", "IMMEDIATE",
}
