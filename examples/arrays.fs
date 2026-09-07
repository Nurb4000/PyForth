\ arrays.fs - declare and use a fixed-size array of cells.
\ Run with:  python -m forth.cli examples/arrays.fs

\ Declare an array of 6 cells named SQUARES.
6 ARRAYS SQUARES

\ Fill it with the squares of 0..5 and print them back out.
0 6 DO
   I I * SQUARES I + !      \ store I*I into element I
LOOP

0 6 DO SQUARES I + @ . LOOP CR
