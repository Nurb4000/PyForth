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
        # The ABORT word used to raise AttributeError (f.control).
        run_code("1 2 ABORT")
        self.assertEqual(run_code("3 4 + ."), " 7 ")

    def test_abort_quote(self):
        run_code('ABORT" boom"')
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
