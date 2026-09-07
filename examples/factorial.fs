\ factorial.fs - compute 6! using a DO/LOOP.
\ Run with:  python -m forth.cli examples/factorial.fs

: FACTORIAL   ( n -- n! )
   1  SWAP  1 +  1 SWAP
   DO  I *  LOOP
;

6 FACTORIAL . CR

\ Also show it for a few values using a loop:
1 10 DO I FACTORIAL . LOOP CR
