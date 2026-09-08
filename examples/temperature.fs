\ temperature.fs - Fahrenheit to Celsius converter.
\ Run with:  python -m forth -b examples/temperature.fs

: F>C   ( fahrenheit -- celsius )
   32 -        \ Subtract 32
   5 *         \ Multiply by 5
   9 /         \ Divide by 9
;

: CONVERT-WEATHER   ( fahrenheit -- )
   CR ." Fahrenheit: " DUP .
   F>C
   CR ." Celsius:    " .
;

\ Convert a few common readings:
212 CONVERT-WEATHER
98 CONVERT-WEATHER
32 CONVERT-WEATHER