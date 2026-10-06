; =============================================================================
; Joystick port 2 and keyboard -> keys_held / keys_pressed (the CPC's bits).
;
;   left  = joystick left, O, cursor left     right = joystick right, P, cursor right
;   jump  = joystick up / fire, Q, space, cursor up
;   down  = joystick down, A, cursor down (fast landing)
;   pause = H     esc = RUN/STOP
; A test sets test_mode and writes test_keys instead.
; =============================================================================

KEY_LEFT        = 1
KEY_RIGHT       = 2
KEY_JUMP        = 4
KEY_DOWN        = 8
KEY_PAUSE       = 16
KEY_ESC         = 32
KEY_UP          = 64                    ; menus: up (also a jump in the game)
KEY_FIRE        = 128                   ; menus: select (also a jump in the game)

read_input
        lda test_mode
        beq +
        lda test_keys
        jmp _done
+       lda #$ff                        ; no keyboard column: the joystick alone
        sta CIA1_PRA
        lda CIA1_PRA
        eor #$ff
        and #$1f
        tax
        lda joy_keys,x
        sta t8
        cpx #0                          ; joystick in use: its lines would show
        bne _sum                        ; up as keys, skip the keyboard

        ldx #KEYMAP_LEN-1               ; keyboard: column, row, controls
-       lda keymap_col,x
        sta CIA1_PRA
        lda CIA1_PRB
        and keymap_row,x
        bne +
        lda t8
        ora keymap_bits,x
        sta t8
+       dex
        bpl -
        lda #%11111110                  ; cursor keys: left/up with a shift
        sta CIA1_PRA
        lda CIA1_PRB
        eor #$ff
        sta t8b
        lda #%11111101                  ; left shift
        sta CIA1_PRA
        lda CIA1_PRB
        and #$80
        beq _shift
        lda #%10111111                  ; right shift
        sta CIA1_PRA
        lda CIA1_PRB
        and #$10
_shift  php                             ; Z: a shift is down
        lda t8b
        and #$04                        ; CRSR left/right
        beq _vert
        lda #KEY_RIGHT
        plp
        php
        bne +
        lda #KEY_LEFT
+       ora t8
        sta t8
_vert   lda t8b
        and #$80                        ; CRSR up/down
        beq _cursors
        lda #KEY_DOWN
        plp
        php
        bne +
        lda #KEY_JUMP | KEY_UP
+       ora t8
        sta t8
_cursors
        plp
        lda #$ff
        sta CIA1_PRA
_sum    lda t8
_done   sta t8                          ; pressed = now and not before
        lda keys_held
        eor #$ff
        and t8
        sta keys_pressed
        lda t8
        sta keys_held
        rts

; joystick bits (up, down, left, right, fire) -> controls
joy_keys
        .for j = 0, j < 32, j += 1
        .byte ((j & 1) != 0 ? KEY_JUMP | KEY_UP : 0) | ((j & 2) != 0 ? KEY_DOWN : 0) | ((j & 4) != 0 ? KEY_LEFT : 0) | ((j & 8) != 0 ? KEY_RIGHT : 0) | ((j & 16) != 0 ? KEY_JUMP | KEY_FIRE : 0)
        .endfor

; keyboard matrix: column select ($dc00), row bit ($dc01), controls
keymap_col      .byte %11101111, %11011111, %01111111, %11111101, %01111111, %11110111, %01111111
keymap_row      .byte %01000000, %00000010, %01000000, %00000100, %00010000, %00100000, %10000000
keymap_bits     .byte KEY_LEFT, KEY_RIGHT, KEY_JUMP | KEY_UP, KEY_DOWN, KEY_JUMP | KEY_FIRE, KEY_PAUSE, KEY_ESC
KEYMAP_LEN      = 7                     ; O, P, Q, A, space, H, RUN/STOP
