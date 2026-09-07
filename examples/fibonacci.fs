\ fibonacci.fs - compute Fibonacci numbers using recursion.
\ Run with:  python -m forth.cli examples/fibonacci.fs

: FIB   ( n -- fib(n) )
   DUP 2 <=
     IF  DROP 1
     ELSE  DUP 1 - FIB  SWAP 2 - FIB  +
   THEN
;

\ Print the first ten Fibonacci numbers.
1 11 DO I FIB . LOOP CR
