"""Test suite for PyForth.

Uses only the standard library (``unittest``) so it can be run without any
third-party dependencies::

    python -m unittest discover -s tests
    python tests/test_forth.py

The suite covers the interpreter core, the command-line front-end and the
Flask web front-end.
"""

import io
import os
import sys
import unittest
from contextlib import redirect_stdout

# Make sure the package is importable regardless of the working directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from forth.machine import Forth, ForthError  # noqa: E402
from forth import cli  # noqa: E402


def run_code(code):
    """Run ``code`` in a fresh interpreter and return its captured output."""
    forth = Forth()
    forth.run(code)
    return forth.output_text()


class TestArithmetic(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(run_code("1 2 + ."), " 3 ")
        self.assertEqual(run_code("5 3 - ."), " 2 ")
        self.assertEqual(run_code("4 5 * ."), " 20 ")
        self.assertEqual(run_code("10 2 / ."), " 5 ")
        self.assertEqual(run_code("10 3 MOD ."), " 1 ")

    def test_truncated_division(self):
        # FORTH '/' truncates toward zero (unlike Python's floor division).
        self.assertEqual(run_code("7 2 / ."), " 3 ")
        self.assertEqual(run_code("-7 3 / ."), " -2 ")
        self.assertEqual(run_code("7 -3 / ."), " -2 ")
        self.assertEqual(run_code("-7 -3 / ."), " 2 ")

    def test_mod_sign_follows_dividend(self):
        self.assertEqual(run_code("-7 3 MOD ."), " -1 ")
        self.assertEqual(run_code("7 -3 MOD ."), " 1 ")

    def test_negate_abs(self):
        self.assertEqual(run_code("5 NEGATE ."), " -5 ")
        self.assertEqual(run_code("-5 ABS ."), " 5 ")


class TestStack(unittest.TestCase):
    def test_swap(self):
        self.assertEqual(run_code("1 2 SWAP . ."), " 1  2 ")

    def test_over(self):
        self.assertEqual(run_code("1 2 OVER . ."), " 1  2 ")

    def test_rot(self):
        # ROT: ( x1 x2 x3 -- x2 x3 x1 ); dots pop top-first -> 1 3 2
        self.assertEqual(run_code("1 2 3 ROT . . ."), " 1  3  2 ")

    def test_dup(self):
        self.assertEqual(run_code("3 DUP . ."), " 3  3 ")

    def test_depth(self):
        self.assertEqual(run_code("1 2 3 DEPTH ."), " 3 ")


class TestComparison(unittest.TestCase):
    def test_relations(self):
        self.assertEqual(run_code("3 5 < ."), " -1 ")
        self.assertEqual(run_code("5 3 > ."), " -1 ")
        self.assertEqual(run_code("5 5 = ."), " -1 ")
        self.assertEqual(run_code("3 4 <> ."), " -1 ")
        self.assertEqual(run_code("3 3 <> ."), " 0 ")

    def test_boolean_logic(self):
        self.assertEqual(run_code("0 NOT ."), " -1 ")
        self.assertEqual(run_code("3 1 AND ."), " 1 ")
        self.assertEqual(run_code("3 1 OR ."), " 3 ")


class TestBases(unittest.TestCase):
    def test_hex(self):
        # Base must be set before the literal is parsed.
        self.assertEqual(run_code("HEX FF . DECIMAL"), " FF ")

    def test_binary(self):
        self.assertEqual(run_code("2#1010 ."), " 10 ")

    def test_prefixed_numbers(self):
        self.assertEqual(run_code("16#1F ."), " 31 ")
        self.assertEqual(run_code("8#17 ."), " 15 ")


class TestControlStructures(unittest.TestCase):
    def test_do_loop(self):
        self.assertEqual(run_code("1 5 DO i . LOOP"), " 1  2  3  4 ")

    def test_plusloop_constant(self):
        self.assertEqual(
            run_code("1 10 DO i . 2 +LOOP"), " 1  3  5  7  9 "
        )

    def test_plusloop_dynamic(self):
        self.assertEqual(
            run_code("2 1 10 DO i . +LOOP"), " 1  3  5  7  9 "
        )

    def test_do_no_iterations(self):
        self.assertEqual(run_code("10 1 DO i . LOOP"), "")

    def test_if_true(self):
        self.assertEqual(
            run_code('1 IF S"yes" THEN COUNT TYPE'), "yes"
        )

    def test_if_false_skips(self):
        # The string in the skipped branch is not pushed, so COUNT has
        # nothing to consume and the interpreter raises (correct behaviour).
        with self.assertRaises(ForthError):
            run_code('0 IF S"no" THEN COUNT TYPE')


class TestDefinitions(unittest.TestCase):
    def test_simple_definition(self):
        self.assertEqual(run_code(": SQUARE 2 ** ; 7 SQUARE ."), " 49 ")

    def test_recursion_factorial(self):
        code = ": FACT ( n -- n! ) 1 SWAP 1+ 1 SWAP DO i * LOOP ;"
        self.assertEqual(run_code(code + " 6 FACT ."), " 720 ")

    def test_variable(self):
        self.assertEqual(run_code("VARIABLE X 100 X ! X @ ."), " 100 ")

    def test_constant(self):
        self.assertEqual(run_code("7 CONSTANT N N ."), " 7 ")


class TestStrings(unittest.TestCase):
    def test_count_type(self):
        self.assertEqual(run_code('S"hello" COUNT TYPE'), "hello")

    def test_len(self):
        self.assertEqual(run_code('S"python" LEN .'), " 6 ")

    def test_char(self):
        self.assertEqual(run_code("CHAR A ."), " 65 ")

    def test_string_equality(self):
        self.assertEqual(
            run_code('S"ab" S"ab" STRING= .'), " -1 "
        )
        self.assertEqual(
            run_code('S"ab" S"cd" STRING= .'), " 0 "
        )

    def test_string_ordering(self):
        self.assertEqual(
            run_code('S"abc" S"abd" STRING< .'), " -1 "
        )

    def test_escaped_quote(self):
        self.assertEqual(
            run_code(r'S" he said \"hi\"" COUNT TYPE'),
            ' he said "hi"',
        )


class TestArrays(unittest.TestCase):
    def test_array_store_read(self):
        code = "6 ARRAYS DATA 99 DATA 2 + ! DATA 2 + @ ."
        self.assertEqual(run_code(code), " 99 ")


class TestIOWords(unittest.TestCase):
    def test_emit(self):
        self.assertEqual(run_code("65 EMIT"), "A")

    def test_cr(self):
        self.assertEqual(run_code("1 CR"), "\n")


class TestErrorHandling(unittest.TestCase):
    def test_underflow_raises(self):
        with self.assertRaises(ForthError):
            run_code(". ")  # nothing on the stack for '.'

    def test_abort_resets_stack(self):
        # After an error the interpreter should still be usable.
        run_code("1 2 +")
        with self.assertRaises(ForthError):
            run_code(". . .")
        self.assertEqual(run_code("5 5 + ."), " 10 ")


class TestFixedWords(unittest.TestCase):
    """Regression tests for words that were previously broken."""

    def test_k_nested_loops(self):
        self.assertEqual(
            run_code("1 3 DO 1 3 DO 1 3 DO I K . LOOP LOOP LOOP"),
            " 1  1  1  1  2  2  2  2 ",
        )

    def test_stack_pointer_words(self):
        # SP! / SP@ / RS@ should not crash (used to raise AttributeError).
        self.assertEqual(run_code("0 SP! SP@ ."), " 0 ")
        self.assertEqual(run_code("RS@ ."), " 0 ")

    def test_nrot(self):
        self.assertEqual(run_code("1 2 3 -ROT . . ."), " 2  1  3 ")

    def test_dot_quote(self):
        # A single space after ." is a separator (kept, matching S").
        self.assertEqual(run_code('." hi there"'), " hi there")
        self.assertEqual(run_code(': X ." hello world" ; X'), " hello world")

    def test_immediate_paren_string(self):
        # .( text) prints its text and must not touch the data stack.
        self.assertEqual(run_code("CR .( Hello, World!)"), "\n Hello, World!")
        self.assertEqual(run_code("1 .( x) ."), " x 1 ")
        # Like .", the print is deferred until the compiled word runs.
        self.assertEqual(run_code(": SAY .( hi now) ; SAY"), " hi now")
        self.assertEqual(run_code(": SAY .( hi now) ;"), "")

    def test_alias(self):
        self.assertEqual(run_code(": FOO 42 ; FOO ALIAS BAR BAR ."), " 42 ")

    def test_struct_field(self):
        code = (
            "2 STRUCT POINT 0 FIELD .X 1 FIELD .Y ENDSTRUCT "
            "5 POINT ! .X @ ."
        )
        self.assertEqual(run_code(code), " 5 ")

    def test_numberq(self):
        self.assertEqual(run_code('S"123" NUMBER? . .'), " -1  123 ")
        self.assertEqual(run_code('S"nope" NUMBER? . .'), " 0  0 ")

    def test_abort_word(self):
        # ABORT clears the machine state and raises so the front-end can
        # report it, but the interpreter remains usable afterwards.
        with self.assertRaises(ForthError):
            run_code("1 2 ABORT")
        self.assertEqual(run_code("3 4 + ."), " 7 ")

    def test_abort_quote(self):
        # ABORT" raises with its text as the message and aborts execution.
        with self.assertRaises(ForthError):
            run_code('ABORT" boom"')
        with self.assertRaises(ForthError) as ctx:
            run_code('1 2 ABORT" count failed" 99 .')
        self.assertEqual(str(ctx.exception), " count failed")
        self.assertEqual(run_code("3 4 + ."), " 7 ")

    def test_fm_um_return_quotient_and_remainder(self):
        # FM/ / UM/M leave ( remainder quotient ); '.' prints top first.
        self.assertEqual(run_code("7 2 FM/ . ."), " 3  1 ")
        self.assertEqual(run_code("0 5 3 UM/M . ."), " 1  2 ")

    def test_immediate_compile_words(self):
        self.assertEqual(run_code(": FOO 5 ; : X ['] FOO EXECUTE ; X ."), " 5 ")
        self.assertEqual(run_code(": X 42 LITERAL ; X ."), " 42 ")
        self.assertEqual(run_code(": FOO 7 ; : X POSTPONE FOO ; X ."), " 7 ")
        self.assertEqual(run_code(": FOO 9 ; : X [COMPILE] FOO ; X ."), " 9 ")

    def test_endof_and_undo_no_crash(self):
        self.assertEqual(
            run_code('1 CASE 1 OF ." one" ENDOF ENDCASE'), " one"
        )


class TestCLI(unittest.TestCase):
    def _run_file(self, path):
        forth = Forth()
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli._run_source(forth, path, buf)
        return buf.getvalue()

    def test_run_example_file(self):
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "examples",
            "hello.fs",
        )
        self.assertIn("Hello, World!", self._run_file(path))

    def test_run_temperature_example(self):
        # The F>C converter example must produce the expected conversions.
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "examples",
            "temperature.fs",
        )
        output = self._run_file(path)
        self.assertIn("Celsius:     100", output)
        self.assertIn("Celsius:     36", output)
        self.assertIn("Celsius:     0", output)

    def test_batch_multiple_files(self):
        import tempfile
        tmpdir = tempfile.mkdtemp()
        first = os.path.join(tmpdir, "first.fs")
        second = os.path.join(tmpdir, "second.fs")
        with open(first, "w") as handle:
            handle.write("11 .\n")
        with open(second, "w") as handle:
            handle.write("22 .\n")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli.main(["-b", first, second])
        self.assertEqual(rc, 0)
        output = buf.getvalue()
        self.assertIn("11", output)
        self.assertIn("22", output)

    def test_repl_multiline_definition_single_ok(self):
        # A ": ... ;" spread over several pasted lines must announce only one
        # "ok", and comment/empty lines must stay silent.
        buf = io.StringIO()
        inp = io.StringIO(
            "\\ comment line\n\n"
            ": F>C\n"
            "32 -\n"
            "5 *\n"
            "9 /\n"
            ";\n"
            "212 F>C .\n"
            "bye\n"
        )
        with redirect_stdout(buf):
            cli.repl(Forth(), infile=inp, outfile=buf)
        self.assertEqual(buf.getvalue(), "ok\n 100 ok\n")

    def test_repl_bye_quits(self):
        for word in ("bye", "quit"):
            buf = io.StringIO()
            inp = io.StringIO("1 2 + .\n{}\n".format(word))
            with redirect_stdout(buf):
                cli.repl(Forth(), infile=inp, outfile=buf)
            self.assertEqual(buf.getvalue(), " 3 ok\n")


