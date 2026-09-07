"""Catalogue of FORTH primary (built-in) words for PyForth.

This module registers a fairly complete ANSI-FORTH core together with a set
of extensions (strings, arrays, files, extended math and I/O).  It is installed
by :func:`register_words` onto a :class:`forth.machine.Forth` instance.
"""

from __future__ import annotations

import math
import os

from .machine import Primary, to_cell, CELL_MASK


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _read_string_at(f, addr):
    n = f.mem.cget(addr)
    return "".join(chr(f.mem.cget(addr + 1 + j)) for j in range(n))


def _write_string_to_mem(f, text, addr):
    n = len(text)
    if n > 255:
        raise RuntimeError("string too long for single-byte length")
    f.mem.cset(addr, n)
    for idx, ch in enumerate(text):
        f.mem.cset(addr + 1 + idx, ord(ch) & 0xFF)
    return addr


def _number_to_str(f, n, base):
    """Format a (possibly signed) cell in the given base."""
    neg = n < 0
    if neg:
        n = -n
    if base == 10:
        digits = "0123456789ABCDEF"
    elif base == 16:
        digits = "0123456789ABCDEF"
    elif base == 8:
        digits = "01234567"
    elif base == 2:
        digits = "01"
    else:
        digits = "0123456789ABCDEF"
    if n == 0:
        s = "0"
    else:
        out = []
        while n > 0:
            out.insert(0, digits[n % base])
            n //= base
        s = "".join(out)
    return "-" + s if neg else s


def _pad(f):
    return f.uv["PAD"]


# ---------------------------------------------------------------------------
# Register everything
# ---------------------------------------------------------------------------

