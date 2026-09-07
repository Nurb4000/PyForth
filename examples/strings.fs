\ strings.fs - demonstrate the string extension words.
\ Run with:  python -m forth.cli examples/strings.fs

S" Hello"   S" World" STRING= .   CR \ different text -> 0 (false)
S" abc"     S" abc"   STRING= .   CR \ same text      -> -1 (true)
S" apple"   S" banana" STRING< .  CR \ 'apple' < 'banana' -> -1 (true)

\ Print a label and the result of a calculation.
S" The answer is " COUNT TYPE
40 20 * . CR
