; VIC-II: multicolor text, two screen buffers, vertical scroll, HUD split.
;
; Picture (raster lines, 24-row mode: window $37-$f6):
;   $30+y ...   screen rows 0-20 scroll (YSCROLL = y). Row 20 is only partly
;               visible; row 0 enters at the top.
;   $d7-$de     black band: ECM+MCM (invalid mode) shows black, and YSCROLL
;               is moved so no bad line falls inside it (FLD).
;   $df-$f6     screen rows 21-23 = HUD, always at YSCROLL 7, so it never moves.
;
; Coarse step: both screens hold the playfield; the hidden one is rebuilt
; (rows 0-19 of the shown one -> rows 1-20, new row 0) over COPY_STAGES
; frames, then the top IRQ swaps them together with the YSCROLL wrap.

SCREEN_A        = $4000
SCREEN_B        = $4400
CHARSET         = $4800

D018_A          = ((SCREEN_A & $3fff) >> 6) | ((CHARSET & $3fff) >> 10)
D018_B          = ((SCREEN_B & $3fff) >> 6) | ((CHARSET & $3fff) >> 10)

PF_ROWS         = 21            ; scrolling rows 0-20
HUD_ROW         = 21            ; HUD rows 21-23
HUD_ROWS        = 3
COPY_STAGES     = 2
COPY_ROWS       = 10            ; rows per stage (2 x 10 = rows 0-19)

D011_ON         = $10           ; DEN, 24 rows, text
D011_ECM        = $40           ; ECM + MCM: invalid mode, black

SPLIT_IRQ_LINE  = $d3            ; a bad line here (y = 3) still leaves time to reach $d6
BAND_TOP        = $d7           ; first black line
HUD_TOP         = $df           ; first HUD line (bad line of row 21)
SPLIT_DELAY     = 11            ; delay loop counts (5 cycles each), see video_irq_split
SPLIT_DELAY_BAD = 3

; ---------------------------------------------------------------------------
video_init
        lda #BLACK
        sta VIC_BORDER
        lda #DARK_GREY
        sta VIC_BG0
        lda #LIGHT_GREY
        sta VIC_BG1
        lda #BROWN
        sta VIC_BG2
        lda #0
        sta VIC_SPR_ENA

        lda CIA2_DDRA           ; VIC bank 1: $4000-$7fff
        ora #3
        sta CIA2_DDRA
        lda CIA2_PRA
        and #$fc
        ora #2
        sta CIA2_PRA

        jsr copy_rom_font

        lda #D011_ON | 7
        sta VIC_CTRL1
        lda #$18                ; multicolor, 40 columns
        sta VIC_CTRL2
        lda #D018_A
        sta VIC_MEM

        ; colour RAM: playfield columns fixed, HUD per cell (hires white)
        ldx #0
-       lda col_colours,x
        .for rr = 0, rr < PF_ROWS, rr += 1
        sta COLOR_RAM + rr*40,x
        .endfor
        lda #WHITE
        .for rr = HUD_ROW, rr < 25, rr += 1
        sta COLOR_RAM + rr*40,x
        .endfor
        inx
        cpx #40
        bne -

        ; both screens: blank, HUD text
        ldx #0
        lda #$20
-       sta SCREEN_A,x
        sta SCREEN_A+$100,x
        sta SCREEN_A+$200,x
        sta SCREEN_A+$2e8,x
        sta SCREEN_B,x
        sta SCREEN_B+$100,x
        sta SCREEN_B+$200,x
        sta SCREEN_B+$2e8,x
        inx
        bne -
        ldx #39
-       lda hud_text,x
        sta SCREEN_A + HUD_ROW*40,x
        sta SCREEN_B + HUD_ROW*40,x
        dex
        bpl -

        ; screen A shows world rows 20 (top) .. 0 (row 20)
        lda #PF_ROWS-1
        sta disp_top
        lda #0
        sta disp_top+1
        sta cur_buf
        lda #<SCREEN_A
        sta ptr
        lda #>SCREEN_A
        sta ptr+1
        ldx #0
-       txa
        eor #$ff
        sec
        adc disp_top            ; world row = top - screen row
        stx tmp
        jsr render_row
        ldx tmp
        lda ptr
        clc
        adc #40
        sta ptr
        bcc +
        inc ptr+1
+       inx
        cpx #PF_ROWS
        bne -

        lda #0                  ; build screen B for the first coarse step
        sta copy_stage
        lda #7
        sta scroll_y
        sta scroll_cmd
        lda #$00                ; 2.0 pixels per frame
        sta speed_lo
        lda #2
        sta speed_hi
        rts

; Upper-case ROM font -> CHARSET (the Phase 1 stand-in for our own charset).
copy_rom_font
        lda #$33                ; character ROM at $d000
        sta $01
        ldx #0
-       .for pg = 0, pg < 8, pg += 1
        lda $d000 + pg*$100,x
        sta CHARSET + pg*$100,x
        .endfor
        inx
        bne -
        lda #$36
        sta $01
        rts

; ---------------------------------------------------------------------------
; Top IRQ (line 0): apply what the main loop asked for in scroll_cmd.
video_irq_top
        lda scroll_cmd
        and #8
        beq +
        lda cur_buf             ; coarse step: swap screens
        eor #1
        sta cur_buf
        tax
        lda d018_values,x
        sta VIC_MEM
        inc disp_top
        bne +
        inc disp_top+1