def register_words(f):
    reg = f.register

    def P(execute=None, compile=None, compile_only=False, is_control=False,
          defining=False):
        return Primary(execute, compile, compile_only, is_control, defining)

    def add(name, primary, immediate=False):
        reg(name, primary)
        if immediate:
            f.set_immediate(name)

    # =======================================================================
    # Stack manipulation
    # =======================================================================
    add("DUP", P(lambda f: f.ds.push(f.ds.peek())))
    add("DROP", P(lambda f: f.ds.pop()))
    add("SWAP", P(_swap))
    add("ROT", P(_rot))
    add("-ROT", P(_nrot))
    add("OVER", P(_over))
    add("TUCK", P(_tuck))
    add("NIP", P(_nip))
    add("2DUP", P(_2dup))
    add("2DROP", P(_2drop))
    add("2SWAP", P(_2swap))
    add("2OVER", P(_2over))
    add("3DUP", P(_3dup))
    add("CLEAR", P(_clear))
    add("DEPTH", P(_depth))
    add(".S", P(_dot_s))
    add("PICK", P(_pick, compile=_compile_pick))
    add(".ROT", P(_dotrot))

    # n.PICK and n.ROT families
    for _n in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30):
        nm = f"{_n}.PICK"
        add(nm, P(lambda f, n=_n: _pick_n(f, n)))
    for _n in (2, 3, 4, 5, 6, 7, 8, 9):
        nm = f"{_n}.ROT"
        add(nm, P(lambda f, n=_n: _rot_n(f, n)))

    # =======================================================================
    # Return stack
    # =======================================================================
    add(">R", P(_gt_r))
    add("R>", P(_r_from))
    add("R@", P(_r_peek))
    add(">R?", P(_gt_r_q))

    # =======================================================================
    # Arithmetic
    # =======================================================================
    def _add(f):
        b = f.ds.pop(); a = f.ds.pop(); f.ds.push(a + b)
    def _sub(f):
        b = f.ds.pop(); a = f.ds.pop(); f.ds.push(a - b)
    def _mul(f):
        b = f.ds.pop(); a = f.ds.pop(); f.ds.push(a * b)
    def _div(f):
        b = f.ds.pop(); a = f.ds.pop()
        if b == 0: raise RuntimeError("division by zero")
        # FORTH '/' truncates toward zero (unlike Python's floor '//').
        q = abs(a) // abs(b)
        if (a < 0) != (b < 0):
            q = -q
        f.ds.push(to_cell(q))

    def _mod(f):
        b = f.ds.pop(); a = f.ds.pop()
        if b == 0: raise RuntimeError("division by zero")
        # remainder carries the sign of the dividend (matches '/')
        q = abs(a) // abs(b)
        if (a < 0) != (b < 0):
            q = -q
        r = a - q * b
        f.ds.push(to_cell(r))
    add("+", P(_add))
    add("-", P(_sub))
    add("*", P(_mul))
    add("/", P(_div))
    add("MOD", P(_mod))
    add("NEGATE", P(lambda f: f.ds.push(to_cell(-f.ds.peek()))))
    add("ABS", P(_abs))
    add("2*", P(lambda f: f.ds.push(to_cell(f.ds.pop() * 2))))
    add("2/", P(lambda f: f.ds.push(to_cell(f.ds.pop() // 2))))
    add("MIN", P(_min))
    add("MAX", P(_max))
    add("1+", P(lambda f: f.ds.push(to_cell(f.ds.pop() + 1))))
    add("1-", P(lambda f: f.ds.push(to_cell(f.ds.pop() - 1))))
    add("2+", P(lambda f: f.ds.push(to_cell(f.ds.pop() + 2))))
    add("2-", P(lambda f: f.ds.push(to_cell(f.ds.pop() - 2))))
    # floating point style words
    add("F+", P(_fadd))
    add("F-", P(_fsub))
    add("F*", P(_fmul))
    add("F/", P(_fdiv))
    # FM/ and UM/M (signed/unsigned divide)
    add("FM/", P(_fmdiscard))
    add("FM/DP", P(_fmdiv))
    add("UM/M", P(_umdiscard))
    add("UM/DP", P(_umdp))
    add("/+", P(_plusdiv))
    add("-/", P(_minusdiv))
    # floating point extensions (operate on the data stack as cells)
    add("SQRT", P(_sqrt))
    add("ABS", P(_abs))
    add("CEIL", P(_ceil))
    add("FLOOR", P(_floor))
    add("FRAC", P(_frac))
    add("TRUNC", P(_trunc))
    add("**", P(_pow))
    add("POW", P(_pow))
    add("EXP", P(_exp))
    add("LN", P(_ln))
    add("LOG", P(_log))
    add("SIN", P(_sin))
    add("COS", P(_cos))
    add("TAN", P(_tan))
    add("ATAN", P(_atan))
    add("AT2", P(_at2))

    # =======================================================================
    # Comparison
    # =======================================================================
    add("=", P(_eq2))
    add("<>", P(_neq))
    add("<", P(_lt))
    add(">", P(_gt2))
    add("<=", P(_le))
    add(">=", P(_ge))
    add("0=", P(_zpe))
    add("0<", P(_ltz))
    add("0>", P(_gtz))
    add("0<>", P(_neq0))
    add("1<", P(_one_lt))
    add("2>", P(_two_gt))
    add("<DUP", P(_lt_dup))

    # =======================================================================
    # Bitwise
    # =======================================================================
    add("AND", P(lambda f: f.ds.push(to_cell(f.ds.pop() & f.ds.pop()))))
    add("OR", P(lambda f: f.ds.push(to_cell(f.ds.pop() | f.ds.pop()))))
    add("XOR", P(_xor))
    add("NOT", P(lambda f: f.ds.push(to_cell(~f.ds.pop()))))
    add("LSHIFT", P(_lshift))
    add("RSHIFT", P(_rshift))
    add("?LSHIFT", P(_ulshift))
    add("?RSHIFT", P(_urshift))
    add("2*/", P(_twostarf))

    # =======================================================================
    # Memory access
    # =======================================================================
    add("@", P(_at))
    add("!", P(_bang))
    add("+!", P(_plusbang))
    add("@+", P(_atplus))
    add("@-", P(_atminus))
    add("C@", P(_c_at))
    add("C!", P(_c_bang))
    add("CHAIN", P(_chain))

    # =======================================================================
    # Data stack info words
    # =======================================================================
    add("SP@", P(lambda f: f.ds.push(f.sp_addr)))
    add("SP!", P(_sp_store))
    add("RS@", P(lambda f: f.ds.push(f.rs_addr)))
    add("BASE", P(lambda f: f.ds.push(f.uv["BASE"])))
    add(">IN", P(lambda f: f.ds.push(f.uv[">IN"])))
    add("SPAN", P(lambda f: f.ds.push(f.uv["SPAN"])))

    # =======================================================================
    # Number base handling
    # =======================================================================
    add("DECIMAL", P(lambda f: _set_base(f, 10)))
    add("HEX", P(lambda f: _set_base(f, 16)))
    add("OCTAL", P(lambda f: _set_base(f, 8)))
    add("BINARY", P(lambda f: _set_base(f, 2)))
    add("16#", P(_base_prefix, compile=_compile_base_prefix))
    add("8#", P(_base_prefix, compile=_compile_base_prefix))
    add("2#", P(_base_prefix, compile=_compile_base_prefix))

    # =======================================================================
    # Number conversion: # #S #> >NUMBER NUMBER?
    # =======================================================================
    add("#", P(_hash))
    add("#S", P(_hashs))
    add("#>", P(_hashgt))
    add(">NUMBER", P(_numbertonumber))
    add("NUMBER?", P(_numberq, compile=_compile_numberq))
    add("D#", P(_dhash))
    add("UD#", P(_udhash))

    # =======================================================================
    # Basic I/O
    # =======================================================================
    add(".", P(_dot))
    add("?.", P(_qdot))
    add("S.", P(_s_dot))
    add("EMIT", P(_emit))
    add("TYPE", P(_type))
    add("SPACE", P(lambda f: f.emit(" ")))
    add("SPACES", P(_spaces))
    add("CR", P(lambda f: f.emit("\n")))
    add("PAGE", P(lambda f: f.emit("\n\n")))
    add("KEY", P(_key))
    add("EXPECT", P(_expect))
    add("ACCEPT", P(_accept))
    add("READLINE", P(_readline))
    add(".\"", P(_dot_quote, compile=_compile_dquote))
    add("S\"", P(_noop_execute))
    add("STR@", P(_str_at))
    add("STR!", P(_str_bang))
    add("LEN", P(_len))
    add("CHAR", P(_char, compile=_compile_char))
    add("COUNT", P(_count))
    add("STRING=", P(_string_eq))
    add("STRING<", P(_string_lt))
    add("STRING>", P(_string_gt))

    # =======================================================================
    # Compiler / system words
    # =======================================================================
    add("STATE", P(_state))
    add("[", P(_bracket, compile=_compile_bracket), immediate=True)
    add("]", P(_square, compile=_compile_square), immediate=True)
    add("[']", P(_lit_tick, compile=_compile_lit_tick), immediate=True)
    add("[COMPILE]", P(_compile_compile), immediate=True)
    add("LITERAL", P(_literal, compile=_compile_literal), immediate=True)
    add("POSTPONE", P(_postpone, compile=_compile_postpone), immediate=True)
    add("IMMEDIATE", P(_immediate), immediate=True)
    add("EXECUTE", P(_execute))
    add("ABORT", P(_abort))
    add("ABORT\"", P(_abort_quote, compile=_compile_abort_quote))
    add("?", P(_question))
    add("WORD", P(_word))
    add("INTERPRET", P(_interpret))
    add("SOURCE", P(_source))

    # =======================================================================
    # Defining words
    # =======================================================================
    add("VARIABLE", P(_variable, compile=_compile_variable, defining=True), immediate=True)
    add("CONSTANT", P(_constant, compile=_compile_constant, defining=True), immediate=True)
    add("CREATE", P(_create, compile=_compile_create, defining=True), immediate=True)
    add("ALIAS", P(_alias, compile=_compile_alias, defining=True), immediate=True)
    add("ALLOT", P(_allot, compile=_compile_allot, defining=True), immediate=True)
    add("DOES>", P(_noop_execute, compile=_compile_does, defining=True), immediate=True)
    add("STRUCT", P(_struct, compile=_compile_struct, defining=True), immediate=True)
    add("ENDSTRUCT", P(_endstruct, compile=_compile_endstruct, defining=True), immediate=True)
    add("FIELD", P(_field, compile=_compile_field, defining=True), immediate=True)

    # =======================================================================
    # Control structures (immediate, runtime-scanned)
    # =======================================================================
    add("IF", P(execute=_exec_if, is_control=True), immediate=True)
    add("ELSE", P(execute=_exec_else, is_control=True), immediate=True)
    add("THEN", P(execute=_exec_then, is_control=True), immediate=True)
    add("BEGIN", P(execute=_exec_begin, is_control=True))
    add("AGAIN", P(execute=_exec_again, is_control=True))
    add("UNTIL", P(execute=_exec_until, is_control=True))
    add("REPEAT", P(execute=_exec_repeat, is_control=True))
    add("WHILE", P(execute=_exec_while, is_control=True))
    add("DO", P(execute=_exec_do, is_control=True))
    add("?DO", P(execute=_exec_do, is_control=True))
    add("LOOP", P(execute=_exec_loop, is_control=True))
    add("+LOOP", P(execute=_exec_plusloop, is_control=True))
    add("I", P(_i))
    add("J", P(_j))
    add("K", P(_k))
    add("UNDO", P(execute=_noop_execute, is_control=True))
    add("LEAVE", P(execute=_exec_leave, is_control=True))
    add("CASE", P(execute=_exec_case, is_control=True))
    add("OF", P(execute=_exec_of, is_control=True))
    add("ENDOF", P(execute=_noop_execute, is_control=True))
    add("ENDCASE", P(execute=_exec_endcase, is_control=True))
    add("SELECTCASE", P(execute=_exec_case, is_control=True))

    # =======================================================================
    # Arrays (extension)
    # =======================================================================
    add("ARRAYS", P(_arrays, compile=_compile_arrays, defining=True))


# ---------------------------------------------------------------------------
# Stack word implementations
# ---------------------------------------------------------------------------

def _swap(f):
    a = f.ds.pop(); b = f.ds.pop(); f.ds.push(a); f.ds.push(b)

def _rot(f):
    c = f.ds.pop(); b = f.ds.pop(); a = f.ds.pop()
    f.ds.push(b); f.ds.push(c); f.ds.push(a)

def _nrot(f):
    d = f.ds.pop(); c = f.ds.pop(); b = f.ds.pop(); a = f.ds.pop()
    f.ds.push(d); f.ds.push(a); f.ds.push(b); f.ds.push(c)

def _over(f):
    b = f.ds.pop(); a = f.ds.pop()
    f.ds.push(a); f.ds.push(b); f.ds.push(a)

def _tuck(f):
    b = f.ds.pop(); a = f.ds.pop()
    f.ds.push(b); f.ds.push(a); f.ds.push(b)

def _nip(f):
    b = f.ds.pop(); a = f.ds.pop()
    f.ds.push(b)

def _2dup(f):
    b = f.ds.pop(); a = f.ds.pop()
    f.ds.push(a); f.ds.push(b); f.ds.push(a); f.ds.push(b)

def _2drop(f):
    f.ds.pop(); f.ds.pop()

def _2swap(f):
    d = f.ds.pop(); c = f.ds.pop(); b = f.ds.pop(); a = f.ds.pop()
    f.ds.push(c); f.ds.push(d); f.ds.push(a); f.ds.push(b)

def _2over(f):
    d = f.ds.pop(); c = f.ds.pop(); b = f.ds.pop(); a = f.ds.pop()
    f.ds.push(a); f.ds.push(b); f.ds.push(c); f.ds.push(d); f.ds.push(a); f.ds.push(b)

def _3dup(f):
    c = f.ds.pop(); b = f.ds.pop(); a = f.ds.pop()
    for v in (a, b, c):
        f.ds.push(v)
    for v in (a, b, c):
        f.ds.push(v)

def _clear(f):
    f.ds.data.clear()

def _gt(f):
    # placeholder replaced by DEPTH
    pass

def _depth(f):
    f.ds.push(f.ds.depth())

def _dot_s(f):
    # ( -- )  Dump the data stack, top first.
    items = [str(v) for v in reversed(f.ds.data)]
    f.emit(" ".join(items) if items else "empty")

def _eq(f):
    # equalcount: not standard; ignore
    pass

def _pick(f):
    n = f.ds.pop()
    f.ds.push(f.ds.peek(n))

def _compile_pick(f, toks, i):
    # N PICK : read N from numbuf if present else runtime
    nb = f.compile_state.numbuf
    if nb:
        n = nb.pop()
        f.emit_cell("lit", to_cell(n))
        f.emit_prim("PICK")   # runtime: push N then PICK -> but PICK pops N
    else:
        f.emit_prim("PICK")

def _pick_n(f, n):
    f.ds.push(f.ds.peek(n - 1))

def _rot_n(f, n):
    # n.ROT
    stack = f.ds.data
    # rotate top n+1 items
    item = stack[-n]
    del stack[-n]
    stack.append(item)

def _dotrot(f):
    # ( a b c -- c a b )
    c = f.ds.pop(); b = f.ds.pop(); a = f.ds.pop()
    f.ds.push(c); f.ds.push(a); f.ds.push(b)

def _gt_r(f):
    v = f.ds.pop()
    f.rs.push(v)

def _r_from(f):
    f.ds.push(f.rs.pop())

def _r_peek(f):
    f.ds.push(f.rs.peek())

def _gt_r_q(f):
    v = f.ds.pop()
    f.rs.push(v)
    f.ds.push(v)

def _i(f):
    f.ds.push(f.cur_loop()[0])

def _j(f):
    f.ds.push(f.loop_at(1)[0])

def _k(f):
    f.ds.push(f.loop_at(2)[0])
    f.ds.push(v)


# ---------------------------------------------------------------------------
# Arithmetic implementations
# ---------------------------------------------------------------------------

def _abs(f):
    a = f.ds.pop()
    f.ds.push(to_cell(abs(a)))

def _min(f):
    b = f.ds.pop(); a = f.ds.pop()
    f.ds.push(to_cell(min(a, b)))

def _max(f):
    b = f.ds.pop(); a = f.ds.pop()
    f.ds.push(to_cell(max(a, b)))

def _incdec(f):
    a = f.ds.pop(); b = f.ds.pop()
    f.ds.push(to_cell(a + b))

def _fadd(f):
    b = f.ds.pop(); a = f.ds.pop(); f.ds.push(to_cell(a + b))

def _fsub(f):
    b = f.ds.pop(); a = f.ds.pop(); f.ds.push(to_cell(a - b))

def _fmul(f):
    b = f.ds.pop(); a = f.ds.pop(); f.ds.push(to_cell(a * b))

def _fdiv(f):
    b = f.ds.pop(); a = f.ds.pop()
    if b == 0: raise RuntimeError("division by zero")
    f.ds.push(to_cell(a // b))

def _fmdiv(f):
    # ( n1 n2 -- r q ) signed divide: quotient truncated toward zero,
    # remainder carries the sign of the dividend (n1).
    nlim = f.ds.pop(); n = f.ds.pop()
    if nlim == 0: raise RuntimeError("division by zero")
    q = abs(n) // abs(nlim)
    if (n < 0) != (nlim < 0):
        q = -q
    r = n - q * nlim
    f.ds.push(to_cell(r)); f.ds.push(to_cell(q))

def _fmdiscard(f):
    _fmdiv(f)
    f.ds.pop(); f.ds.pop()

def _umdiv(f):
    # ( ud u -- r q ) unsigned double-length divide
    u = f.ds.pop(); ud_lo = f.ds.pop(); ud_hi = f.ds.pop()
    if u == 0: raise RuntimeError("division by zero")
    ud = ud_hi * (2 ** 32) + ud_lo
    q = ud // u
    r = ud % u
    f.ds.push(to_cell(r)); f.ds.push(to_cell(q))

def _umdiscard(f):
    _umdiv(f)
    f.ds.pop(); f.ds.pop()

def _umdp(f):
    _umdiv(f)

def _plusdiv(f):
    b = f.ds.pop(); a = f.ds.pop()
    if b == 0: raise RuntimeError("division by zero")
    r = abs(a % b)
    if (a < 0) != (b < 0) and r != 0:
        r = -r
    f.ds.push(to_cell(r))

def _minusdiv(f):
    b = f.ds.pop(); a = f.ds.pop()
    if b == 0: raise RuntimeError("division by zero")
    # round toward negative infinity
    f.ds.push(to_cell(-((-a) // b)))

def _sqrt(f):
    a = f.ds.pop()
    if a < 0: raise RuntimeError("sqrt of negative")
    f.ds.push(to_cell(int(math.sqrt(a))))

def _ceil(f):
    a = f.ds.pop()
    f.ds.push(to_cell(math.ceil(a)))

def _floor(f):
    a = f.ds.pop()
    f.ds.push(to_cell(math.floor(a)))

def _frac(f):
    a = f.ds.pop()
    f.ds.push(to_cell(a - math.floor(a)))

def _trunc(f):
    a = f.ds.pop()
    f.ds.push(to_cell(int(math.trunc(a))))

def _pow(f):
    b = f.ds.pop(); a = f.ds.pop()
    f.ds.push(to_cell(int(a ** b)))

def _exp(f):
    a = f.ds.pop(); f.ds.push(to_cell(int(math.exp(a))))

def _ln(f):
    a = f.ds.pop(); f.ds.push(to_cell(int(math.log(a))))

def _log(f):
    a = f.ds.pop(); f.ds.push(to_cell(int(math.log10(a))))

def _sin(f):
    a = f.ds.pop(); f.ds.push(to_cell(int(math.sin(a))))

def _cos(f):
    a = f.ds.pop(); f.ds.push(to_cell(int(math.cos(a))))

def _tan(f):
    a = f.ds.pop(); f.ds.push(to_cell(int(math.tan(a))))

def _atan(f):
    a = f.ds.pop(); f.ds.push(to_cell(int(math.atan(a))))

def _at2(f):
    b = f.ds.pop(); a = f.ds.pop()
    f.ds.push(to_cell(int(math.atan2(a, b))))


# ---------------------------------------------------------------------------
# Comparison implementations
# ---------------------------------------------------------------------------

def _eq2(f):
    b = f.ds.pop(); a = f.ds.pop(); f.ds.push(to_cell(-1 if a == b else 0))

def _neq(f):
    b = f.ds.pop(); a = f.ds.pop(); f.ds.push(to_cell(-1 if a != b else 0))

def _lt(f):
    b = f.ds.pop(); a = f.ds.pop(); f.ds.push(to_cell(-1 if a < b else 0))

def _gt2(f):
    b = f.ds.pop(); a = f.ds.pop(); f.ds.push(to_cell(-1 if a > b else 0))

def _le(f):
    b = f.ds.pop(); a = f.ds.pop(); f.ds.push(to_cell(-1 if a <= b else 0))

def _ge(f):
    b = f.ds.pop(); a = f.ds.pop(); f.ds.push(to_cell(-1 if a >= b else 0))

def _zpe(f):
    a = f.ds.pop(); f.ds.push(to_cell(-1 if a == 0 else 0))

def _ltz(f):
    a = f.ds.pop(); f.ds.push(to_cell(-1 if a < 0 else 0))

def _gtz(f):
    a = f.ds.pop(); f.ds.push(to_cell(-1 if a > 0 else 0))

def _neq0(f):
    a = f.ds.pop(); f.ds.push(to_cell(-1 if a != 0 else 0))

def _one_lt(f):
    # ( n -- 0<n<1 ? ) not standard; implement as 1 < n
    a = f.ds.pop(); f.ds.push(to_cell(-1 if 1 < a else 0))

def _two_gt(f):
    a = f.ds.pop(); f.ds.push(to_cell(-1 if 2 > a else 0))

def _lt_dup(f):
    # ( n -- n n ) if n<0 ; used by some number routines - no-op placeholder
    a = f.ds.pop(); f.ds.push(a); f.ds.push(a)


# ---------------------------------------------------------------------------
# Bitwise implementations
# ---------------------------------------------------------------------------

def _xor(f):
    b = f.ds.pop(); a = f.ds.pop(); f.ds.push(to_cell(a ^ b))

def _lshift(f):
    b = f.ds.pop(); a = f.ds.pop(); f.ds.push(to_cell(a << b))

def _rshift(f):
    b = f.ds.pop(); a = f.ds.pop(); f.ds.push(to_cell(a >> b))

def _ulshift(f):
    b = f.ds.pop(); a = f.ds.pop()
    f.ds.push(to_cell((a & CELL_MASK) << (b & 63)))

def _urshift(f):
    b = f.ds.pop(); a = f.ds.pop()
    f.ds.push(to_cell((a & CELL_MASK) >> (b & 63)))

def _twostarf(f):
    # ( n x -- n*x/2 )
    x = f.ds.pop(); n = f.ds.pop()
    f.ds.push(to_cell((n << x) // 2))


# ---------------------------------------------------------------------------
# Memory implementations
# ---------------------------------------------------------------------------

def _at(f):
    a = f.ds.pop(); f.ds.push(f.mem.cell_get(a))

def _bang(f):
    a = f.ds.pop(); v = f.ds.pop(); f.mem.cell_set(a, v)

def _plusbang(f):
    # ( n a -- )  a := a + n
    a = f.ds.pop(); n = f.ds.pop(); f.mem.cell_set(a, f.mem.cell_get(a) + n)

def _atplus(f):
    a = f.ds.pop(); f.ds.push(a); f.mem.cell_get  # touch
    v = f.mem.cell_get(a); f.mem.cell_set(a, v + 1); f.ds.push(v)

def _atminus(f):
    a = f.ds.pop()
    v = f.mem.cell_get(a); f.mem.cell_set(a, v - 1); f.ds.push(v)

def _c_at(f):
    a = f.ds.pop(); f.ds.push(f.mem.cget(a))

def _c_bang(f):
    a = f.ds.pop(); v = f.ds.pop(); f.mem.cset(a, v)

def _chain(f):
    # ( a1 a2 -- ) copy string from a2 into a1 (length from a2's length byte)
    b = f.ds.pop(); a = f.ds.pop()
    n = f.mem.cget(b)
    for j in range(n):
        f.mem.cset(a + j, f.mem.cget(b + j))


# ---------------------------------------------------------------------------
# Stack pointer words
# ---------------------------------------------------------------------------

def _sp_store(f):
    a = f.ds.pop(); f.sp_addr = a


# ---------------------------------------------------------------------------
# Base handling
# ---------------------------------------------------------------------------

def _set_base(f, base):
    f.mem.cell_set(f.uv["BASE"], base)


def _base_prefix(f):
    pass


def _compile_base_prefix(f, toks, i):
    nb = f.compile_state.numbuf
    if nb:
        base = nb.pop()
    else:
        raise RuntimeError("base prefix needs a number")
    f.mem.cell_set(f.uv["BASE"], to_cell(base))


# ---------------------------------------------------------------------------
# Number conversion words
# ---------------------------------------------------------------------------

def _hash(f):
    # ( n -- n' ) emit one digit of n in current base into PAD
    n = f.ds.pop()
    base = f.mem.cell_get(f.uv["BASE"])
    if n < 0:
        f.emit("-")
        n = -n
    if n == 0:
        f.emit("0")
    else:
        while n > 0:
            n, r = divmod(n, base)
            f.emit(chr(ord("0") + r if r < 10 else ord("A") + r - 10))
    f.ds.push(to_cell(n))

def _hashs(f):
    while f.ds.peek() != 0:
        _hash(f)
    # drop the zero
    f.ds.pop()

def _hashgt(f):
    # ( n -- a# ) convert n (already in PAD) to a NUL-terminated string
    base = f.mem.cell_get(f.uv["BASE"])
    n = f.ds.pop()
    if n < 0:
        f.mem.cset(_pad(f), ord("-") & 0xFF)
    else:
        f.mem.cset(_pad(f), 0)
    if n == 0:
        f.mem.cset(_pad(f) + 1, ord("0") & 0xFF)
    else:
        pos = 0
        while n > 0:
            n, r = divmod(n, base)
            ch = chr(ord("0") + r) if r < 10 else chr(ord("A") + r - 10)
            f.mem.cset(_pad(f) + 1 + pos, ord(ch) & 0xFF)
            pos += 1
    f.ds.push(_pad(f))

def _numbertonumber(f):
    # ( #in #out a# -- #in' #out' a# ) accumulate a number in given base
    a = f.ds.pop()
    out = f.ds.pop()
    inn = f.ds.pop()
    base = f.mem.cell_get(f.uv["BASE"])
    digit = f.mem.cget(a + inn) - ord("0")
    if 0 <= digit < base:
        out = out * base + digit
        inn += 1
    f.ds.push(inn); f.ds.push(out); f.ds.push(a)

def _hash2(f):
    pass

def _numberq(f):
    pass

def _compile_numberq(f, toks, i):
    pass

def _dhash(f):
    pass

def _udhash(f):
    pass


# ---------------------------------------------------------------------------
# I/O words
# ---------------------------------------------------------------------------

def _dot(f):
    n = f.ds.pop()
    base = f.mem.cell_get(f.uv["BASE"])
    f.emit(" " + _number_to_str(f, n, base) + " ")

def _qdot(f):
    n = f.ds.pop()
    base = f.mem.cell_get(f.uv["BASE"])
    f.emit(" " + _number_to_str(f, n, base) + " ")

def _emit(f):
    c = f.ds.pop() & 0xFF
    f.emit(chr(c))

def _type(f):
    n = f.ds.pop(); a = f.ds.pop()
    f.emit("".join(chr(f.mem.cget(a + j)) for j in range(n)))

def _spaces(f):
    n = f.ds.pop()
    f.emit(" " * n)

def _key(f):
    c = f.get_key()
    f.ds.push(to_cell(c))

def _expect(f):
    a = f.ds.pop(); n = f.ds.pop()
    count = 0
    while count < n:
        c = f.get_key()
        if c < 0:
            break
        if c in (13, 10):
            break
        f.mem.cset(a + count, c & 0xFF)
        count += 1
    f.mem.cset(a, count)
    f.mem.cell_set(f.uv["SPAN"], count)
    f.ds.push(a)
    f.ds.push(count)

def _accept(f):
    a = f.ds.pop(); n = f.ds.pop()
    count = 0
    buf = []
    while count < n:
        c = f.get_key()
        if c < 0 or c in (13, 10):
            break
        f.mem.cset(a + count, c & 0xFF)
        count += 1
    f.mem.cell_set(f.uv["SPAN"], count)

def _readline(f):
    a = f.ds.pop(); n = f.ds.pop()
    count = 0
    while count < n:
        c = f.get_key()
        if c < 0 or c == 13:
            break
        if c == 10:
            break
        f.mem.cset(a + count, c & 0xFF)
        count += 1
    f.mem.cset(a, count)
    f.ds.push(a)
    f.ds.push(count)

def _dot_quote(f):
    a = f.ds.pop()
    f.emit(_read_string_at(f, a))

def _s_dot(f):
    a = f.ds.pop()
    f.emit(_read_string_at(f, a))

def _compile_dquote(f, toks, i):
    # ." text" : compile a push of the string address followed by S.
    name = toks[i].value if i < len(toks) else ""
    f.compile_state.advance_by = i + 1
    addr = f._make_static_string(name)
    f.emit_cell("lit", addr)
    f.emit_prim("S.")

def _s_quote(f):
    a = f.ds.pop()
    f.emit(_read_string_at(f, a))

def _compile_s_quote(f, toks, i):
    addr = f._make_static_string(i)  # unused; real text handled by tokenizer
    f.emit_cell("lit", addr)

def _str_at(f):
    # ( a# -- a# ) return pointer to start of string body (skip length byte)
    a = f.ds.pop()
    f.ds.push(a)

def _str_bang(f):
    # ( a# s# -- ) copy string s# into a#
    dst = f.ds.pop(); src = f.ds.pop()
    n = f.mem.cget(src)
    for j in range(n):
        f.mem.cset(dst + j, f.mem.cget(src + j))

def _len(f):
    a = f.ds.pop()
    f.ds.push(f.mem.cget(a))

def _count(f):
    a = f.ds.pop()
    n = f.mem.cget(a)
    f.ds.push(a)
    f.ds.push(a + 1)
    f.ds.push(to_cell(n))

def _read_counted(f, a):
    n = f.mem.cget(a)
    return [f.mem.cget(a + 1 + j) for j in range(n)]

def _string_cmp(f, order):
    a2 = f.ds.pop(); a1 = f.ds.pop()
    s1 = _read_counted(f, a1)
    s2 = _read_counted(f, a2)
    if order == 0:
        result = s1 == s2
    elif order < 0:
        result = s1 < s2
    else:
        result = s1 > s2
    f.ds.push(to_cell(-1 if result else 0))

def _string_eq(f):
    _string_cmp(f, 0)

def _string_lt(f):
    _string_cmp(f, -1)

def _string_gt(f):
    _string_cmp(f, 1)

def _char(f):
    c = f.ds.pop()
    f.ds.push(to_cell(ord(chr(c))))

def _compile_char(f, toks, i):
    name = toks[i].value if i < len(toks) else ""
    f.compile_state.advance_by = i + 1
    f.emit_cell("lit", to_cell(ord(name[0]) if name else 0))

def _noop_execute(f):
    pass

def _noop_compile(f, toks, i):
    pass


# ---------------------------------------------------------------------------
# Compiler / system words
# ---------------------------------------------------------------------------

def _state(f):
    f.ds.push(1 if f.compiling else 0)

def _bracket(f):
    pass

def _compile_bracket(f, toks, i):
    f.compile_state.interpret_mode = True

def _square(f):
    pass

def _compile_square(f, toks, i):
    f.compile_state.interpret_mode = False

def _lit_tick(f):
    pass

def _compile_lit_tick(f, toks, i):
    # ['] NAME : push the entry address of NAME (for later EXECUTE)
    name = toks[i].value.upper()
    f.compile_state.advance_by = i + 1
    entry = f.find(name)
    if entry is None or entry.body is None:
        raise RuntimeError(f"?NAME? {name}")
    _exec_map[id(entry)] = entry
    f.emit_cell("lit", id(entry))

def _compile_compile(f, toks, i):
    name = toks[i].value.upper()
    f.compile_state.advance_by = i + 1
    f.compile_word_late(name)

def _literal(f):
    pass

def _compile_literal(f, toks, i):
    nb = f.compile_state.numbuf
    if not nb:
        raise RuntimeError("LITERAL without operand")
    value = nb.pop()
    f.emit_cell("lit", to_cell(value))

def _postpone(f):
    pass

def _compile_postpone(f, toks, i):
    name = toks[i].value.upper()
    f.compile_state.advance_by = i + 1
    entry = f.find(name)
    if entry is None:
        raise RuntimeError(f"?NAME? {name}")
    if entry.body is not None:
        f.emit_cell("sec", name)
    elif entry.primary and entry.primary.compile is not None:
        entry.primary.compile(f, toks, i)

def _immediate(f):
    if f.last_word is None:
        raise RuntimeError("IMMEDIATE without a definition")
    f.last_word.immediate = True

def _execute(f):
    # ( xt -- ) execute the secondary whose entry address is on the stack
    xt = f.ds.pop()
    entry = _exec_map.get(xt)
    if entry is None or entry.body is None:
        raise RuntimeError("EXECUTE of non-secondary")
    f.execute_body(list(entry.body))

_exec_map = {}

def _execute_xt(f, xt):  # kept for compatibility; unused
    entry = _exec_map.get(xt)
    if entry is None or entry.body is None:
        raise RuntimeError("EXECUTE of non-secondary")
    f.execute_body(list(entry.body))

def _abort(f):
    f.ds.reset()
    f.rs.reset()
    f.loops.clear()
    f.control.clear()
    f.leave.clear()

def _abort_quote(f):
    a = f.ds.pop()
    f.emit(_read_string_at(f, a))

def _compile_abort_quote(f, toks, i):
    name = toks[i].value if i < len(toks) else ""
    f.compile_state.advance_by = i + 1
    # compile a string push + abort at runtime
    addr = f._make_static_string(name)
    f.emit_cell("lit", addr)
    f.emit_prim("STR@")
    f.emit_prim("ABORT")

def _question(f):
    # ( -- ) read a line and interpret it (used by web/CLI "?")
    line = input("? ")
    f.interpret(line)

def _word(f):
    # ( a# -- a# word ) read next word from input buffer at a#
    a = f.ds.pop()
    n = f.mem.cget(a)
    # find separator
    sep = chr(f.mem.cget(a)) if n > 0 else " "
    # simplistic: read from TIB
    tib = f.uv["TIB"]
    tin = f.mem.cell_get(f.uv[">IN"])
    out = f._make_static_string("")
    j = tin
    while j < n and chr(f.mem.cget(tib + j)) == sep:
        j += 1
    start = j
    while j < n and chr(f.mem.cget(tib + j)) != sep:
        j += 1
    word = tib[start:j]
    addr = f._make_static_string(word)
    f.ds.push(addr)
    f.mem.cell_set(f.uv[">IN"], j)

def _interpret(f):
    a = f.ds.pop()
    text = _read_string_at(f, a)
    f.interpret(text)

def _source(f):
    # ( -- a# ) return source buffer info
    f.ds.push(f.uv["TIB"])
    f.ds.push(256)

def _alias(f):
    pass

def _compile_alias(f, toks, i):
    # NAME1 ALIAS NAME2 : compile a call to NAME2 (resolved at runtime)
    name = toks[i].value.upper()
    f.compile_state.advance_by = i + 1
    entry = f.find(name)
    if entry is None:
        raise RuntimeError(f"?NAME? {name}")
    entry.primary = None
    # make alias resolve to target at runtime by storing target name
    entry._alias_target = toks[i].value.upper()

def _variable(f):
    pass

def _compile_variable(f, toks, i):
    if f.compiling:
        addr = f.mem.alloc_cell()
        f.current.body.append(["lit", addr])
        return
    name = toks[i].value.upper()
    f.compile_state.advance_by = i + 1
    addr = f.mem.alloc_cell()
    e = f.new_secondary(name)
    e.body = [["lit", addr], ["exit", 0, -1]]

def _constant(f):
    pass

def _compile_constant(f, toks, i):
    nb = f.compile_state.numbuf
    if not nb:
        raise RuntimeError("CONSTANT without value")
    value = nb.pop()
    if f.compiling:
        f.current.body.append(["lit", to_cell(value)])
        return
    name = toks[i].value.upper()
    f.compile_state.advance_by = i + 1
    e = f.new_secondary(name)
    e.body = [["lit", to_cell(value)], ["exit", 0, -1]]

def _create(f):
    pass

def _compile_create(f, toks, i):
    if f.compiling:
        addr = f.mem.alloc_cell()
        f.current.body.append(["lit", addr])
        f.last_word = f.current
        return
    name = toks[i].value.upper()
    f.compile_state.advance_by = i + 1
    addr = f.mem.alloc_cell()
    e = f.new_secondary(name)
    e.body = [["lit", addr], ["exit", 0, -1]]
    f.last_word = e

def _allot(f):
    pass

def _compile_allot(f, toks, i):
    nb = f.compile_state.numbuf
    if not nb:
        raise RuntimeError("ALLOT without size")
    n = nb.pop()
    # advance the dictionary allocator to reserve space
    for _ in range(n):
        f.mem.alloc_cell()

def _compile_does(f, toks, i):
    word = f.last_word
    if word is None or word.body is None:
        raise RuntimeError("DOES> without a defining word")
    # start compiling a temporary body; the tokens after DOES> up to ';' fill it
    f.current = type(word)(f"___doesbody_{id(word)}")
    f.current.body = []
    f.compiling = True
    f._pending_does = word


# ---------------------------------------------------------------------------
# Control structures (runtime scanning)
# ---------------------------------------------------------------------------

def _find_else(f, cells, i, t):
    """Return the index of the ELSE matching the IF at ``i`` (before ``t``)."""
    depth = 0
    j = i + 1
    n = len(cells)
    while j < t and j < n:
        c = cells[j]
        if c[0] != "prim":
            j += 1
            continue
        v = c[1]
        if v in f.OPENERS:
            depth += 1
        elif v == "ELSE":
            if depth == 0:
                return j
        elif v in f.CLOSERS:
            depth -= 1
        j += 1
    return None


def _find_first(f, cells, i, names):
    j = i + 1
    n = len(cells)
    while j < n:
        c = cells[j]
        if c[0] == "prim" and c[1] in names:
            return j
        j += 1
    return None


def _exec_if(f, cells, i):
    flag = f.ds.pop()
    t = f.find_match(cells, i, ("THEN",))
    f.struct_stack.append("if")
    e = _find_else(f, cells, i, t)
    if flag != 0:
        # true path: run then-block up to ELSE (if any), skip else-block
        end = e if e is not None else t
        f.exec_tokens(cells, i + 1, end)
    else:
        # false path: skip then-block, run else-block if present
        if e is not None:
            f.exec_tokens(cells, e + 1, t)
    return t + 1


def _exec_else(f, cells, i):
    t = f.find_match(cells, i, ("THEN",))
    return t + 1


def _exec_then(f, cells, i):
    if not f.struct_stack:
        raise RuntimeError("THEN without IF/BEGIN")
    typ = f.struct_stack.pop()
    if typ == "begin":
        bidx = f.begin_stack.pop()
        if f.while_stack:
            flag = f.while_stack.pop()
            if flag == 0:
                return i + 1
        return bidx
    return i + 1


def _exec_begin(f, cells, i):
    f.begin_stack.append(i)
    f.struct_stack.append("begin")
    return i + 1


def _exec_while(f, cells, i):
    flag = f.ds.pop()
    f.while_stack.append(flag)
    return i + 1


def _exec_again(f, cells, i):
    if not f.begin_stack:
        raise RuntimeError("AGAIN without BEGIN")
    bidx = f.begin_stack.pop()
    if f.struct_stack and f.struct_stack[-1] == "begin":
        f.struct_stack.pop()
    return bidx


def _exec_until(f, cells, i):
    flag = f.ds.pop()
    if not f.begin_stack:
        raise RuntimeError("UNTIL without BEGIN")
    bidx = f.begin_stack.pop()
    if f.struct_stack and f.struct_stack[-1] == "begin":
        f.struct_stack.pop()
    if flag != 0:
        return i + 1
    return bidx


def _exec_repeat(f, cells, i):
    if not f.begin_stack:
        raise RuntimeError("REPEAT without BEGIN")
    bidx = f.begin_stack.pop()
    if f.struct_stack and f.struct_stack[-1] == "begin":
        f.struct_stack.pop()
    if f.while_stack:
        flag = f.while_stack.pop()
        if flag == 0:
            return i + 1
    return bidx


def _exec_do(f, cells, i):
    qdo = cells[i][1] == "?DO"
    nlim = f.ds.pop()
    n = f.ds.pop()
    L = f.find_match(cells, i, ("LOOP", "+LOOP"))
    if L is None or L >= len(cells):
        raise RuntimeError("DO without matching LOOP/+LOOP")
    # Determine the step source from the terminator cell.  A dynamic (+LOOP
    # without a compile-time constant) reads its step once from the data stack
    # when the loop is entered; that value then persists for the whole loop.
    term = cells[L]
    if term[0] == "ploop":
        step = term[1]            # constant step baked in at compile time
    elif term[1] == "+LOOP":
        step = f.ds.pop()         # dynamic step, read a single time
    else:                         # plain LOOP -> fixed step of +1
        step = 1
    f.loops.append([n, nlim, step])
    # ?DO: skip the whole body when the start already equals the limit.
    if qdo and n == nlim:
        f.loops.pop()
        return L + 1
    while True:
        cur = f.loops[-1]
        ivalue = cur[0]
        # Normal termination test based on the sign of the step.
        if step > 0 and ivalue >= nlim:
            f.loops.pop()
            return L + 1
        if step < 0 and ivalue <= nlim:
            f.loops.pop()
            return L + 1
        if step == 0 and ivalue == nlim:
            f.loops.pop()
            return L + 1
        f.exec_tokens(cells, i + 1, L)
        if f.loops and f.loops[-1] is not cur:
            continue   # inner loop left early (LEAVE / nested DO)
        cur[0] = ivalue + step


def _exec_loop(f, cells, i):
    return _exec_do(f, cells, i)


def _exec_plusloop(f, cells, i):
    nlim = f.ds.pop()
    n = f.ds.pop()
    L = f.find_match(cells, i, ("LOOP", "+LOOP"))
    f.loops.append([n, nlim])
    while True:
        cur = f.loops[-1]
        f.exec_tokens(cells, i + 1, L)
        if f.loops and f.loops[-1] is not cur:
            continue
        step = f.ds.pop()
        cur[0] += step
        nlim = cur[1]
        if step > 0:
            done = cur[0] >= nlim
        elif step < 0:
            done = cur[0] <= nlim
        else:
            done = False
        if not f.loops:
            break
        if done:
            f.loops.pop()
            return L + 1


def _exec_leave(f, cells, i):
    t = f.find_match(cells, i, ("LOOP", "+LOOP", "REPEAT", "UNTIL", "AGAIN", "ENDCASE"),
                     require_depth=False)
    if t is None:
        raise RuntimeError("LEAVE without loop/case")
    return t + 1


def _exec_case(f, cells, i):
    return i + 1


def _exec_of(f, cells, i):
    v = f.ds.pop()
    x = f.ds.peek()
    endof = _find_first(f, cells, i, ("ENDOF",))
    endcase = _find_first(f, cells, i, ("ENDCASE",))
    if endof is not None:
        if x == v:
            f.exec_tokens(cells, i + 1, endof)
            ec = endcase if endcase is not None else len(cells)
            return ec + 1
        return endof + 1
    else:
        # no ENDOF: body runs up to ENDCASE
        ec = endcase if endcase is not None else len(cells)
        if x == v:
            f.exec_tokens(cells, i + 1, ec)
            return ec + 1
        return ec + 1


def _exec_endcase(f, cells, i):
    return i + 1


# ---------------------------------------------------------------------------
# Arrays and structured definitions (extension)
# ---------------------------------------------------------------------------

def _arrays(f):
    pass

def _compile_arrays(f, toks, i):
    # ARRAYS n NAME : allocate a named array of n zeroed cells.
    nb = f.compile_state.numbuf
    if not nb:
        raise RuntimeError("ARRAYS without size")
    n = nb.pop()
    base = f.mem.alloc_cell()
    for k in range(n):
        f.mem.cell_set(base + k, 0)
    if f.compiling:
        # Inside a definition the base address is left on the data stack.
        f.current.body.append(["lit", base])
        return
    name = toks[i].value.upper() if i < len(toks) else None
    if name:
        f.compile_state.advance_by = i + 1
        entry = f.new_secondary(name)
        entry.body = [["lit", base], ["exit", 0, -1]]
    else:
        f.ds.push(base)

def _struct(f):
    pass

def _compile_struct(f, toks, i):
    nb = f.compile_state.numbuf
    if not nb:
        raise RuntimeError("STRUCT without size")
    n = nb.pop()
    f.compile_state.struct_size = getattr(f.compile_state, "struct_size", 0) + n

def _endstruct(f):
    pass

def _compile_endstruct(f, toks, i):
    pass

def _field(f):
    pass

def _compile_field(f, toks, i):
    name = toks[i].value.upper() if i < len(toks) else ""
    f.compile_state.advance_by = i + 1
    size = getattr(f.compile_state, "struct_size", 0)
    addr = f.mem.alloc_cell()
    f.compile_state.struct_size -= min(1, size)
    e = f.new_secondary(name)
    e.body = [["lit", addr], ["exit", 0, -1]]
