; =============================================================================
; HUD: screen rows 21-23, below the black band (video.asm), never scrolled.
;
;   row 21   score (white), best score (cyan), coin icon + coins (yellow),
;            life icon + lives
;   row 22   the route Kiato - Piraeus: a station every 6 cells, the runner
;            (route_here) where it is
;   row 23   the six power-ups: icon (lit, or black colour RAM when off) and a
;            time bar of 3 characters (12 pixels)
;
; Both screens hold the same HUD (the top IRQ swaps them); colour RAM is one.
; hud_update compares every value with the one on screen (hud_shown) and
; writes only what changed.
; =============================================================================

HUD_A           = SCREEN_A + HUD_ROW*40
HUD_B           = SCREEN_B + HUD_ROW*40
HUD_CRAM        = COLOR_RAM + HUD_ROW*40
HUD_SCORE_X     = 1
HUD_HI_X        = 9
HUD_COIN_X      = 24
HUD_COINS_X     = 27
HUD_LIFE_X      = 34
HUD_LIVES_X     = 37
ROUTE_FIRST     = 1                     ; route_start
ROUTE_LAST      = 38                    ; route_end
ROUTE_CELLS     = 6                     ; cells between two stations
ROUTE_STEP      = 53                    ; rows a cell (320 / 6)
PU_BAR_PIXELS   = 12

; offsets in hud_chars / hud_colours (png2c64.py: A.CHAR_SHEETS["hud"])
HC_ICONS        = 0                     ; 2 characters each: 6 power-ups,
HC_COIN         = 12                    ; coin, life
HC_LIFE         = 14
HC_BAR          = 16                    ; bar0 .. bar4
HC_LINE         = 21
HC_STATION      = 22
HC_HERE         = 23
HC_START        = 24
HC_END          = 25

; -----------------------------------------------------------------------------
; hud_init: the fixed parts, and nothing shown yet (all drawn next update)
; -----------------------------------------------------------------------------
hud_init
        ldx #3*40-1
-       lda #FONT_SPACE
        sta HUD_A,x
        sta HUD_B,x
        lda #8 | WHITE
        sta HUD_CRAM,x
        dex
        bpl -
        ldx #1                          ; coin and life icons
-       lda hud_chars+HC_COIN,x
        sta HUD_A+HUD_COIN_X,x
        sta HUD_B+HUD_COIN_X,x
        lda hud_colours+HC_COIN,x
        sta HUD_CRAM+HUD_COIN_X,x
        lda hud_chars+HC_LIFE,x
        sta HUD_A+HUD_LIFE_X,x
        sta HUD_B+HUD_LIFE_X,x
        lda hud_colours+HC_LIFE,x
        sta HUD_CRAM+HUD_LIFE_X,x
        dex
        bpl -
        lda #8 | CYAN
        ldx #5
-       sta HUD_CRAM+HUD_HI_X,x
        dex
        bpl -
        lda #8 | YELLOW
        ldx #3
-       sta HUD_CRAM+HUD_COINS_X,x
        dex
        bpl -
        jsr hud_route                   ; the route (and the runner, next update)
        ldx #5                          ; power-up icons (their colour: update)
-       txa
        asl a
        tay
        lda pu_hud_x,x
        stx t8
        tax
        lda hud_chars+HC_ICONS,y
        sta HUD_A+80,x
        sta HUD_B+80,x
        lda hud_chars+HC_ICONS+1,y
        sta HUD_A+81,x
        sta HUD_B+81,x
        ldx t8
        dex
        bpl -
        ldx #HUD_SHOWN_SIZE-1           ; nothing valid on screen
        lda #$ff
-       sta hud_shown,x
        dex
        bpl -
        rts

; the route without the runner; the runner drawn by the next update
hud_route
        ldx #ROUTE_LAST
-       jsr route_cell
        dex
        cpx #ROUTE_FIRST
        bcs -
        lda #$ff
        sta shown_route
        rts

; X = route column: its character without the runner, both screens + colour
route_cell
        ldy #HC_LINE
        cpx #ROUTE_FIRST
        bne +
        ldy #HC_START
+       cpx #ROUTE_LAST
        bne +
        ldy #HC_END
+       txa                             ; a station every ROUTE_CELLS
        sec
        sbc #ROUTE_FIRST
        beq _done
-       sec
        sbc #ROUTE_CELLS
        bcs -
        adc #ROUTE_CELLS
        bne _done
        cpy #HC_LINE
        bne _done
        ldy #HC_STATION
_done   lda hud_chars,y
        sta HUD_A+40,x
        sta HUD_B+40,x
        lda hud_colours,y
        sta HUD_CRAM+40,x
        rts

; -----------------------------------------------------------------------------
; hud_update: once a frame, whatever changed
; -----------------------------------------------------------------------------
hud_update
        ; --- score ---
        ldx #2
-       lda score,x
        cmp shown_score,x
        bne _score
        dex
        bpl -
        bmi _hi
_score  ldx #2
-       lda score,x
        sta shown_score,x
        dex
        bpl -
        lda score+2
        ldx #HUD_SCORE_X
        jsr hud_bcd
        lda score+1
        ldx #HUD_SCORE_X+2
        jsr hud_bcd
        lda score
        ldx #HUD_SCORE_X+4
        jsr hud_bcd

        ; --- best: the score if higher ---
_hi     ldx #2
-       lda score,x
        cmp best,x
        bcc _best                       ; lower
        bne _score_hi                   ; higher
        dex
        bpl -
_score_hi
        lda #<score
        ldx #>score
        bne +
_best   lda #<best
        ldx #>best
+       sta ptr4
        stx ptr4+1
        ldy #2