+       lda scroll_cmd
        and #7
        sta scroll_cmd          ; consumed: no second swap if the main loop is late
        tax
        ora #D011_ON
        sta VIC_CTRL1
        ora #D011_ECM
        sta split_w1
        lda #SPLIT_DELAY
        cpx #6                  ; y = 6: line $d6 is a bad line, the CPU loses
        bne +                   ; cycles 12-54 inside the delay loop
        lda #SPLIT_DELAY_BAD
+       sta split_delay
        rts

; Split IRQ (line SPLIT_IRQ_LINE): black band, then the HUD at YSCROLL 7.
;
; The two mode changes (W1 black on, W4 black off) are written in the right
; border of the line before ($d6, $de), never at the start of a line: a write
; near cycle 12 of a bad line is held up by the DMA until cycle 55 and the
; whole line would come out wrong. Raster poll jitter is 7 cycles; the
; delay puts the write at cycles 60-66 (VICE numbering), between the end of
; the picture (57) and the start of the next line's (~74, or 12 if bad).
; Sprites must stay off lines $d3-$df: their DMA would move these writes.
video_irq_split
        ldx split_w1
        ldy split_delay
        lda #BAND_TOP-1
-       cmp VIC_RASTER
        bne -
-       dey
        bne -
split_w1_at
        stx VIC_CTRL1           ; W1: black from line $d7 on, YSCROLL unchanged
        cpx #D011_ON | D011_ECM | 7
        beq _band               ; y = 7: YSCROLL is already 7, $d7 is row 20's
                                ; bad line and nothing else matches before $df
        lda #BAND_TOP
-       cmp VIC_RASTER
        bne -
        lda #D011_ON | D011_ECM | 3
        sta VIC_CTRL1           ; W2: YSCROLL 3 matches none of $d7/$d8 (with
                                ; y = 0, YSCROLL 7 here would match $d7 itself)
        lda #BAND_TOP+1
-       cmp VIC_RASTER
        bne -
        lda #D011_ON | D011_ECM | 7
        sta VIC_CTRL1           ; W3: YSCROLL 7, next match is $df
_band   ldx #D011_ON | 7
        ldy #SPLIT_DELAY
        lda #HUD_TOP-1
-       cmp VIC_RASTER
        bne -
-       dey
        bne -
split_w4
        stx VIC_CTRL1           ; W4: valid mode, row 21 (HUD) starts at $df
        rts

d018_values
        .byte D018_A, D018_B

; ---------------------------------------------------------------------------
; Main loop part: one stage of the hidden buffer, then the scroll position.
video_frame
        lda copy_stage
        cmp #COPY_STAGES
        bcs scroll_advance
        lda scroll_cmd          ; swap still waiting for the IRQ: screens not
        and #8                  ; exchanged yet
        bne scroll_advance
        lda copy_stage
        asl a
        ora cur_buf
        asl a
        tax
        lda copy_jumps,x
        sta ptr2
        lda copy_jumps+1,x
        sta ptr2+1
        jsr copy_go
copy_done                       ; tests: end of a build stage
        inc copy_stage
        jmp scroll_advance
copy_go jmp (ptr2)

; Fine/coarse position: scroll_y += speed; a wrap needs the hidden buffer.
scroll_advance
        lda scroll_frac
        clc
        adc speed_lo
        sta scroll_frac
        lda scroll_y
        adc speed_hi
        cmp #8
        bcc _fine
        ldx copy_stage
        cpx #COPY_STAGES
        bcc _stall
        sbc #8                  ; carry set
        ora #8                  ; coarse step
        ldx #0
        stx copy_stage
        sta scroll_cmd
        and #7
        sta scroll_y
        rts
_stall  inc stalls              ; hidden buffer not ready: hold at 7
        lda #0
        sta scroll_frac
        lda #7
_fine   sta scroll_y
        sta scroll_cmd
        rts

copy_jumps
        .word copy_ab0, copy_ba0, copy_ab1, copy_ba1

; copy rows first..first+COPY_ROWS-1 of src to rows +1 of dst
copy_rows .macro src, dst, first
        ldx #39
-       .for row = \first, row < \first + COPY_ROWS, row += 1
        lda \src + row*40,x
        sta \dst + (row+1)*40,x
        .endfor
        dex
        bpl -
        .endm

copy_ab0 #copy_rows SCREEN_A, SCREEN_B, 0
        rts
copy_ba0 #copy_rows SCREEN_B, SCREEN_A, 0
        rts
copy_ab1 #copy_rows SCREEN_A, SCREEN_B, COPY_ROWS
        lda #<SCREEN_B
        ldx #>SCREEN_B
        jmp new_row
copy_ba1 #copy_rows SCREEN_B, SCREEN_A, COPY_ROWS
        lda #<SCREEN_A
        ldx #>SCREEN_A
; row 0 of the hidden screen (A/X) = world row disp_top + 1
new_row
        sta ptr
        stx ptr+1
        lda disp_top
        clc
        adc #1
        jmp render_row

; ---------------------------------------------------------------------------
; World row A (low byte) -> 40 characters at (ptr). Phase 1 test pattern:
; character (row + column) & 63, so every row is different and checkable.
render_row
        sta tmp+1
        ldy #0
-       tya
        clc
        adc tmp+1
        and #$3f
        sta (ptr),y
        iny
        cpy #40
        bne -
        rts

; colour RAM of the playfield columns (bit 3 = multicolor)
col_colours
        .fill 9, 8 | GREEN      ; left side
        .fill 21, 8 | YELLOW    ; three tracks
        .fill 10, 8 | GREEN     ; right side

hud_text
        .enc "screen"
        .text "  score 000000  hi 000000  coins 00     "
        .enc "none"
