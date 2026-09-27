\ fibonacci.fs - compute Fibonacci numbers using recursion.
\ Run with:  python -m forth.cli examples/fibonacci.fs

: FIB   ( n -- fib(n) )
   DUP 2 <            \ 2 below n, i.e. n is greater than 2?
     IF  DUP 1 - FIB  SWAP 2 - FIB  +
     ELSE  DROP 1
   THEN
;

\ Print the first ten Fibonacci numbers.
1 11 DO I FIB . LOOP CR
