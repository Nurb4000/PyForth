"""Catalogue of FORTH primary (built-in) words for PyForth.

This module registers a fairly complete ANSI-FORTH core together with a set
of extensions (strings, arrays, extended math and I/O).  It is installed
by :func:`register_words` onto a :class:`forth.machine.Forth` instance.
"""

from __future__ import annotations

import math
import sys

from .machine import Primary, to_cell, CELL_MASK, ForthError


class _LeaveSignal(Exception):
    """Internal exception used to unwind a DO...LOOP when LEAVE executes."""


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
    if base < 2:
        raise RuntimeError("BASE too small")
    if base > 36:
        raise RuntimeError("BASE too large")
    neg = n < 0
    if neg:
        n = -n
    if n == 0:
        s = "0"
    else:
        out = []
        while n > 0:
            out.insert(0, _DIGITS[n % base])
            n //= base
        s = "".join(out)
    return "-" + s if neg else s


_DIGITS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _pad(f):
    return f.uv["PAD"]


def _pad_word(f):
    # ( -- addr ) address of the scratch area used by pictured output
    f.ds.push(f.uv["PAD"])


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
    add("?DUP", P(_q_dup))
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
    add("2ROT", P(_two_rot))
    add("ROLL", P(_roll))

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
    add("2>R", P(_two_gt_r))
    add("2R>", P(_two_r_from))
    add("2R@", P(_two_r_peek))
    add("RDROP", P(_r_drop))

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

    def _slash_mod(f):
        # ( n1 n2 -- rem quot )  same convention as '/' and MOD
        b = f.ds.pop(); a = f.ds.pop()
        if b == 0: raise RuntimeError("division by zero")
        q = abs(a) // abs(b)
        if (a < 0) != (b < 0):
            q = -q
        r = a - q * b
        f.ds.push(to_cell(r))
        f.ds.push(to_cell(q))

    def _star_slash_mod(f):
        # ( n1 n2 n3 -- rem quot )  n1 * n2 / n3, product kept full-size
        n3 = f.ds.pop(); n2 = f.ds.pop(); n1 = f.ds.pop()
        if n3 == 0: raise RuntimeError("division by zero")
        prod = n1 * n2
        q = abs(prod) // abs(n3)
        if (prod < 0) != (n3 < 0):
            q = -q
        f.ds.push(to_cell(prod - q * n3))
        f.ds.push(to_cell(q))

    def _star_slash(f):
        # ( n1 n2 n3 -- n4 )  n1 * n2 / n3 without intermediate overflow
        n3 = f.ds.pop(); n2 = f.ds.pop(); n1 = f.ds.pop()
        if n3 == 0: raise RuntimeError("division by zero")
        prod = n1 * n2
        q = abs(prod) // abs(n3)
        if (prod < 0) != (n3 < 0):
            q = -q
        f.ds.push(to_cell(q))
    add("+", P(_add))
    add("-", P(_sub))
    add("*", P(_mul))
    add("/", P(_div))
    add("MOD", P(_mod))
    add("/MOD", P(_slash_mod))
    add("*/MOD", P(_star_slash_mod))
    add("*/", P(_star_slash))
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
    # FM/ and UM/M (signed/unsigned divide) -- leave quotient and remainder.
    add("FM/", P(_fmdiv))
    add("FM/DP", P(_fmdiv))
    add("UM/M", P(_umdp))
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
    add("WITHIN", P(_within))

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
    add("2@", P(_at_two))
    add("2!", P(_bang_two))
    add("@+", P(_atplus))
    add("@-", P(_atminus))
    add("C@", P(_c_at))
    add("C!", P(_c_bang))
    add("CHAIN", P(_chain))
    add("HERE", P(_here))
    add(",", P(_comma))
    add("C,", P(_c_comma))
    add("CMOVE", P(_cmove))
    add("CMOVE>", P(_cmove_up))
    add("MOVE", P(_move))
    add("/STRING", P(_slash_string))
    add("FILL", P(_fill))
    add("ERASE", P(_erase))
    add("BLANK", P(_blank))
    add("BOUNDS", P(_bounds))
    add("CELLS", P(_cells))
    add("CELL+", P(_cell_plus))
    add("CHARS", P(_cells))

    # =======================================================================
    # Data stack info words
    # =======================================================================
    add("SP@", P(lambda f: f.ds.push(f.sp_addr)))
    add("SP!", P(_sp_store))
    add("RS@", P(lambda f: f.ds.push(f.rs_addr)))
    add("BASE", P(lambda f: f.ds.push(f.uv["BASE"])))
    add(">IN", P(lambda f: f.ds.push(f.uv[">IN"])))
    add("SPAN", P(lambda f: f.ds.push(f.uv["SPAN"])))
    add("TIB", P(lambda f: f.ds.push(f.uv["TIB"])))
    add("PAD", P(_pad_word))

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
    add("U.", P(_u_dot))
    add("?.", P(_qdot))
    add("S.", P(_s_dot))
    add(".R", P(_dot_r))
    add("U.R", P(_u_dot_r))
    add("EMIT", P(_emit))
    add("TYPE", P(_type))
    add("SPACE", P(lambda f: f.emit(" ")))
    add("BL", P(lambda f: f.ds.push(ord(" "))))
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
    add("[COMPILE]", P(_noop_execute, compile=_compile_compile), immediate=True)
    add("LITERAL", P(_literal, compile=_compile_literal), immediate=True)
    add("POSTPONE", P(_postpone, compile=_compile_postpone), immediate=True)
    add("IMMEDIATE", P(_immediate), immediate=True)
    add("EXIT", P(_exit, compile=_compile_exit), immediate=True)
    add("RECURSE", P(_recurse, compile=_compile_recurse), immediate=True)
    add("EXECUTE", P(_execute))
    add("ABORT", P(_abort))
    add("ABORT\"", P(_abort_quote, compile=_compile_abort_quote))
    add("?", P(_question))
    add("WORD", P(_word))
    add("INTERPRET", P(_interpret))
    add("INCLUDE", P(_include))
    add("WORDS", P(_words))
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
    add("UNDO", P(execute=_noop_control, is_control=True))
    add("LEAVE", P(execute=_exec_leave, is_control=True))
    add("CASE", P(execute=_exec_case, is_control=True))
    add("OF", P(execute=_exec_of, is_control=True))
    add("ENDOF", P(execute=_noop_control, is_control=True))
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
    c = f.ds.pop(); b = f.ds.pop(); a = f.ds.pop()
    f.ds.push(c); f.ds.push(a); f.ds.push(b)