-       lda (ptr4),y
        cmp shown_hi,y
        bne _hi_new
        dey
        bpl -
        bmi _coins
_hi_new ldy #2
-       lda (ptr4),y
        sta shown_hi,y
        dey
        bpl -
        lda shown_hi+2
        ldx #HUD_HI_X
        jsr hud_bcd
        lda shown_hi+1
        ldx #HUD_HI_X+2
        jsr hud_bcd
        lda shown_hi
        ldx #HUD_HI_X+4
        jsr hud_bcd

        ; --- coins ---
_coins  lda coins
        cmp shown_coins
        bne +
        lda coins+1
        cmp shown_coins+1
        beq _lives
+       lda coins
        sta shown_coins
        lda coins+1
        sta shown_coins+1
        ldx #HUD_COINS_X
        jsr hud_bcd
        lda coins
        ldx #HUD_COINS_X+2
        jsr hud_bcd

        ; --- lives ---
_lives  lda lives
        cmp shown_lives
        beq _route
        sta shown_lives
        clc
        adc #FONT_N0
        sta HUD_A+HUD_LIVES_X
        sta HUD_B+HUD_LIVES_X

        ; --- the runner on the route ---
_route  lda route_x
        cmp shown_route
        beq _pu
        ldx shown_route
        sta shown_route
        cpx #ROUTE_LAST+1               ; ($ff: nothing there yet)
        bcs +
        jsr route_cell
+       ldx shown_route
        lda hud_chars+HC_HERE
        sta HUD_A+40,x
        sta HUD_B+40,x
        lda hud_colours+HC_HERE
        sta HUD_CRAM+40,x

        ; --- power-ups: $80 | lit pixels of the bar, or 0 ---
_pu     ldx #5
_pu_one stx hud_i
        jsr pu_level
        ldx hud_i
        cmp shown_pu,x
        beq _pu_next
        sta shown_pu,x
        jsr pu_draw
_pu_next
        ldx hud_i
        dex
        bpl _pu_one
        rts

; A = BCD byte, X = column in HUD row 0: its two digits (both screens)
hud_bcd
        pha
        lsr a
        lsr a
        lsr a
        lsr a
        clc
        adc #FONT_N0
        sta HUD_A,x
        sta HUD_B,x
        pla
        and #$0f
        clc
        adc #FONT_N0
        sta HUD_A+1,x
        sta HUD_B+1,x
        rts

; X = power-up 0-5 -> A = 0 (off) or $80 | pixels of its bar (1-12)
pu_level
        cpx #ITEM_HELMET - ITEM_MAGNET
        bne _timer
        lda helmet                      ; the helmet: lit, a full bar
        beq _ret
        lda #$80 | PU_BAR_PIXELS
_ret    rts
_timer  txa
        asl a
        tay
        lda pu_timers,y
        sta t16
        lda pu_timers+1,y
        sta t16+1
        ora t16
        beq _ret
        ldy #0                          ; pixels = timer / step, rounded up
-       iny
        cpy #PU_BAR_PIXELS
        beq _full
        lda t16
        sec
        sbc pu_steps,x
        sta t16
        lda t16+1
        sbc #0
        sta t16+1
        bcc _full                       ; went below zero: this pixel is the last
        ora t16
        bne -
_full   tya
        ora #$80
        rts

; X = power-up, A = its level: icon colour and the 3 bar characters
pu_draw
        sta t8                          ; level
        lda pu_hud_x,x
        tay                             ; Y = column
        txa
        asl a
        tax                             ; X = icon in hud_*
        lda t8
        bne +
        lda #8                          ; off: black
        sta HUD_CRAM+80,y
        sta HUD_CRAM+81,y
        jmp _bars
+       lda hud_colours+HC_ICONS,x
        sta HUD_CRAM+80,y
        lda hud_colours+HC_ICONS+1,x
        sta HUD_CRAM+81,y
_bars   lda t8
        and #$7f                        ; pixels left to show
        sta t8
        ldx #3
-       lda t8                          ; this character: min(4, pixels)
        cmp #4
        bcc +
        lda #4
+       sta t8b
        lda t8
        sec
        sbc t8b
        sta t8
        lda t8b
        clc
        adc #HC_BAR
        sta t8b
        stx t8c
        tax
        lda hud_chars,x
        sta HUD_A+82,y
        sta HUD_B+82,y
        lda hud_colours,x
        sta HUD_CRAM+82,y
        iny
        ldx t8c
        dex
        bne -
        rts

; HUD columns of the six power-ups (icon, then the bar)
pu_hud_x        .byte 1, 7, 13, 21, 27, 33
; timer frames a bar pixel, by power-up (durations / 12; the helmet: none)
pu_steps        .byte 42, 34, 34, 42, 0, 63

; best = the score, if higher (game over)
update_best
        ldx #2
-       lda score,x
        cmp best,x
        bcc _ret
        bne _new
        dex
        bpl -
_ret    rts
_new    ldx #2
-       lda score,x
        sta best,x
        dex
        bpl -
        rts

; -----------------------------------------------------------------------------
; route_row: the world moved one row (score_row)
; -----------------------------------------------------------------------------
route_row
        inc route_sub
        lda route_sub
        cmp #ROUTE_STEP
        bcc +
        lda #0
        sta route_sub
        lda route_x
        cmp #ROUTE_LAST-1               ; Piraeus is as far as it goes
        bcs +
        inc route_x
+       rts

; A = station just passed (1-6): the runner on it (Piraeus: back to the start)
route_to_station
        cmp #ROUTE_STATIONS-1
        bne +
        lda #0
+       sta t8
        asl a
        adc t8
        asl a                           ; * ROUTE_CELLS
        adc #ROUTE_FIRST
        sta route_x
        lda #0
        sta route_sub
        rts