class TestWeb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from forth.web import app
        app.config.update(TESTING=True)
        cls.app = app
        cls.client = app.test_client()

    def test_index_loads(self):
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_run_endpoint(self):
        resp = self.client.post("/api/run", json={"code": "5 5 + ."})
        data = resp.get_json()
        self.assertIsNone(data["error"])
        self.assertIn("10", data["output"])

    def test_multi_line_run_endpoint(self):
        # Definitions and loops may span several lines in the web UI.
        code = ": SQUARE 2 ** ;\n1 5 DO I SQUARE . LOOP"
        resp = self.client.post("/api/run", json={"code": code})
        data = resp.get_json()
        self.assertIsNone(data["error"])
        self.assertIn(" 1  4  9  16 ", data["output"])

    def test_error_endpoint(self):
        resp = self.client.post("/api/run", json={"code": ". "})
        data = resp.get_json()
        self.assertIsNotNone(data["error"])

    def test_reset_endpoint(self):
        resp = self.client.post("/api/reset")
        self.assertTrue(resp.get_json()["ok"])


class TestRegression(unittest.TestCase):
    """Regression coverage for the interpreter fixes: control flow, error
    handling, numeric conversion and the compiler/interpret-mode words."""

    # -- LEAVE / DO ... LOOP ------------------------------------------------

    def test_leave_do_loop(self):
        self.assertEqual(
            run_code("1 10 DO I . I 3 > IF LEAVE THEN LOOP"), " 1  2  3  4 "
        )

    def test_leave_nested_do_loop(self):
        # The inner LEAVE exits only the inner loop; the outer loop runs
        # to completion with one iteration of the inner loop each time.
        self.assertEqual(
            run_code("1 10 DO I . 1 3 DO LEAVE LOOP LOOP"),
            " 1  2  3  4  5  6  7  8  9 ",
        )

    def test_leave_in_nested_plusloop(self):
        self.assertEqual(
            run_code("0 10 DO I . 2 +LOOP 1 5 DO I . LEAVE LOOP"),
            " 0  2  4  6  8  1 ",
        )

    def test_begin_until_loop(self):
        self.assertEqual(
            run_code("1 BEGIN DUP . 1+ DUP 5 > UNTIL DROP"), " 1  2  3  4  5 "
        )

    # -- raw Python exceptions become FORTH errors --------------------------

    def test_ln_domain_raises(self):
        with self.assertRaises(RuntimeError):
            run_code("0 LN")

    def test_log_domain_raises(self):
        with self.assertRaises(RuntimeError):
            run_code("-1 LOG")

    def test_exp_overflow_raises(self):
        with self.assertRaises(RuntimeError):
            run_code("100000 EXP")

    def test_pow_domain_raises(self):
        # fractional exponents are not reachable from FORTH source (no float
        # literals), so guard this small fixed case where it is reachable.
        with self.assertRaises(RuntimeError):
            run_code("0 -1 **")

    def test_shift_negative_count_raises(self):
        with self.assertRaises(RuntimeError):
            run_code("1 -1 LSHIFT")
        with self.assertRaises(RuntimeError):
            run_code("1 -1 RSHIFT")

    def test_if_without_then_raises(self):
        with self.assertRaises(ForthError):
            run_code(": BAD IF ; BAD")

    def test_else_without_then_raises(self):
        with self.assertRaises(ForthError):
            run_code(": BAD ELSE ; BAD")

    def test_colon_missing_name_raises(self):
        # Do not leave the machine in a half-compiled state.
        with self.assertRaises(ForthError):
            run_code(": 5")

    def test_variable_missing_name_raises(self):
        with self.assertRaises(ForthError):
            run_code("VARIABLE 5")

    def test_constant_missing_name_raises(self):
        with self.assertRaises(ForthError):
            run_code("3 CONSTANT 7")

    def test_create_missing_name_raises(self):
        with self.assertRaises(ForthError):
            run_code("CREATE 9")

    def test_plusloop_without_do_raises(self):
        with self.assertRaises(ForthError):
            run_code("2 +LOOP")

    # -- execution step budget ----------------------------------------------

    def test_max_steps_raises(self):
        forth = Forth()
        forth.max_steps = 50000
        forth.run(": LOOPIT BEGIN AGAIN ;")
        with self.assertRaises(ForthError):
            forth.run("LOOPIT")
        # the machine stays usable afterwards
        forth.run("1 2 + .")
        self.assertEqual(forth.output_text(), " 3 ")

    # -- ? reads the fed input without blocking -----------------------------

    def test_question_non_blocking_input(self):
        forth = Forth()
        forth.feed_input("3 4 + .\n")
        forth.run("?")
        self.assertEqual(forth.output_text(), " 7 ")

    # -- CASE selector leak --------------------------------------------------

    def test_case_no_selector_leak_matched(self):
        forth = Forth()
        forth.run("5 CASE 5 OF S\"five\" ENDOF ENDCASE COUNT TYPE DROP")
        self.assertEqual(forth.ds.depth(), 0)
        self.assertEqual(forth.output_text(), "five")

    def test_case_no_selector_leak_unmatched(self):
        forth = Forth()
        forth.run("0 CASE 1 OF S\"one\" ENDOF 2 OF S\"two\" ENDOF ENDCASE")
        self.assertEqual(forth.ds.depth(), 0)

    def test_case_no_selector_leak_default(self):
        forth = Forth()
        forth.run("4 CASE 1 OF S\"one\" ENDOF S\"other\" ENDCASE "
                  "COUNT TYPE DROP")
        self.assertEqual(forth.ds.depth(), 0)
        self.assertEqual(forth.output_text(), "other")

    def test_case_compiled(self):
        forth = Forth()
        forth.run(": PICKCASE CASE 2 OF S\"two\" ENDOF ENDCASE "
                  "COUNT TYPE DROP ;")
        forth.run("2 PICKCASE")
        self.assertEqual(forth.ds.depth(), 0)
        self.assertEqual(forth.output_text(), "two")
        # with a non-matching selector nothing is pushed, so the trailing
        # COUNT underflows (correctly) and raises a clean FORTH error
        with self.assertRaises(ForthError):
            forth.run("1 PICKCASE")
        self.assertEqual(forth.ds.depth(), 0)
        self.assertEqual(forth.output_text(), "two")

    # -- ABORT / ABORT" ------------------------------------------------------

    def test_abort_word_recovers(self):
        forth = Forth()
        with self.assertRaises(ForthError):
            forth.run("ABORT")
        forth.run("1 2 + .")
        self.assertEqual(forth.output_text(), " 3 ")
        self.assertEqual(forth.ds.depth(), 0)

    def test_abort_quote_message(self):
        forth = Forth()
        with self.assertRaises(ForthError) as cm:
            forth.run("ABORT\" boom\"")
        self.assertIn("boom", str(cm.exception))

    # -- counted string writes ----------------------------------------------

    def test_str_bang_keeps_last_char(self):
        forth = Forth()
        forth.run('CREATE BUF 20 ALLOT S"abcdefgh" BUF STR! '
                  "BUF COUNT TYPE")
        self.assertEqual(forth.output_text(), "abcdefgh")

    def test_chain_writes_full_string(self):
        forth = Forth()
        forth.run('CREATE BUF 20 ALLOT BUF S"xyzzy" CHAIN BUF COUNT TYPE')
        self.assertEqual(forth.output_text(), "xyzzy")

    def test_expect_accept_readline_arg_order(self):
        forth = Forth()
        forth.feed_input("hello")
        forth.run("CREATE BUF 40 ALLOT "
                  "BUF 5 EXPECT DROP COUNT TYPE ")
        self.assertEqual(forth.output_text(), "hello")
        forth.feed_input("abc")
        forth.run("BUF DUP 5 ACCEPT TYPE ")
        self.assertEqual(forth.output_text(), "helloabc")

    # -- comparison helpers --------------------------------------------------

    def test_one_less_comparison(self):
        self.assertEqual(run_code("0 1< ."), " -1 ")
        self.assertEqual(run_code("1 1< ."), " 0 ")

    def test_two_greater_comparison(self):
        self.assertEqual(run_code("3 2> ."), " -1 ")
        self.assertEqual(run_code("0 2> ."), " 0 ")

    def test_lt_dup_only_when_nonzero(self):
        self.assertEqual(run_code("0 <DUP ."), " 0 ")
        self.assertEqual(run_code("5 <DUP . ."), " 5  5 ")

    def test_q_dup_only_when_nonzero(self):
        forth = Forth()
        forth.run("0 ?DUP")
        self.assertEqual(forth.ds.depth(), 1)
        forth = Forth()
        forth.run("5 ?DUP")
        self.assertEqual(forth.ds.depth(), 2)

    # -- division semantics --------------------------------------------------

    def test_fdiv_truncates_to_zero(self):
        self.assertEqual(run_code("-7 3 F/ ."), " -2 ")

    def test_minusdiv_floors(self):
        self.assertEqual(run_code("-7 3 -/ ."), " -3 ")
        self.assertEqual(run_code("7 3 -/ ."), " 2 ")

    def test_odd_base_rejected(self):
        with self.assertRaises(RuntimeError):
            run_code("1 BASE ! 123 .")

    # -- numeric picture words ----------------------------------------------

    def test_hash_words_build_picture(self):
        self.assertEqual(run_code("123 #S #> COUNT TYPE"), "123")
        self.assertEqual(run_code("-45 #S #> COUNT TYPE"), "-45")
        self.assertEqual(run_code("HEX FF #S #> COUNT TYPE"), "FF")
        self.assertEqual(run_code("0 #S #> COUNT TYPE"), "0")

    # -- [] / LITERAL interpret regions -------------------------------------

    def test_bracket_literal(self):
        self.assertEqual(run_code(": X [ 5 ] LITERAL ; X ."), " 5 ")

    def test_plain_literal(self):
        self.assertEqual(run_code(": X 5 LITERAL ; X ."), " 5 ")

    def test_bracket_region_computes(self):
        self.assertEqual(run_code(": X [ 2 2 + ] LITERAL ; X ."), " 4 ")

    def test_bracket_at_top_level(self):
        self.assertEqual(run_code("1 [ 2 ] + ."), " 3 ")

    # -- POSTPONE / ['] / EXECUTE --------------------------------------------

    def test_postpone_secondary(self):
        self.assertEqual(run_code(": X 5 ; : Y POSTPONE X ; Y ."), " 5 ")

    def test_postpone_primitive(self):
        self.assertEqual(run_code(": DUP2 POSTPONE DUP ; 7 DUP2 . ."),
                         " 7  7 ")

    def test_lit_tick_and_execute(self):
        self.assertEqual(run_code(": SQ DUP * ; 7 ['] SQ EXECUTE ."), " 49 ")
        self.assertEqual(run_code("7 ['] DUP EXECUTE . ."), " 7  7 ")

    # -- STATE / SOURCE / WORD / BL ------------------------------------------

    def test_state_word(self):
        self.assertEqual(run_code("STATE @ ."), " 0 ")
        self.assertEqual(run_code(": S STATE @ ; S ."), " 0 ")

    def test_source_word(self):
        forth = Forth()
        forth.run("SOURCE SWAP DROP .")
        self.assertEqual(forth.output_text(), " 18 ")

    def test_word_parses_source(self):
        forth = Forth()
        forth.run("BL WORD COUNT TYPE BL WORD COUNT TYPE")
        self.assertEqual(forth.output_text(), "BLWORD")

    def test_word_advances_in(self):
        forth = Forth()
        forth.run("BL WORD DROP >IN @ .")
        self.assertTrue(forth.output_text().strip().isnumeric())

    def test_bl_word(self):
        self.assertEqual(run_code("BL ."), " 32 ")

    # -- missing-feature batch: HERE , C, 2@ 2! WORDS INCLUDE ----------------

    def test_here_returns_free_cell(self):
        f = Forth()
        f.run("HERE .")
        here = int(f.output_text().split()[0])
        self.assertGreater(here, 0)
        f.run("1 ALLOT")
        self.assertEqual(f.ds.depth(), 0)
        self.assertEqual(f.mem.next_cell_addr, here + 1)

    def test_comma_stores_cell(self):
        forth = Forth()
        forth.run("HERE 42 , HERE 1- @ .")
        self.assertEqual(forth.output_text(), " 42 ")

    def test_c_comma_stores_byte(self):
        forth = Forth()
        forth.run("HERE 65 C, HERE 1- C@ .")
        self.assertEqual(forth.output_text(), " 65 ")

    def test_two_fetch_and_store(self):
        self.assertEqual(run_code("1 2 HERE 2! HERE 2@ . ."), " 2  1 ")
        self.assertEqual(run_code("1 2 HERE 2! HERE 2@ + ."), " 3 ")

    def test_words_lists_dictionary(self):
        forth = Forth()
        forth.run(": FOO 10 ;")
        forth.run("WORDS")
        names = forth.output_text().split()
        self.assertIn("DUP", names)
        self.assertIn("HERE", names)
        self.assertIn("FOO", names)
        self.assertIn("INCLUDE", names)

    def test_include_loads_file(self):
        import tempfile
        with tempfile.NamedTemporaryFile(
                mode="w", suffix=".fs", delete=False) as handle:
            handle.write(": SQU 4 ;")
            path = handle.name
        try:
            forth = Forth()
            forth.run("INCLUDE {} SQU .".format(path))
            self.assertEqual(forth.output_text(), " 4 ")
        finally:
            os.unlink(path)

    def test_include_missing_file_raises(self):
        with self.assertRaises(ForthError):
            run_code("INCLUDE this_file_does_not_exist.fs")

    # -- batch 2: ROLL/2ROT, /MOD family, R-stack pairs, WITHIN ------------

    def test_two_rot(self):
        self.assertEqual(run_code("1 2 3 4 5 6 2ROT . . . . . ."),
                         " 2  1  6  5  4  3 ")

    def test_roll(self):
        self.assertEqual(run_code("5 4 3 2 1 4 ROLL . . . . ."),
                         " 5  1  2  3  4 ")

    def test_slash_mod(self):
        self.assertEqual(run_code("-7 3 /MOD . ."), " -2  -1 ")
        self.assertEqual(run_code("7 3 /MOD . ."), " 2  1 ")
        with self.assertRaises(RuntimeError):
            run_code("1 0 /MOD")

    def test_star_slash_family(self):
        self.assertEqual(run_code("6 7 3 */MOD . ."), " 14  0 ")
        self.assertEqual(run_code("6 -7 3 */ ."), " -14 ")
        with self.assertRaises(RuntimeError):
            run_code("6 7 0 */")

    def test_double_return_stack(self):
        self.assertEqual(run_code("1 2 2>R 2R> . ."), " 2  1 ")
        self.assertEqual(run_code("1 2 2>R 2R@ + ."), " 3 ")
        self.assertEqual(run_code("1 2 2>R RDROP R> ."), " 1 ")

    def test_within(self):
        self.assertEqual(run_code("5 0 10 WITHIN ."), " -1 ")
        self.assertEqual(run_code("0 0 10 WITHIN ."), " -1 ")
        self.assertEqual(run_code("10 0 10 WITHIN ."), " 0 ")
        self.assertEqual(run_code("11 0 10 WITHIN ."), " 0 ")
        self.assertEqual(run_code("-3 -5 0 WITHIN ."), " -1 ")

    # -- batch 2: CMOVE/CMOVE>/FILL/ERASE/BLANK/BOUNDS/CELLS --------------

    def test_cmove_forward(self):
        self.assertEqual(run_code("65 100 C! 66 101 C! 67 102 C! "
                                  "100 200 3 CMOVE "
                                  "200 C@ . 201 C@ . 202 C@ ."),
                         " 65  66  67 ")

    def test_cmove_backward_and_overlap(self):
        self.assertEqual(run_code("65 200 C! 66 201 C! 67 202 C! "
                                  "200 100 3 CMOVE> "
                                  "100 C@ . 101 C@ . 102 C@ ."),
                         " 65  66  67 ")
        # overlapping same-buffer copy: shift a run right by one
        self.assertEqual(run_code("66 201 C! 66 202 C! "
                                  "201 200 2 CMOVE> "
                                  "200 C@ . 201 C@ ."),
                         " 66  66 ")

    def test_fill_erase_blank(self):
        forth = Forth()
        forth.run("HERE 3 64 FILL HERE C@ . HERE 1+ C@ .")
        self.assertEqual(forth.output_text(), " 64  64 ")
        forth = Forth()
        forth.run("HERE 3 64 FILL HERE 3 ERASE HERE C@ . HERE 1+ C@ .")
        self.assertEqual(forth.output_text(), " 0  0 ")
        forth = Forth()
        forth.run("HERE 3 BLANK HERE C@ .")
        self.assertEqual(forth.output_text(), " 32 ")

    def test_bounds_cells(self):
        self.assertEqual(run_code("100 10 BOUNDS - ."), " 10 ")
        self.assertEqual(run_code("100 10 BOUNDS ."), " 100 ")
        self.assertEqual(run_code("100 CELLS CELL+ ."), " 101 ")

    def test_dot_r_forms(self):
        self.assertEqual(run_code("5 3 .R"), "  5")
        self.assertEqual(run_code("-5 3 .R"), " -5")
        self.assertEqual(run_code("12345 3 .R"), "12345")
        self.assertEqual(run_code("-5 3 U.R"), "  5")
        self.assertEqual(run_code("5 4 U.R"), "   5")

    # -- batch 2: EXIT / RECURSE ------------------------------------------

    def test_exit_aborts_top_of_definition(self):
        self.assertEqual(run_code(": A 10 EXIT 99 ; A ."), " 10 ")

    def test_exit_inside_if(self):
        self.assertEqual(run_code(": C DUP 1 = IF EXIT THEN DROP 77 ;"
                                  " 1 C ."), " 1 ")
        self.assertEqual(run_code(": C DUP 1 = IF EXIT THEN DROP 77 ;"
                                  " 2 C ."), " 77 ")

    def test_exit_inside_do(self):
        self.assertEqual(run_code(": D 1 10 DO I . EXIT LOOP 99 ; D"),
                         " 1 ")

    def test_exit_outside_definition_raises(self):
        with self.assertRaises(ForthError):
            run_code("EXIT")

    def test_recurse(self):
        code = ": F DUP 1 = IF DROP 1 EXIT THEN DUP 1- F * ;"
        self.assertEqual(run_code(code + " 5 F ."), " 120 ")
        self.assertEqual(run_code(code + " 1 F ."), " 1 ")

    # -- batch 2: U. / [CHAR] / TIB / PAD / MOVE / /STRING ----------------

    def test_u_dot(self):
        self.assertEqual(run_code("-5 U."), " 5 ")
        self.assertEqual(run_code("5 U."), " 5 ")

    def test_bracket_char(self):
        self.assertEqual(run_code("[CHAR] X EMIT"), "X")
        self.assertEqual(run_code(": A [CHAR] X EMIT ; A"), "X")

    def test_tib_pad_addresses(self):
        forth = Forth()
        forth.run("TIB PAD")
        self.assertEqual(forth.ds.data, [forth.uv["TIB"], forth.uv["PAD"]])

    def test_move_cells(self):
        self.assertEqual(run_code("65 100 C! 66 101 C! 100 200 2 MOVE "
                                  "200 C@ . 201 C@ ."), " 65  66 ")

    def test_slash_string(self):
        forth = Forth()
        forth.run('S" abcABCD" COUNT 4 /STRING 4 = .')
        self.assertEqual(forth.output_text(), " -1 ")

    # -- invalid-program recovery across a whole file ------------------------

    def test_error_does_not_corrupt_dictionary(self):
        forth = Forth()
        forth.run(": GOOD 5 ;")
        forth.run(": DIVZ 1 0 / ;")
        with self.assertRaises(RuntimeError):
            forth.run("DIVZ")
        forth.run("GOOD .")
        self.assertEqual(forth.output_text(), " 5 ")


if __name__ == "__main__":
    unittest.main(verbosity=2)