def _over(f):
    b = f.ds.pop(); a = f.ds.pop()
    f.ds.push(a); f.ds.push(b); f.ds.push(a)

def _tuck(f):
    b = f.ds.pop(); a = f.ds.pop()
    f.ds.push(b); f.ds.push(a); f.ds.push(b)

def _nip(f):
    b = f.ds.pop()
    f.ds.pop()
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

def _depth(f):
    f.ds.push(f.ds.depth())

def _dot_s(f):
    # ( -- )  Dump the data stack, top first.
    items = [str(v) for v in reversed(f.ds.data)]
    f.emit(" ".join(items) if items else "empty")

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

def _two_rot(f):
    # ( x1 x2 x3 x4 x5 x6 -- x3 x4 x5 x6 x1 x2 )
    if f.ds.depth() < 6:
        raise ForthError("data stack underflow")
    x1 = f.ds.data[-6]
    x2 = f.ds.data[-5]
    del f.ds.data[-6:-4]
    f.ds.data.append(x1)
    f.ds.data.append(x2)

def _roll(f):
    # ( xu ... x0 u -- xu-1 ... x0 xu )  move the u-th item to the top
    u = f.ds.pop()
    if u < 0:
        raise RuntimeError("ROLL: negative depth")
    if u == 0:
        f.ds.push(f.ds.peek())
        return
    if u >= f.ds.depth():
        raise ForthError("data stack underflow")
    item = f.ds.data[-u - 1]
    del f.ds.data[-u - 1]
    f.ds.data.append(item)

