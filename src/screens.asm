; =============================================================================
; Screens and game flow (the CPC's screens.asm): menu, controls, story, high
; scores, game over with name entry, the countdown, pause, RUN/STOP.
;
; A still screen (game_mode >= MODE_MENU) stops the world: no scroll, no
; sprites, YSCROLL 7 (rows 0-19 whole), the screen shown cleared and the
; texts written into it once (screen_dirty). Its rows use the menu charset
; ($6000: the game's font at the same codes, then the logo) on black; the
; split IRQ puts the game's charset back for the HUD, which stays.
; The logo's second half needs another MC2 (grey for orange): irq_logo
; changes $D023 between logo rows 2 and 3.
;
; Texts in two languages (text/*.txt, tools/mktext64.py): L switches on the
; menu, controls, story and high score screens.
; =============================================================================

MODE_PLAY       = 0
MODE_MENU       = 2                     ; >= MODE_MENU: a still screen
MODE_CONTROLS   = 3
MODE_SCORES     = 4
MODE_OVER       = 5
MODE_STORY      = 6

MENU_ITEMS      = 7
MENU_ROW        = 7                     ; first option
MENU_X          = 14
CURSOR_X        = MENU_X - 2
LOGO_X          = (40 - LOGO_W) / 2
LOGO_SWITCH     = $37 + 3*8 - 1         ; last line of logo row 2 (YSCROLL 7)
LOGO_IRQ_LINE   = LOGO_SWITCH - 2
TEXT_CENTRE     = $ff
HISCORES        = 8
HS_SIZE         = 6                     ; score (3, BCD, low first), name (3 letters 0-25)
NAME_LETTERS    = 3
COUNT_STEP      = 40                    ; frames a number (the CPC's 20)
COUNT_ROW       = LABEL_ROW + 3
HINT_FRAMES     = 100                   ; hard: the wagons hint before the numbers
SKILL_HARD      = 2

D018_MENU_A     = ((SCREEN_A & $3fff) >> 6) | ((MENU_CHARSET & $3fff) >> 10)
D018_MENU_B     = ((SCREEN_B & $3fff) >> 6) | ((MENU_CHARSET & $3fff) >> 10)

; -----------------------------------------------------------------------------
; boot: defaults, the saved table if there is one, then the menu
; -----------------------------------------------------------------------------
flow_init
        ldx #MSTATE_SIZE-1
        lda #0
-       sta mstate,x
        dex
        bpl -
        ldx #3
-       lda score_magic,x
        sta scores_file,x
        dex
        bpl -
        ldx #HISCORES*HS_SIZE-1
-       lda default_scores,x
        sta hiscore_table,x
        dex
        bpl -
        lda #1
        sta music_on
        sta sound_on
        jsr load_scores                 ; disk.asm
        ; fall through

; best = the table's first score
best_from_table
        ldx #2
-       lda hiscore_table,x
        sta best,x
        dex
        bpl -
        rts

score_magic     .text "APER"            ; SCORES starts with it
default_scores                          ; the CPC's
        .byte $00, $00, $02, 0, 15, 4   ; APE 20000
        .byte $00, $50, $01, 17, 20, 13 ; RUN 15000
        .byte $00, $20, $01, 15, 8, 17  ; PIR 12000
        .byte $00, $00, $01, 0, 19, 7   ; ATH 10000
        .byte $00, $75, $00, 10, 8, 5   ; KIF  7500
        .byte $00, $50, $00, 13, 4, 14  ; NEO  5000
        .byte $00, $25, $00, 12, 0, 17  ; MAR  2500
        .byte $00, $10, $00, 5, 0, 11   ; FAL  1000

; -----------------------------------------------------------------------------
; mode changes
; -----------------------------------------------------------------------------
go_menu
        lda #MODE_MENU
set_screen
        sta game_mode
        lda #1
        sta screen_dirty
        lda #0
        sta paused
        sta countdown
        sta spr_ena
        lda #7                          ; YSCROLL 7, no swap: the screen
        sta scroll_cmd                  ; shown stays
        rts

; the menu's START: a new game at the chosen skill, after the countdown
start_game
        jsr game_start
        ldx skill
        lda skill_speeds,x
        sta speed_hi
        lda skill_speeds_lo,x
        sta speed_lo
        lda #COUNT_STEP*3 + COUNT_STEP/2
        ldx gap_hard                    ; hard: the wagons hint first
        beq +
        lda #COUNT_STEP*3 + COUNT_STEP/2 + HINT_FRAMES
+       sta countdown
        lda #1
        sta count_first
        rts
; pixels a frame: 1.5, 2.0, 2.5. The CPC's 4, 5, 6 lines a game frame would
; be 2.0, 2.5, 3.0, but the C64 shows 145 lines ahead of the feet, the CPC
; 248: the time to see an obstacle coming is 1.9 / 1.45 / 1.16 s this way
; (the CPC's: 2.5 / 2.0 / 1.65 s).
skill_speeds    .byte 1, 2, 2
skill_speeds_lo .byte $80, $00, $80

; game_state_update: the game-over wait is over
game_finished
        lda #MODE_OVER
        jsr set_screen
        lda #0
        sta name_pos
        sta name_buf
        sta name_buf+1
        sta name_buf+2
        sta over_named
        jsr score_rank
        sta over_rank
        rts

; -----------------------------------------------------------------------------
; play_input: a playing frame, after read_input. C clear: the game runs this
; frame; C set: it does not (countdown, pause, or a still screen now).
; -----------------------------------------------------------------------------
play_input
        lda countdown
        beq _playing
        dec countdown
        bne _counting
        lda #TXT_PU_GO                  ; GO!: the game runs
        ldx #COUNT_ROW
        jsr show_label_at
        clc
        rts
_counting
        ldx count_first                 ; first frame, hard: the hint
        beq _numbers
        ldx #0
        stx count_first
        ldx gap_hard
        beq _numbers
        lda #TXT_PU_WAGONS
        ldx #LABEL_ROW
        jsr show_label_at
_numbers
        lda countdown
        ldx #TXT_PU_3                   ; 3, 2, 1 with 120, 80, 40 frames left
        cmp #COUNT_STEP*3
        beq _show
        inx
        cmp #COUNT_STEP*2
        beq _show
        inx
        cmp #COUNT_STEP
        bne _wait
_show   txa
        ldx #COUNT_ROW
        jsr show_label_at
_wait   sec
        rts
_playing
        lda keys_pressed
        and #KEY_ESC
        beq +
        jsr go_menu
        sec
        rts
+       jsr key_m                       ; M: music on/off
        beq +
        lda music_on
        eor #1
        sta music_on
+       lda keys_pressed                ; H: pause
        and #KEY_PAUSE
        beq +
        lda paused
        eor #1
        sta paused
        jsr pause_label
+       lda paused
        lsr a                           ; C = paused
        rts

; PAUSE over the HUD's route while paused
pause_label
        lda paused
        bne +
        jmp hud_route                   ; the route back
+       ldx #39                         ; the route row blank
        lda #FONT_SPACE
-       sta HUD_A+40,x
        sta HUD_B+40,x
        dex
        bpl -
        lda #TXT_PAUSE
        jsr text_addr
        sty t8
        tya                             ; centred
        eor #$ff
        sec
        adc #40
        lsr a
        tax
        ldy #0
-       lda (ptr5),y
        sta HUD_A+40,x
        sta HUD_B+40,x
        lda #8 | WHITE
        sta HUD_CRAM+40,x
        inx
        iny
        cpy t8
        bne -
        rts

; -----------------------------------------------------------------------------
; key_l / key_m: NZ if the key went down since the last call (matrix edges)
; -----------------------------------------------------------------------------
key_l
        lda #%11011111                  ; column 5, row 2
        ldx #%00000100
        ldy #0
        beq key_edge
key_m
        lda #%11101111                  ; column 4, row 4
        ldx #%00010000
        ldy #1
key_edge
        sta CIA1_PRA
        stx t8
        lda CIA1_PRB
        ldx #$ff
        stx CIA1_PRA
        and t8                          ; 0: down
        ldx test_mode                   ; tests: never down
        beq +
        lda t8
+       ldx #0
        cmp t8
        beq +
        inx                             ; X = 1: down now
+       lda key_down,y                  ; before
        eor #1
        sta t8
        txa
        sta key_down,y
        and t8                          ; down now, up before
        rts

; -----------------------------------------------------------------------------
; screen_frame: a frame of a still screen
; -----------------------------------------------------------------------------
screen_frame
        lda #0                          ; no sprites
        sta spr_ena
        lda game_mode
        cmp #MODE_OVER
        beq +
        jsr key_l                       ; L: the other language
        beq +
        lda language
        eor #1
        sta language
        lda #1
        sta screen_dirty
+       lda screen_dirty
        beq +
        jsr draw_screen
+       lda game_mode
        cmp #MODE_MENU
        beq menu_frame
        cmp #MODE_OVER
        bne +
        jmp over_frame
+       lda keys_pressed                ; controls, story, scores: back
        and #KEY_FIRE | KEY_ESC
        beq +
        jmp go_menu
+       rts

menu_frame
        lda keys_pressed
        beq _ret
        tax
        and #KEY_UP
        beq _not_up
        lda menu_sel
        beq _ret
        dec menu_sel
        jmp menu_cursor
_not_up txa
        and #KEY_DOWN
        beq _not_down
        lda menu_sel
        cmp #MENU_ITEMS-1
        beq _ret
        inc menu_sel
        jmp menu_cursor
_not_down
        txa
        and #KEY_FIRE
        beq _ret
        lda menu_sel
        bne +
        jmp start_game
+       cmp #4
        bcs _option
        tax                             ; 1-3: controls, scores, story
        lda menu_modes-1,x
        jmp set_screen
_option bne _flag                       ; 4: easy, medium, hard
        ldx skill
        inx
        cpx #3
        bcc +
        ldx #0
+       stx skill
        jmp _redraw
_flag   cmp #5                          ; 5: music, 6: sound
        bne +
        lda music_on
        eor #1
        sta music_on
        jmp _redraw
+       lda sound_on
        eor #1
        sta sound_on
_redraw lda #1
        sta screen_dirty
_ret    rts
menu_modes      .byte MODE_CONTROLS, MODE_SCORES, MODE_STORY

over_frame
        lda over_rank
        cmp #HISCORES
        bcs _done                       ; no record: wait for fire
        lda name_pos
        cmp #NAME_LETTERS
        bcs _done
        ldx name_pos
        lda keys_pressed
        and #KEY_UP
        beq _not_up
        lda name_buf,x
        clc
        adc #1
        cmp #26
        bcc _set
        lda #0
        beq _set
_not_up lda keys_pressed
        and #KEY_DOWN
        beq _not_down
        lda name_buf,x
        sec
        sbc #1
        bcs _set
        lda #25
_set    sta name_buf,x
        jmp draw_name
_not_down
        lda keys_pressed
        and #KEY_FIRE
        beq _ret
        inc name_pos
        lda name_pos
        cmp #NAME_LETTERS
        beq +
        jmp draw_name
+       jsr draw_name                   ; (the marker off)
        jsr insert_score
        jsr best_from_table
        jsr save_scores                 ; disk.asm
        lda #1
        sta over_named
        lda #WHITE
        sta text_colour
        lda #TXT_OVER_CONTINUE
        ldx #19
        ldy #TEXT_CENTRE
        jmp draw_text
_done   lda keys_pressed
        and #KEY_FIRE | KEY_ESC
        beq _ret
        lda #MODE_SCORES
        jmp set_screen
_ret    rts

; -----------------------------------------------------------------------------
; draw_screen: the whole still screen of the mode
; -----------------------------------------------------------------------------
draw_screen
        lda #0
        sta screen_dirty
        jsr screen_clear
        lda #YELLOW
        sta text_colour
        lda game_mode
        cmp #MODE_CONTROLS
        bne +
        jmp draw_controls
+       cmp #MODE_SCORES
        bne +
        jmp draw_scores
+       cmp #MODE_OVER
        bne +
        jmp draw_over
+       cmp #MODE_STORY
        bne draw_menu
        jmp draw_story

draw_menu
        ldx #0                          ; the logo
_logo   stx t8c
        txa
        tay                             ; Y = logo row
        lda logo_rows_lo,y
        sta ptr2
        lda logo_rows_hi,y
        sta ptr2+1
        lda logo_cols_lo,y
        sta ptr5
        lda logo_cols_hi,y
        sta ptr5+1
        ldx t8c
        lda #LOGO_X
        jsr row_ptrs
        ldy #LOGO_W-1
-       lda (ptr2),y
        sta (ptr4),y
        lda (ptr5),y
        sta (ptr3),y
        dey
        bpl -
        ldx t8c
        inx
        cpx #LOGO_H
        bne _logo
        lda #WHITE                      ; the options
        sta text_colour
        ldx #0
-       stx t8c
        lda menu_texts,x
        ldy menu_vars,x                 ; + skill / music / sound
        beq +
        clc
        adc 0,y
+       sta menu_texts_now
        txa
        clc
        adc #MENU_ROW
        tax
        ldy #MENU_X
        lda menu_texts_now
        jsr draw_text
        ldx t8c
        inx
        cpx #MENU_ITEMS
        bne -
        lda #CYAN
        sta text_colour
        lda #TXT_MENU_HINT
        ldx #15
        ldy #TEXT_CENTRE
        jsr draw_text
        lda #TXT_MENU_LANG
        ldx #16
        ldy #TEXT_CENTRE
        jsr draw_text
        lda #GREEN
        sta text_colour
        lda #TXT_MENU_CREDIT
        ldx #17
        ldy #TEXT_CENTRE
        jsr draw_text
        lda #TXT_MENU_CREDIT2
        ldx #18
        ldy #TEXT_CENTRE
        jsr draw_text
        lda #TXT_MENU_CREDIT3
        ldx #19
        ldy #TEXT_CENTRE
        jsr draw_text
        ; fall through

; the cursor in front of option menu_sel (the others: blank)
menu_cursor
        ldx #MENU_ITEMS-1
-       stx t8c
        lda #CURSOR_X
        pha
        txa
        clc
        adc #MENU_ROW
        tax
        pla
        jsr row_ptrs
        ldx t8c
        lda #FONT_SPACE
        cpx menu_sel
        bne +
        lda #FONT_RIGHT
+       ldy #0
        sta (ptr4),y
        lda #8 | YELLOW
        sta (ptr3),y
        dex
        bpl -
        rts

menu_texts      .byte TXT_MENU_START, TXT_MENU_CONTROLS, TXT_MENU_SCORES, TXT_MENU_STORY
                .byte TXT_MENU_SKILL_0, TXT_MENU_MUSIC_OFF, TXT_MENU_SOUND_OFF
menu_vars       .byte 0, 0, 0, 0, skill, music_on, sound_on
logo_rows_lo    .byte <(logo_chars + range(LOGO_H) * LOGO_W)
logo_rows_hi    .byte >(logo_chars + range(LOGO_H) * LOGO_W)
logo_cols_lo    .byte <(logo_colours + range(LOGO_H) * LOGO_W)
logo_cols_hi    .byte >(logo_colours + range(LOGO_H) * LOGO_W)

draw_controls
        lda #TXT_CONTROLS_TITLE
        ldx #1
        ldy #TEXT_CENTRE
        jsr draw_text
        lda #WHITE
        sta text_colour
        ldx #0
-       stx t8c
        txa
        asl a
        adc #3                          ; rows 3, 5, .. 17
        tax
        lda t8c
        clc
        adc #TXT_CONTROLS_LEFT
        ldy #6
        jsr draw_text
        ldx t8c
        inx
        cpx #TXT_CONTROLS_BACK - TXT_CONTROLS_LEFT
        bne -
draw_back
        lda #CYAN
        sta text_colour
        lda #TXT_CONTROLS_BACK
        ldx #19
        ldy #TEXT_CENTRE
        jmp draw_text

draw_story
        lda #TXT_STORY_TITLE
        ldx #1
        ldy #TEXT_CENTRE
        jsr draw_text
        lda #WHITE
        sta text_colour
        ldx #0
-       stx t8c
        txa
        clc
        adc #3                          ; rows 3-17
        tax
        lda t8c
        clc
        adc #TXT_STORY_1
        ldy #TEXT_CENTRE
        jsr draw_text
        ldx t8c
        inx
        cpx #15
        bne -
        jmp draw_back

draw_scores
        lda #TXT_SCORES_TITLE
        ldx #1
        ldy #TEXT_CENTRE
        jsr draw_text
        lda #WHITE
        sta text_colour
        ldx #0
_entry  stx t8c                         ; "N. ABC 012345"
        txa
        asl a
        sta t8b
        asl a
        adc t8b
        sta t8b                         ; table offset = 6 * place
        txa
        clc
        adc #FONT_N0 + 1
        sta text_buf
        lda #FONT_DOT
        sta text_buf+1
        lda #FONT_SPACE
        sta text_buf+2
        sta text_buf+6
        ldy t8b
        ldx #0
-       lda hiscore_table+3,y
        clc
        adc #FONT_A
        sta text_buf+3,x
        iny
        inx
        cpx #NAME_LETTERS
        bne -
        lda t8b
        clc
        adc #<(hiscore_table+2)         ; most significant byte
        sta ptr2
        lda #>(hiscore_table+2)
        adc #0
        sta ptr2+1
        ldx #7
        lda #3
        jsr bcd_text
        ldx t8c                         ; rows 3, 5, .. 17
        txa
        asl a
        adc #3
        tax
        ldy #13                         ; length
        lda #TEXT_CENTRE
        jsr draw_buf
        ldx t8c
        inx
        cpx #HISCORES
        bne _entry
        jmp draw_back

draw_over
        lda #TXT_OVER_TITLE
        ldx #1
        ldy #TEXT_CENTRE
        jsr draw_text
        lda #WHITE
        sta text_colour
        lda #TXT_OVER_SCORE
        ldx #4
        ldy #8
        jsr draw_text
        lda #<(score+2)
        sta ptr2
        lda #>(score+2)
        sta ptr2+1
        ldx #0
        lda #3
        jsr bcd_text
        ldx #4
        ldy #6
        lda #26
        jsr draw_buf
        lda #TXT_OVER_COINS
        ldx #6
        ldy #8
        jsr draw_text
        lda #<(coins+1)
        sta ptr2
        lda #>(coins+1)
        sta ptr2+1
        ldx #0
        lda #2
        jsr bcd_text
        ldx #6
        ldy #4
        lda #28
        jsr draw_buf
        lda #TXT_OVER_DIST
        ldx #8
        ldy #8
        jsr draw_text
        jsr dec_text                    ; distance, 5 digits
        ldx #8
        ldy #5
        lda #27
        jsr draw_buf
        lda over_rank
        cmp #HISCORES
        bcs _no_record
        lda #YELLOW
        sta text_colour
        lda #TXT_OVER_RECORD
        ldx #11
        ldy #TEXT_CENTRE
        jsr draw_text
        lda #WHITE
        sta text_colour
        lda #TXT_OVER_NAME
        ldx #13
        ldy #12
        jsr draw_text
        lda #CYAN
        sta text_colour
        lda #TXT_OVER_NAME_HINT
        ldx #16
        ldy #TEXT_CENTRE
        jsr draw_text
        jmp draw_name
_no_record
        lda #TXT_OVER_CONTINUE
        ldx #19
        ldy #TEXT_CENTRE
        jmp draw_text

; the name being entered (row 13) and the marker under its letter (row 14)
draw_name
        ldx #NAME_LETTERS-1
-       lda name_buf,x
        clc
        adc #FONT_A
        sta text_buf,x
        lda #FONT_SPACE
        cpx name_pos
        bne +
        lda #FONT_UP
+       sta text_buf+NAME_LETTERS,x
        dex
        bpl -
        lda #YELLOW
        sta text_colour
        ldx #13
        ldy #NAME_LETTERS
        lda #NAME_X
        jsr draw_buf
        ldx #NAME_LETTERS-1
-       lda text_buf+NAME_LETTERS,x
        sta text_buf,x
        dex
        bpl -
        ldx #14
        ldy #NAME_LETTERS
        lda #NAME_X
        jmp draw_buf
NAME_X          = 20

; -----------------------------------------------------------------------------
; the high score table
; -----------------------------------------------------------------------------
; A = place of the score in the table (HISCORES: none). Equal: below.
score_rank
        ldy #0
        ldx #0
_entry  lda score+2
        cmp hiscore_table+2,y
        bcc _lower
        bne _higher
        lda score+1
        cmp hiscore_table+1,y
        bcc _lower
        bne _higher
        lda score
        cmp hiscore_table,y
        bcc _lower
        beq _lower
_higher txa
        rts
_lower  tya
        clc
        adc #HS_SIZE
        tay
        inx
        cpx #HISCORES
        bne _entry
        txa
        rts

; the score and name at over_rank, the ones below it one place down
insert_score
        lda over_rank
        cmp #HISCORES
        bcs _ret
        asl a                           ; offset = 6 * rank
        sta t8
        asl a
        adc t8
        sta t8
        ldx #(HISCORES-1)*HS_SIZE - 1   ; move down, from the end
-       cpx t8
        bcc +
        lda hiscore_table,x
        sta hiscore_table+HS_SIZE,x
        dex
        bpl -
+       ldx t8
        lda score
        sta hiscore_table,x
        lda score+1
        sta hiscore_table+1,x
        lda score+2
        sta hiscore_table+2,x
        lda name_buf
        sta hiscore_table+3,x
        lda name_buf+1
        sta hiscore_table+4,x
        lda name_buf+2
        sta hiscore_table+5,x
_ret    rts

; -----------------------------------------------------------------------------
; text output on the still screen (the screen shown, rows 0-20)
; -----------------------------------------------------------------------------
; A = text number -> ptr5 = its characters, Y = its length
text_addr
        ldx language
        beq +
-       clc
        adc #TXT_COUNT
        dex
        bne -
+       tax
        lda text_lo,x
        sta ptr5
        lda text_hi,x
        sta ptr5+1
        ldy #0
-       lda (ptr5),y
        cmp #TEXT_END
        beq +
        iny
        bne -
+       rts

; A = text, X = row, Y = column (TEXT_CENTRE: centred), in text_colour
draw_text
        sty dt_col
        stx dt_row
        jsr text_addr
        lda dt_col
        ldx dt_row
        jmp draw_ptr

; text_buf: A = column (TEXT_CENTRE), X = row, Y = length
draw_buf
        pha
        lda #<text_buf
        sta ptr5
        lda #>text_buf
        sta ptr5+1
        pla
; ptr5 = characters, Y = length, A = column (TEXT_CENTRE), X = row
draw_ptr
        cmp #TEXT_CENTRE
        bne +
        tya
        eor #$ff
        sec
        adc #40
        lsr a
+       jsr row_ptrs
        lda text_colour
        ora #8
        sta t8
        dey
        bmi _ret
-       lda (ptr5),y
        sta (ptr4),y
        lda t8
        sta (ptr3),y
        dey
        bpl -
_ret    rts

; X = row, A = column -> ptr4 = there in the screen shown, ptr3 = colour RAM
row_ptrs
        clc
        adc screen_a_lo,x
        sta ptr4
        sta ptr3
        lda screen_a_hi,x
        adc #0
        sta ptr3+1
        ldx cur_buf
        beq +
        clc
        adc #>(SCREEN_B - SCREEN_A)
+       sta ptr4+1
        lda ptr3+1
        clc
        adc #>(COLOR_RAM - SCREEN_A)
        sta ptr3+1
        rts

; A = bytes, ptr2 = the most significant one, X = position in text_buf: BCD digits
bcd_text
        sta t8
        ldy #0
-       lda (ptr2),y
        lsr a
        lsr a
        lsr a
        lsr a
        clc
        adc #FONT_N0
        sta text_buf,x
        inx
        lda (ptr2),y
        and #$0f
        clc
        adc #FONT_N0
        sta text_buf,x
        inx
        lda ptr2                        ; the next byte down
        bne +
        dec ptr2+1
+       dec ptr2
        dec t8
        bne -
        rts

; distance -> text_buf: 5 decimal digits
dec_text
        lda distance
        sta t16
        lda distance+1
        sta t16+1
        ldx #0
_digit  ldy #FONT_N0 - 1
-       iny
        lda t16
        sec
        sbc dec_lo,x
        sta t8
        lda t16+1
        sbc dec_hi,x
        bcc +
        sta t16+1
        lda t8
        sta t16
        jmp -
+       tya
        sta text_buf,x
        inx
        cpx #5
        bne _digit
        rts
dec_lo  .byte <10000, <1000, <100, <10, <1
dec_hi  .byte >10000, >1000, >100, >10, >1

; rows 0-20 of both screens blank, their colour RAM white
screen_clear
        ldx #0
-       lda #FONT_SPACE
        sta SCREEN_A,x
        sta SCREEN_A+$100,x
        sta SCREEN_A+$200,x
        sta SCREEN_B,x
        sta SCREEN_B+$100,x
        sta SCREEN_B+$200,x
        lda #8 | WHITE
        sta COLOR_RAM,x
        sta COLOR_RAM+$100,x
        sta COLOR_RAM+$200,x
        cpx #PF_ROWS*40 - $300
        bcs +
        sta COLOR_RAM+$300,x
        lda #FONT_SPACE
        sta SCREEN_A+$300,x
        sta SCREEN_B+$300,x
+       inx
        bne -
        rts

; -----------------------------------------------------------------------------
; IRQ side
; -----------------------------------------------------------------------------
; still screens: logo row 3 on, MC2 grey for orange
irq_logo_h
        lda #1
        sta VIC_IRQ
        lda #LOGO_SWITCH
-       cmp VIC_RASTER                  ; (no MC2 on this line or the next)
        bcc +
        bne -
+       lda #LOGO_MC2_BOTTOM
        sta VIC_BG2
        jmp irq_to_split

d018_menu       .byte D018_MENU_A, D018_MENU_B

; -----------------------------------------------------------------------------
; state, kept from game to game (flow_init at boot)
; -----------------------------------------------------------------------------
        .virtual MSTATE
mstate
scores_file                             ; SCORES: "APER", then the table
                .fill 4
hiscore_table   .fill HISCORES*HS_SIZE
SCORES_SIZE     = * - scores_file
menu_sel        .byte ?
screen_dirty    .byte ?
countdown       .byte ?                 ; frames left before the game runs
count_first     .byte ?
paused          .byte ?
key_down        .fill 2                 ; L, M (key_edge)
over_rank       .byte ?
over_named      .byte ?
name_pos        .byte ?
name_buf        .fill NAME_LETTERS
dt_row          .byte ?
dt_col          .byte ?
text_colour     .byte ?
menu_texts_now  .byte ?
text_buf        .fill 41
MSTATE_SIZE     = * - mstate
        .endv
