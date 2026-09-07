\ fizzbuzz.fs - the classic programming puzzle in FORTH.
\ Run with:  python -m forth.cli examples/fizzbuzz.fs

\ COUNT leaves the original string pointer on the stack, so wrap printing a
\ counted string in a small helper that drops that leftover pointer.
: P-STR   ( a# -- )  COUNT TYPE DROP ;

: FIZZBUZZ   ( n -- )
   DUP 3 MOD 0 = IF S"Fizz" P-STR THEN
   DUP 5 MOD 0 = IF S"Buzz" P-STR THEN
   CR DROP
;

1 20 DO I FIZZBUZZ LOOP
