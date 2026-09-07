"""PyForth - a FORTH interpreter written in Python.

This package provides a reasonably complete implementation of the FORTH
language: an ANSI-FORTH style core plus a set of extensions (strings,
arrays, files, extended math and more).  It is designed to run both from
the command line (interactive REPL / source-file execution) and through a
web front-end (see the ``forth.web`` module).
"""

from .machine import Forth, ForthError

__all__ = ["Forth", "ForthError"]
__version__ = "1.0.0"