def _gt_r(f):
    v = f.ds.pop()
    f.rs.push(v)

def _r_from(f):
    f.ds.push(f.rs.pop())

def _r_peek(f):
    f.ds.push(f.rs.peek())

def _two_gt_r(f):
    # ( x1 x2 -- ) ( R: -- x1 x2 )
    x2 = f.ds.pop(); x1 = f.ds.pop()
    f.rs.push(x1)
    f.rs.push(x2)

def _two_r_from(f):
    # ( R: x1 x2 -- ) ( -- x1 x2 )
    x2 = f.rs.pop(); x1 = f.rs.pop()
    f.ds.push(x1)
    f.ds.push(x2)

def _two_r_peek(f):
    # ( R: x1 x2 -- R: x1 x2 ) ( -- x1 x2 )  2R@ - copy without removing
    x1 = f.rs.peek(1)
    x2 = f.rs.peek(0)
    f.ds.push(x1)
    f.ds.push(x2)

def _r_drop(f):
    # drop the top item from the return stack
    f.rs.pop()

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
    # like '/': result truncated toward zero
    q = abs(a) // abs(b)
    if (a < 0) != (b < 0):
        q = -q
    f.ds.push(to_cell(q))

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

def _umdiv(f):
    # ( ud u -- r q ) unsigned double-length divide
    u = f.ds.pop(); ud_lo = f.ds.pop(); ud_hi = f.ds.pop()
    if u == 0: raise RuntimeError("division by zero")
    ud = ud_hi * (2 ** 32) + ud_lo
    q = ud // u
    r = ud % u
    f.ds.push(to_cell(r)); f.ds.push(to_cell(q))

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
    # round toward negative infinity (Python's '//' is floor division)
    f.ds.push(to_cell(a // b))

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
    try:
        f.ds.push(to_cell(int(a ** b)))
    except (ValueError, OverflowError, ZeroDivisionError):
        raise RuntimeError("POW out of range") from None

def _exp(f):
    a = f.ds.pop()
    try:
        f.ds.push(to_cell(int(math.exp(a))))
    except OverflowError:
        raise RuntimeError("EXP out of range") from None

def _ln(f):
    a = f.ds.pop()
    if a <= 0:
        raise RuntimeError("LN of non-positive")
    f.ds.push(to_cell(int(math.log(a))))

def _log(f):
    a = f.ds.pop()
    if a <= 0:
        raise RuntimeError("LOG of non-positive")
    f.ds.push(to_cell(int(math.log10(a))))

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

def _within(f):
    # ( x lo hi -- flag )  true if lo <= x < hi
    hi = f.ds.pop(); lo = f.ds.pop(); x = f.ds.pop()
    f.ds.push(to_cell(-1 if lo <= x < hi else 0))

def _neq0(f):
    a = f.ds.pop(); f.ds.push(to_cell(-1 if a != 0 else 0))

def _one_lt(f):
    # ( n -- flag ) true if n is less than one
    a = f.ds.pop(); f.ds.push(to_cell(-1 if a < 1 else 0))

def _two_gt(f):
    # ( n -- flag ) true if n is greater than two
    a = f.ds.pop(); f.ds.push(to_cell(-1 if a > 2 else 0))

def _lt_dup(f):
    # ( n -- n n ) duplicate n only if it is non-zero
    a = f.ds.pop()
    if a != 0:
        f.ds.push(a); f.ds.push(a)
    else:
        f.ds.push(a)

def _q_dup(f):
    # ( n -- n [n] ) duplicate only if non-zero
    a = f.ds.peek()
    if a != 0:
        f.ds.push(a)


# ---------------------------------------------------------------------------
# Bitwise implementations
# ---------------------------------------------------------------------------

def _xor(f):
    b = f.ds.pop(); a = f.ds.pop(); f.ds.push(to_cell(a ^ b))

def _lshift(f):
    b = f.ds.pop(); a = f.ds.pop()
    if b < 0:
        raise RuntimeError("LSHIFT by negative count")
    f.ds.push(to_cell(a << b))

def _rshift(f):
    b = f.ds.pop(); a = f.ds.pop()
    if b < 0:
        raise RuntimeError("RSHIFT by negative count")
    f.ds.push(to_cell(a >> b))

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
    a = f.ds.pop()
    v = f.mem.cell_get(a)
    f.mem.cell_set(a, v + 1)
    f.ds.push(a)
    f.ds.push(v)

def _atminus(f):
    a = f.ds.pop()
    v = f.mem.cell_get(a); f.mem.cell_set(a, v - 1); f.ds.push(v)

def _c_at(f):
    a = f.ds.pop(); f.ds.push(f.mem.cget(a))

def _c_bang(f):
    a = f.ds.pop(); v = f.ds.pop(); f.mem.cset(a, v)

def _chain(f):
    # ( a1 a2 -- ) copy string from a2 into a1 (length byte + all body bytes)
    b = f.ds.pop(); a = f.ds.pop()
    n = f.mem.cget(b)
    for j in range(n + 1):
        f.mem.cset(a + j, f.mem.cget(b + j))


def _at_two(f):
    # ( a-addr -- x1 x2 ) load two consecutive cells (lower address first)
    a = f.ds.pop()
    f.ds.push(f.mem.cell_get(a))
    f.ds.push(f.mem.cell_get(a + 1))


def _bang_two(f):
    # ( x1 x2 a-addr -- ) store two consecutive cells (x1 at a-addr)
    a = f.ds.pop()
    x2 = f.ds.pop(); x1 = f.ds.pop()
    f.mem.cell_set(a, x1)
    f.mem.cell_set(a + 1, x2)


def _here(f):
    # ( -- addr ) address of the next free data-space cell
    f.ds.push(f.mem.next_cell_addr)


def _comma(f):
    # ( x -- ) store x at HERE and advance HERE by one cell
    x = f.ds.pop()
    a = f.mem.next_cell_addr
    f.mem.cell_set(a, x)
    f.mem.next_cell_addr += 1


def _c_comma(f):
    # ( char -- ) store char at HERE and advance HERE by one cell
    x = f.ds.pop()
    a = f.mem.next_cell_addr
    f.mem.cset(a, x)
    f.mem.next_cell_addr += 1


def _cmove(f):
    # ( src dst u -- ) copy u bytes from src to dst (forward)
    u = f.ds.pop(); dst = f.ds.pop(); src = f.ds.pop()
    cget = f.mem.cget; cset = f.mem.cset
    for j in range(u):
        cset(dst + j, cget(src + j))


def _cmove_up(f):
    # ( src dst u -- ) copy u bytes from src to dst (backward, overlap-safe)
    u = f.ds.pop(); dst = f.ds.pop(); src = f.ds.pop()
    cget = f.mem.cget; cset = f.mem.cset
    for j in range(u - 1, -1, -1):
        cset(dst + j, cget(src + j))


def _move(f):
    # ( addr1 addr2 u -- ) copy u cells; cells and bytes share one address
    # space here, so forward/backward handling matters for overlap.
    u = f.ds.pop(); dst = f.ds.pop(); src = f.ds.pop()
    cget = f.mem.cget; cset = f.mem.cset
    if dst <= src:
        for j in range(u):
            cset(dst + j, cget(src + j))
    else:
        for j in range(u - 1, -1, -1):
            cset(dst + j, cget(src + j))


def _slash_string(f):
    # ( addr u n -- addr+n u-n ) offset a described string by n characters
    n = f.ds.pop(); u = f.ds.pop(); a = f.ds.pop()
    f.ds.push(a + n)
    f.ds.push(u - n)


def _fill(f):
    # ( addr u char -- ) store char in u bytes starting at addr
    ch = f.ds.pop() & 0xFF
    u = f.ds.pop(); a = f.ds.pop()
    for j in range(u):
        f.mem.cset(a + j, ch)


def _erase(f):
    # ( addr u -- ) store zeros in u bytes starting at addr
    u = f.ds.pop(); a = f.ds.pop()
    for j in range(u):
        f.mem.cset(a + j, 0)


def _blank(f):
    # ( addr u -- ) store spaces in u bytes starting at addr
    u = f.ds.pop(); a = f.ds.pop()
    for j in range(u):
        f.mem.cset(a + j, 32)


def _bounds(f):
    # ( addr u -- addr+u addr )
    u = f.ds.pop(); a = f.ds.pop()
    f.ds.push(a + u)
    f.ds.push(a)


def _cells(f):
    # ( n -- n ) a cell occupies one address in this implementation
    pass


def _cell_plus(f):
    # ( a-addr -- a-addr+1 )
    f.ds.push(f.ds.pop() + 1)


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
    # ( n -- 0 ) convert n to its textual form in the current base and store it
    # in PAD as a counted string; the pushed zero acts as the "done" marker.
    n = f.ds.pop()
    base = f.mem.cell_get(f.uv["BASE"])
    _write_string_to_mem(f, _number_to_str(f, n, base), _pad(f))
    f.ds.push(0)

def _hashs(f):
    # ( n -- 0 ) convert the full value (not just one digit) into PAD.
    return _hash(f)

def _hashgt(f):
    # ( -- a# ) hand back the address of the converted string in PAD.
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

def _numberq(f):
    # ( a# -- n flag ) convert a counted string to a number in the current base.
    a = f.ds.pop()
    text = _read_string_at(f, a)
    val = f.try_number(text)
    if val is None:
        f.ds.push(0)
        f.ds.push(0)
    else:
        f.ds.push(val)
        f.ds.push(-1)

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

def _u_dot(f):
    n = abs(f.ds.pop())
    base = f.mem.cell_get(f.uv["BASE"])
    f.emit(" " + _number_to_str(f, n, base) + " ")

def _dot_r(f):
    # ( n width -- ) right-justified signed display in field of 'width'
    width = f.ds.pop(); n = f.ds.pop()
    base = f.mem.cell_get(f.uv["BASE"])
    s = _number_to_str(f, n, base)
    f.emit(" " * max(0, width - len(s)) + s)

def _u_dot_r(f):
    # ( u width -- ) right-justified unsigned display in field of 'width'
    width = f.ds.pop(); n = f.ds.pop()
    base = f.mem.cell_get(f.uv["BASE"])
    s = _number_to_str(f, abs(n), base)
    f.emit(" " * max(0, width - len(s)) + s)

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
    n = f.ds.pop(); a = f.ds.pop()
    count = 0
    while count < n:
        c = f.get_key()
        if c < 0:
            break
        if c in (13, 10):
            break
        f.mem.cset(a + 1 + count, c & 0xFF)
        count += 1
    f.mem.cset(a, count)
    f.mem.cell_set(f.uv["SPAN"], count)
    f.ds.push(a)
    f.ds.push(count)

def _accept(f):
    n = f.ds.pop(); a = f.ds.pop()
    count = 0
    while count < n:
        c = f.get_key()
        if c < 0 or c in (13, 10):
            break
        f.mem.cset(a + count, c & 0xFF)
        count += 1
    f.mem.cell_set(f.uv["SPAN"], count)
    f.ds.push(count)

def _readline(f):
    n = f.ds.pop(); a = f.ds.pop()
    count = 0
    while count < n:
        c = f.get_key()
        if c < 0 or c in (13, 10):
            break
        f.mem.cset(a + 1 + count, c & 0xFF)
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
    # Kept for compatibility; ." strings are normally handled by the
    # tokenizer (they arrive as "dotstr" tokens), so this path is rarely hit.
    addr = f._make_static_string(toks[i].value if i < len(toks) else "")
    f.emit_cell("lit", addr)
    f.emit_prim("S.")

def _str_at(f):
    # ( a# -- a# ) return pointer to start of string body (skip length byte)
    a = f.ds.pop()
    f.ds.push(a)

def _str_bang(f):
    # ( a# s# -- ) copy counted string s# into a# (length byte + body)
    dst = f.ds.pop(); src = f.ds.pop()
    n = f.mem.cget(src)
    for j in range(n + 1):
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

def _noop_control(f, cells, i):
    return i + 1


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
    name = toks[i].value.upper() if i < len(toks) else ""
    f.compile_state.advance_by = i + 1
    entry = f.find(name)
    if entry is None:
        raise RuntimeError(f"?NAME? {name}")
    f.exec_map[id(entry)] = entry
    f.emit_cell("lit", id(entry))

def _compile_compile(f, toks, i):
    # [COMPILE] NAME : compile NAME into the definition, even if it is
    # immediate.  Control words stay runtime-scanned prim cells.
    name = toks[i].value.upper() if i < len(toks) else ""
    f.compile_state.advance_by = i + 1
    entry = f.find(name)
    if entry is None:
        raise RuntimeError(f"?NAME? {name}")
    if entry.body is not None:
        f.emit_cell("sec", name)
    else:
        f.emit_cell("prim", name)

def _literal(f):
    pass

def _compile_literal(f, toks, i):
    nb = f.compile_state.numbuf
    if nb:
        value = nb.pop()
    else:
        value = f.ds.pop()
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
    else:
        f.emit_cell("prim", name)

def _immediate(f):
    if f.last_word is None:
        raise RuntimeError("IMMEDIATE without a definition")
    f.last_word.immediate = True

def _exit(f):
    raise ForthError("EXIT outside a definition")

def _compile_exit(f, toks, i):
    # EXIT : end the current word early.  The cell carries the 'exitnow' tag
    # (rather than the ';' terminator's 'exit') so it unwinds even when it
    # appears inside an IF / DO region.  Flush pending numbers first so the
    # stack values keep their place.
    dest = f.current.body if f.current is not None else None
    if dest is None:
        raise ForthError("EXIT outside a definition")
    f._flush(dest)
    dest.append(["exitnow", 0, -1])

def _recurse(f):
    raise ForthError("RECURSE outside a definition")

def _compile_recurse(f, toks, i):
    # RECURSE : call the word that is currently being compiled
    cur = f.current
    if cur is None or cur.body is None:
        raise ForthError("RECURSE outside a definition")
    f._flush(cur.body)
    cur.body.append(["sec", cur.name])

def _execute(f):
    # ( xt -- ) execute the word whose entry address is on the stack
    xt = f.ds.pop()
    entry = f.exec_map.get(xt)
    if entry is None:
        raise RuntimeError("EXECUTE of unknown xt")
    if entry.body is not None:
        f.execute_body(list(entry.body))
    elif entry.primary is not None:
        entry.primary.execute(f)
    else:
        raise RuntimeError("EXECUTE of non-executable")

def _abort(f):
    f.abort()
    raise ForthError("ABORT")

def _abort_quote(f):
    a = f.ds.pop()
    msg = _read_string_at(f, a)
    f.abort()
    raise ForthError(msg)

def _compile_abort_quote(f, toks, i):
    name = toks[i].value if i < len(toks) else ""
    f.compile_state.advance_by = i + 1
    # compile a string push + abort at runtime
    addr = f._make_static_string(name)
    f.emit_cell("lit", addr)
    f.emit_prim("ABORT\"")

def _question(f):
    # ( -- ) read a line and interpret it (used by web/CLI "?").
    # Prefer the machine's own (non-blocking) input buffer so a browser
    # session never blocks on stdin; fall back to a real terminal prompt
    # only when running interactively.
    line = None
    if f.key_available():
        chars = []
        while f.key_available():
            c = f.get_key()
            if c in (13, 10):
                break
            chars.append(chr(c))
        line = "".join(chars)
    elif sys.stdin.isatty():
        try:
            line = input("? ")
        except (EOFError, OSError):
            line = None
    if line is None:
        raise ForthError("? no input")
    f.interpret(line)

def _word(f):
    # ( char -- c-addr ) parse the next whitespace-free token from the TIB,
    # skipping leading occurrences of char, and store it in PAD as a counted
    # string.  >IN is advanced past the terminating delimiter.
    delim = chr(f.ds.pop() & 0xFF)
    tib = f.uv["TIB"]
    n = f.mem.cell_get(f.uv["TLEN"])
    tin = f.mem.cell_get(f.uv[">IN"])
    j = tin
    while j < n and chr(f.mem.cget(tib + j)) == delim:
        j += 1
    start = j
    while j < n and chr(f.mem.cget(tib + j)) != delim:
        j += 1
    word = "".join(chr(f.mem.cget(tib + k)) for k in range(start, j))
    # the terminating delimiter is consumed; if we hit the end of the buffer
    # the parsed token ends there too.
    if j < n:
        j += 1
    _write_string_to_mem(f, word, f.uv["PAD"])
    f.ds.push(f.uv["PAD"])
    f.mem.cell_set(f.uv[">IN"], j)

def _interpret(f):
    a = f.ds.pop()
    text = _read_string_at(f, a)
    f.interpret(text)

def _source(f):
    # ( -- c-addr u ) address and length of the current input buffer (TIB)
    f.ds.push(f.uv["TIB"])
    f.ds.push(f.mem.cell_get(f.uv["TLEN"]))


def _words(f):
    # ( -- ) list the dictionary, wrapped at ~80 columns
    names = sorted(f.dict.keys())
    col = 0
    for name in names:
        if col and col + 1 + len(name) > 80:
            f.emit("\n")
            col = 0
        if col:
            f.emit(" ")
            col += 1
        f.emit(name)
        col += len(name)


def _include(f):
    raise RuntimeError("INCLUDE must be followed by a filename")

def _alias(f):
    pass

def _compile_alias(f, toks, i):
    # NAME1 ALIAS NAME2 : make NAME2 behave like NAME1.
    # The defining word sits between the target (NAME1) and the new name.
    if i < 2 or i >= len(toks):
        raise RuntimeError("ALIAS without target and name")
    target = toks[i - 2].value.upper()
    name = toks[i].value.upper()
    entry = f.find(target)
    if entry is None:
        raise RuntimeError(f"?NAME? {target}")
    f.compile_state.advance_by = i + 1
    if f.compiling:
        # Inside a definition: emit a call to the target.
        f._flush(f.current.body)
        if entry.body is not None:
            f.current.body.append(["sec", target])
        else:
            f.current.body.append(["prim", target])
        return
    alias = f.new_secondary(name)
    if entry.body is not None:
        alias.body = [["sec", target], ["exit", 0, -1]]
    else:
        alias.body = [["prim", target], ["exit", 0, -1]]

def _next_name(f, toks, i, word):
    """Return the word-name token at ``i`` or raise a clean error."""
    if i >= len(toks) or toks[i].kind != "word":
        raise ForthError(f"{word} without a word name")
    return toks[i].value.upper()


def _variable(f):
    pass

def _compile_variable(f, toks, i):
    if f.compiling:
        addr = f.mem.alloc_cell()
        f.current.body.append(["lit", addr])
        return
    name = _next_name(f, toks, i, "VARIABLE")
    f.compile_state.advance_by = i + 1
    addr = f.mem.alloc_cell()
    e = f.new_secondary(name)
    e.body = [["lit", addr], ["exit", 0, -1]]

def _constant(f):
    pass

def _compile_constant(f, toks, i):
    nb = f.compile_state.numbuf
    if not nb:
        raise ForthError("CONSTANT without value")
    value = nb.pop()
    if f.compiling:
        f.current.body.append(["lit", to_cell(value)])
        return
    name = _next_name(f, toks, i, "CONSTANT")
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
    name = _next_name(f, toks, i, "CREATE")
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
        if c[0] == "ploop":
            # Constant-step +LOOP acts as a "+LOOP" closer here too.
            depth -= 1
            j += 1
            continue
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
    if t is None:
        raise ForthError("IF without matching THEN")
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
    if t is None:
        raise ForthError("ELSE without matching THEN")
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
        try:
            f.exec_tokens(cells, i + 1, L)
        except _LeaveSignal:
            # LEAVE popped this loop's entry already; unwind to just past
            # the terminator.
            return L + 1
        if f.loops and f.loops[-1] is not cur:
            continue   # inner loop left early (nested DO)
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
        try:
            f.exec_tokens(cells, i + 1, L)
        except _LeaveSignal:
            return L + 1
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
    if f.loops:
        # Only a DO...LOOP is abandoned via the exception (it owns the top of
        # the loop stack).  A BEGIN...loop is left by merely skipping past its
        # terminator, which needs no stack cleanup.
        term = cells[t]
        if term[0] == "ploop" or term[1] in ("LOOP", "+LOOP"):
            f.loops.pop()
            raise _LeaveSignal(t + 1)
    return t + 1


def _exec_case(f, cells, i):
    # record where the CASE selector sits so the matching OF (or ENDCASE in
    # the fall-through path) can remove exactly it, not whatever the selected
    # branch happened to push above it.
    f.case_stack.append(len(f.ds.data) - 1)
    return i + 1


def _exec_of(f, cells, i):
    v = f.ds.pop()
    endof = _find_first(f, cells, i, ("ENDOF",))
    endcase = _find_first(f, cells, i, ("ENDCASE",))
    ec = endcase if endcase is not None else len(cells)
    sel_idx = f.case_stack[-1] if f.case_stack else None
    matched = sel_idx is not None and f.ds.data[sel_idx] == v
    if endof is not None:
        if matched:
            f.exec_tokens(cells, i + 1, endof)
            f.ds.data.pop(sel_idx)
            f.case_stack.pop()
            return ec + 1
        return endof + 1
    else:
        # no ENDOF: body runs up to ENDCASE
        if matched:
            f.exec_tokens(cells, i + 1, ec)
            f.ds.data.pop(sel_idx)
            f.case_stack.pop()
        return ec + 1


def _exec_endcase(f, cells, i):
    # Reached only when no OF matched; remove the leftover CASE selector.
    if f.case_stack:
        idx = f.case_stack.pop()
        del f.ds.data[idx]
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
    name = toks[i].value.upper() if i < len(toks) and toks[i].kind == "word" else None
    if name:
        f.compile_state.advance_by = i + 1
        entry = f.new_secondary(name)
        entry.body = [["lit", base], ["exit", 0, -1]]
    else:
        f.ds.push(base)

def _struct(f):
    pass

def _compile_struct(f, toks, i):
    # STRUCT n NAME : define NAME as the base cell of an n-cell block.
    nb = f.compile_state.numbuf
    if not nb:
        raise RuntimeError("STRUCT without size")
    n = nb.pop()
    name = toks[i].value.upper() if i < len(toks) and toks[i].kind == "word" else None
    if not name:
        raise RuntimeError("STRUCT without name")
    if n < 1:
        raise RuntimeError("STRUCT size must be at least 1")
    f.compile_state.advance_by = i + 1
    base = f.mem.alloc_cell()
    for _ in range(n - 1):
        f.mem.alloc_cell()          # reserve the remaining cells
    # Remember the active block so FIELD can attach addresses to it.
    f.compile_state.struct_info = [name, base, 0, n]
    entry = f.new_secondary(name)
    entry.body = [["lit", base], ["exit", 0, -1]]

def _endstruct(f):
    pass

def _compile_endstruct(f, toks, i):
    f.compile_state.struct_info = None

def _field(f):
    pass

def _compile_field(f, toks, i):
    # FIELD NAME : define NAME as the address of the next cell of the struct.
    name = toks[i].value.upper() if i < len(toks) and toks[i].kind == "word" else ""
    if not name:
        raise RuntimeError("FIELD without name")
    info = getattr(f.compile_state, "struct_info", None)
    if not info:
        raise RuntimeError("FIELD without STRUCT")
    _, base, offset, size = info
    if offset >= size:
        raise RuntimeError("FIELD beyond STRUCT size")
    f.compile_state.advance_by = i + 1
    addr = base + offset
    info[2] = offset + 1
    if f.compiling:
        f.current.body.append(["lit", addr])
        return
    entry = f.new_secondary(name)
    entry.body = [["lit", addr], ["exit", 0, -1]]
