; =============================================================================
; Coins and power-ups (the CPC's pickups.asm), score, stations.
;
; Items live in the row descriptors (D_ITEM). A coin is a character of its
; row (render_row); a power-up is sprite 6, placed every frame over the row
; render_row last saw one in (one at a time: they are 50+ rows apart). The
; runner takes the item of the cell under its feet if it is not more than one
; level above that cell. A coin taken goes back to the track's character in
; the screen shown and, if its row has already been copied there, in the
; hidden one (put_cell).
;
; Magnet: coins of the runner's lane and the lanes next to it that reach
; MAGNET_LINE leave the track and fly to the runner as sprites 3-5.
;
; Labels (a power-up's or a station's name) are characters written into
; screen row LABEL_ROW, centred on the track: part of the picture from then
; on, they scroll down with it.
;
; Score (BCD, 6 digits): 1 point per row run (2 with turbo), 10 per coin
; (20 with the ticket); Piraeus 1000. Timers: the CPC's x 2 (50 Hz).
; =============================================================================

TURBO_EXTRA     = $0166                 ; turbo: + 1.4 pixels a frame ...
TURBO_MAX       = $0400                 ; ... up to 4.0 (the double buffer: 2 frames a row)
COIN_POINTS     = $10                   ; BCD
MAGNET_LINE     = FOOT_Y - 72           ; coins take off here (the CPC's 176)
FLYERS          = 3                     ; sprites 3-5
FLY_STEP_X      = 10                    ; hires pixels a frame (the CPC's 5 bytes)
FLY_STEP_Y      = 12                    ; lines a frame (the CPC's 24 a game frame)
FLY_DX          = 24 - 4                ; sprite x - runner centre: the coin centred
FLY_DY          = 14                    ; ... and on its chest
PU_DY           = 14                    ; power-up sprite y = first line of its row - 14
PU_Y_MAX        = $bc                   ; sprites stay above the split ($d3)
LABEL_ROW       = 8                     ; screen row of the countdown's labels
MSG_FRAMES      = 100                   ; a name in the HUD: 2 s
PU_TIMERS       = 6

pickups_init
        ldx #KSTATE_SIZE-1
        lda #0
-       sta kstate,x
        dex
        bpl -
        lda #1
        sta station_next
        lda #ROUTE_FIRST
        sta route_x
        rts

; -----------------------------------------------------------------------------
; play_pickups: after collide, while running
; -----------------------------------------------------------------------------
play_pickups
        lda game_state
        bne _ret
        lda no_pickups
        bne _ret
        jsr pickups
        jsr magnet
        jsr tick_powerups
        jmp stations
_ret    rts

; the item under the feet (collide's probe)
pickups
        lda arc_len                     ; in the air: over the items
        bne _ret
        lda player_z                    ; at most one level above the cell
        sec
        sbc support
        bcc _ret
        cmp #2
        bcs _ret
        lda feet_row
        jsr desc_index
        lda probe_lane
        sta pk_lane
        clc
        adc #D_ITEM
        tay
        lda (dp),y
        beq _ret
        pha
        lda #0
        sta (dp),y
        pla
        cmp #ITEM_COIN
        bne activate_powerup
        lda disp_top                    ; its screen row (the feet: on screen)
        sec
        sbc feet_row
        tax
        jsr erase_coin
        jmp collect_coin
_ret    rts

; A = item 2..7
activate_powerup
        ldx #SFX_POWERUP
        stx sfx_request
        pha
        clc
        adc #TXT_PU_MAGNET - ITEM_MAGNET
        ldx #MSG_FRAMES                 ; its name in the HUD
        jsr hud_message
        pla
        cmp #ITEM_HELMET
        bne _timed
        sta helmet                      ; non-zero: one crash absorbed
        rts
_timed  ldx #0
        cmp #ITEM_TURBO                 ; turbo and slow cancel each other
        bne +
        stx pu_slow
        stx pu_slow+1
+       cmp #ITEM_SLOW
        bne +
        stx pu_turbo
        stx pu_turbo+1
+       sec
        sbc #ITEM_MAGNET
        asl a
        tax
        lda pu_durations,x
        sta pu_timers,x
        lda pu_durations+1,x
        sta pu_timers+1,x
        rts

; frames, by item 2..7 (the helmet has no timer): 10 s, 8 s, 8 s, 10 s, -, 15 s
pu_durations    .word 500, 400, 400, 500, 0, 750

tick_powerups
        ldx #(PU_TIMERS-1)*2
_timer  lda pu_timers,x
        bne _lo
        lda pu_timers+1,x
        beq _idle
        dec pu_timers+1,x
_lo     dec pu_timers,x
_idle   dex
        dex
        bpl _timer
        rts

; eff_lo/hi = pixels a frame for the scroll: turbo, slow or speed_lo/hi
current_speed
        lda pu_slow
        ora pu_slow+1
        beq _not_slow
        lda speed_hi                    ; slow: half
        lsr a
        sta eff_hi
        lda speed_lo
        ror a
        sta eff_lo
        rts
_not_slow
        lda speed_lo
        sta eff_lo
        lda speed_hi
        sta eff_hi
        lda pu_turbo
        ora pu_turbo+1
        beq _ret
        lda speed_lo                    ; turbo: + TURBO_EXTRA ...
        clc
        adc #<TURBO_EXTRA
        sta eff_lo
        lda speed_hi
        adc #>TURBO_EXTRA
        sta eff_hi
        lda #<TURBO_MAX                 ; ... at most TURBO_MAX
        cmp eff_lo
        lda #>TURBO_MAX
        sbc eff_hi
        bcs _ret
        lda speed_lo                    ; (or the speed itself if it is higher)
        cmp #<TURBO_MAX
        lda speed_hi
        sbc #>TURBO_MAX
        bcs _base
        lda #<TURBO_MAX
        sta eff_lo
        lda #>TURBO_MAX
        sta eff_hi
        rts
_base   lda speed_lo
        sta eff_lo
        lda speed_hi
        sta eff_hi
_ret    rts

; -----------------------------------------------------------------------------
; score_row: the world moved one row (video.asm, coarse step)
; -----------------------------------------------------------------------------
score_row
        jsr route_row                   ; the runner on the HUD's route
        inc distance
        bne +
        inc distance+1
+       lda pu_turbo                    ; turbo: double distance points
        ora pu_turbo+1
        beq +
        lda #2
        bne score_add
+       lda #1
        ; fall through

; A = BCD points (0-99) added to the 6-digit BCD score (saturates at 999999)
score_add
        ldx #0
; ... A added at byte X of the score (1: hundreds)
score_add_x
        php                             ; no IRQ in decimal mode
        sei
        sed
        clc
        adc score,x
        sta score,x
        bcc _done
-       inx
        cpx #3
        beq _full
        lda score,x
        clc
        adc #1
        sta score,x
        bcs -
        bcc _done
_full   lda #$99
        sta score
        sta score+1
        sta score+2
_done   cld
        plp
        rts

; a coin: +1 coin (BCD, saturates at 9999), +10 points (+20 with the ticket)
collect_coin
        lda #SFX_COIN
        sta sfx_request
        php
        sei
        sed
        lda coins
        clc
        adc #1
        tax
        lda coins+1
        adc #0
        bcs +
        stx coins
        sta coins+1
+       cld
        plp
        lda pu_ticket
        ora pu_ticket+1
        beq +
        lda #COIN_POINTS*2
        bne score_add
+       lda #COIN_POINTS
        bne score_add

piraeus_bonus                           ; 1000 points
        lda #$10
        ldx #1
        bne score_add_x

; -----------------------------------------------------------------------------
; X = screen row (picture shown), pk_lane = lane, dp = the row's descriptor:
; the coin's character back to the track's
; -----------------------------------------------------------------------------
erase_coin
        cpx #PF_ROWS
        bcs _ret
        ldy #D_FLAGS                    ; a bridge row has no coins drawn
        lda (dp),y
        bmi _ret
        lda pk_lane
        clc
        adc #D_LANES
        tay
        lda (dp),y
        tay
        lda track_chars_lo,y
        sta ptr4
        lda track_chars_hi,y
        sta ptr4+1
        ldy #COIN_COL
        lda (ptr4),y
        pha
        ldy pk_lane
        lda lane_x,y
        clc
        adc #COIN_COL
        tay
        pla
        jmp put_cell
_ret    rts

; A = character, X = screen row of the picture shown (0-20), Y = column:
; written there, and in the hidden screen too (row + 1) if the build of the
; next picture has already copied that row
put_cell
        sta pc_char
        stx pc_row
        lda screen_a_lo,x
        sta ptr4
        lda screen_a_hi,x
        ldx cur_buf
        beq +
        clc
        adc #>(SCREEN_B - SCREEN_A)
+       sta ptr4+1
        lda pc_char
        sta (ptr4),y
        ldx pc_row
        cpx #PF_ROWS-1                  ; row 20 is never copied
        bcs _ret
        lda scroll_cmd                  ; a swap still waiting: all copied
        and #8
        bne _hidden
        lda copy_stage
        beq _ret                        ; nothing copied yet
        cpx #COPY_ROWS0
        bcc _hidden                     ; rows 0-7: stage 0
        cmp #2
        bcc _ret                        ; rows 8-19: stage 1
_hidden lda screen_a_lo+1,x
        sta ptr4
        lda screen_a_hi+1,x
        ldx cur_buf
        bne +
        clc
        adc #>(SCREEN_B - SCREEN_A)
+       sta ptr4+1
        lda pc_char
        sta (ptr4),y
_ret    rts

; -----------------------------------------------------------------------------
; magnet: while it runs, the coins near the runner's lane that reach
; MAGNET_LINE take off as flying sprites
; -----------------------------------------------------------------------------
magnet
        lda pu_magnet
        ora pu_magnet+1
        beq _ret
        lda #MAGNET_LINE - SCREEN_FIRST ; screen row at the magnet line
        sec
        sbc shown_y
        lsr a
        lsr a
        lsr a
        sta mg_row
        lda disp_top
        sec
        sbc mg_row
        jsr desc_index
        ldx #0
_lane   stx pk_lane
        txa                             ; |lane - player_lane| <= 1
        sec
        sbc player_lane
        bcs +
        eor #$ff
        adc #1
+       cmp #2
        bcs _next
        txa
        clc
        adc #D_ITEM
        tay
        lda (dp),y
        cmp #ITEM_COIN
        bne _next
        ldx #FLYERS-1                   ; a free flyer
-       lda fly_on,x
        beq _free
        dex
        bpl -
_ret    rts                             ; all flying
_free   lda #0
        sta (dp),y
        lda #1
        sta fly_on,x
        ldy pk_lane                     ; where the coin's character was
        lda lane_x,y
        clc
        adc #COIN_COL
        asl a
        asl a
        asl a
        adc #24
        sta fly_x,x
        lda mg_row
        asl a
        asl a
        asl a
        adc #SCREEN_FIRST
        adc shown_y
        sta fly_y,x
        ldx mg_row
        jsr erase_coin
_next   ldx pk_lane
        inx
        cpx #3
        bne _lane
        rts

; every flying coin heads for the runner's chest; collected when it gets there
move_flyers
        lda player_z                    ; target y = FOOT_Y - FLY_DY - 2z
        asl a
        eor #$ff
        sec
        adc #FOOT_Y - FLY_DY
        sta fly_ty
        lda player_centre
        clc
        adc #FLY_DX
        sta fly_tx
        ldx #FLYERS-1
_slot   lda fly_on,x
        beq _next
        ldy #0                          ; Y = axes still on their way
        lda fly_tx                      ; x: FLY_STEP_X towards the target
        sec
        sbc fly_x,x
        beq _x_done
        iny
        bcc _left
        cmp #FLY_STEP_X
        bcc +
        lda #FLY_STEP_X
+       clc
        adc fly_x,x
        sta fly_x,x
        jmp _x_done
_left   eor #$ff
        adc #1                          ; (carry clear)
        cmp #FLY_STEP_X
        bcc +
        lda #FLY_STEP_X
+       sta t8
        lda fly_x,x
        sec
        sbc t8
        sta fly_x,x
_x_done lda fly_ty                      ; y: down, FLY_STEP_Y at a time
        sec
        sbc fly_y,x
        beq _y_done
        bcc _y_done                     ; already below: stays
        iny
        cmp #FLY_STEP_Y
        bcc +
        lda #FLY_STEP_Y
+       clc
        adc fly_y,x
        sta fly_y,x
_y_done tya
        bne _next
        sta fly_on,x                    ; arrived
        stx fly_k
        jsr collect_coin
        ldx fly_k
_next   dex
        bpl _slot
        rts

; -----------------------------------------------------------------------------
; stations: when the runner reaches a station row, its name on the track;
; Piraeus gives 1000 points and the route starts over
; -----------------------------------------------------------------------------
stations
        lda feet_row
        cmp station_seen
        bne +
        lda feet_row+1
        cmp station_seen+1
        beq _ret
+       lda feet_row
        sta station_seen
        lda feet_row+1
        sta station_seen+1
        lda feet_row
        jsr desc_index
        ldy #D_FLAGS
        lda (dp),y
        and #F_STATION
        beq _ret
        lda #SFX_SIGNAL                 ; the bell
        sta sfx_request
        lda station_next                ; 1 Corinth .. 6 Piraeus
        tax
        inx
        cpx #ROUTE_STATIONS
        bcc +
        ldx #1
+       stx station_next
        pha
        jsr route_to_station
        pla
        cmp #ROUTE_STATIONS-1
        bne +
        pha
        jsr piraeus_bonus
        pla
+       clc
        adc #TXT_STATION_1-1
        ldx #MSG_FRAMES
        jmp hud_message
_ret    rts

; A = text number, X = screen row: written there, centred on the track
; (the countdown: the world stands still)
show_label_at
        stx lb_row
        jsr text_addr                   ; ptr5, Y = length (screens.asm)
        sty lb_col
        lda #3*TRACK_COLS + 1           ; first column: centred
        sec
        sbc lb_col
        lsr a
        clc
        adc #LEFT_COLS
        sta lb_col
        ldy #0
_char   sty lb_i
        lda (ptr5),y
        cmp #TEXT_END
        beq _ret
        pha
        tya
        clc
        adc lb_col
        tay
        pla
        ldx lb_row
        jsr put_cell
        ldy lb_i
        iny
        bne _char
_ret    rts

; -----------------------------------------------------------------------------
; coin_spin: up to SPINNERS coins of the picture turn at a time: a coin's
; character goes through its phases (png2c64: consecutive codes) and back,
; SPIN_FRAMES frames each; then another coin, picked at random, starts.
; Written with put_cell (the screen shown, and the hidden one if copied). A
; coin taken, under a bridge or off the screen stops. Its own random numbers
; (the world's are the CPC's).
; -----------------------------------------------------------------------------
SPINNERS        = 3
SPIN_FRAMES     = 3

coin_spin
        lda no_pickups
        bne _ret
        ldx #SPINNERS-1
_one    stx spin_i
        lda spin_phase,x
        bne _going
        jsr spin_start
        jmp _next
_going  dec spin_wait,x
        bne _next
        lda #SPIN_FRAMES
        sta spin_wait,x
        inc spin_phase,x
        lda spin_phase,x
        cmp #COIN_PHASES
        bcc +
        lda #0                          ; round: the plain coin again
        sta spin_phase,x
+       jsr spin_draw
_next   ldx spin_i
        dex
        bpl _one
_ret    rts

; X = a spinner: a coin picked at random starts (or none this frame)
spin_start
        jsr spin_rnd
        lsr a
        lsr a
        lsr a                           ; 0-31
        cmp #PF_ROWS-1                  ; rows 0-19
        bcs _ret
        sta t8
        jsr spin_rnd
        rol a
        rol a
        rol a
        and #3                          ; (the top bits)
        cmp #3
        bcs _ret
        sta t8b
        lda disp_top                    ; its world row
        sec
        sbc t8
        sta t8c
        lda disp_top+1
        sbc #0
        sta t16
        ldy #SPINNERS-1                 ; not one already turning
-       lda spin_phase,y
        beq +
        lda spin_row,y
        cmp t8c
        bne +
        lda spin_lane,y
        cmp t8b
        beq _ret
+       dey
        bpl -
        lda t8c
        sta spin_row,x
        lda t16
        sta spin_row_hi,x
        lda t8b
        sta spin_lane,x
        lda #1
        sta spin_phase,x
        lda #SPIN_FRAMES
        sta spin_wait,x
        jmp spin_draw
_ret    rts

; X = a spinner (kept): its coin's character for its phase; no coin there
; any more (or off the screen, or a bridge row): it stops
spin_draw
        lda disp_top
        sec
        sbc spin_row,x
        sta t8                          ; screen row
        lda disp_top+1
        sbc spin_row_hi,x
        bne _stop
        lda t8
        cmp #PF_ROWS-1
        bcs _stop
        lda spin_row,x
        jsr desc_index
        ldy #D_FLAGS
        lda (dp),y
        bmi _stop
        lda spin_lane,x
        clc
        adc #D_ITEM
        tay
        lda (dp),y
        cmp #ITEM_COIN
        bne _stop
        tya
        sec
        sbc #D_ITEM-D_COLL
        tay
        lda (dp),y
        and #15
        ldy #CH_COIN_RAIL
        cmp #COL_TRAIN
        bne +
        ldy #CH_COIN_ROOF
+       tya
        clc
        adc spin_phase,x
        pha
        ldy spin_lane,x
        lda lane_x,y
        clc
        adc #COIN_COL
        tay
        stx spin_x
        ldx t8
        pla
        jsr put_cell
        ldx spin_x
        rts
_stop   lda #0
        sta spin_phase,x
        rts

; A = the next of the spinners' own random numbers (x * 5 + 59)
spin_rnd
        lda spin_seed
        asl a
        asl a
        clc
        adc spin_seed
        clc
        adc #59
        sta spin_seed
        rts

; -----------------------------------------------------------------------------
; pickup_sprites: after player_sprites. Sprite 6 the power-up on the track,
; sprites 3-5 the flying coins.
; -----------------------------------------------------------------------------
pickup_sprites
        lda vis_kind
        beq _flyers
        lda vis_row                     ; still there?
        jsr desc_index
        lda vis_lane
        clc
        adc #D_ITEM
        tay
        lda (dp),y
        beq _forget                     ; picked up
        lda scroll_cmd                  ; e = next top row - its row
        lsr a
        lsr a
        lsr a
        and #1
        clc
        adc disp_top
        tax
        lda disp_top+1
        adc #0
        sta t8
        txa
        sec
        sbc vis_row
        tax
        lda t8
        sbc vis_row+1
        bmi _flyers                     ; not on the screen yet
        bne _forget
        cpx #PF_ROWS
        bcs _forget                     ; gone past the bottom
        txa
        asl a
        asl a
        asl a
        sta t8
        lda scroll_cmd
        and #7
        clc
        adc t8
        adc #SCREEN_FIRST - PU_DY
        cmp #PU_Y_MAX + 1
        bcs _flyers                     ; too low: the split
        sta spr_y+6
        ldx vis_lane
        lda lane_centres,x
        clc
        adc #12
        sta spr_x+6
        ldx vis_kind
        lda pu_blocks-ITEM_MAGNET,x
        sta spr_ptr+6
        lda pu_colours-ITEM_MAGNET,x
        sta spr_col6
        lda spr_ena
        ora #$40
        sta spr_ena
        jmp _flyers
_forget lda #0
        sta vis_kind
_flyers lda #SPRITE_BLOCK0 + SPR_FLYERS_COIN0 ; the whole coin (edge on, it
        sta t8                          ; is 2 pixels wide in flight)
        ldx #FLYERS-1
-       lda fly_on,x
        beq +
        lda fly_x,x
        sta spr_x+3,x
        lda fly_y,x
        sta spr_y+3,x
        lda t8
        sta spr_ptr+3,x
        lda spr_ena
        ora fly_bits,x
        sta spr_ena
+       dex
        bpl -
        rts

fly_bits        .byte $08, $10, $20
pu_blocks       .byte SPRITE_BLOCK0 + SPR_POWERUPS_MAGNET, SPRITE_BLOCK0 + SPR_POWERUPS_TURBO
                .byte SPRITE_BLOCK0 + SPR_POWERUPS_SLOW, SPRITE_BLOCK0 + SPR_POWERUPS_SPRING
                .byte SPRITE_BLOCK0 + SPR_POWERUPS_HELMET, SPRITE_BLOCK0 + SPR_POWERUPS_TICKET
pu_colours      .byte SPR_POWERUPS_MAGNET_COL, SPR_POWERUPS_TURBO_COL, SPR_POWERUPS_SLOW_COL
                .byte SPR_POWERUPS_SPRING_COL, SPR_POWERUPS_HELMET_COL, SPR_POWERUPS_TICKET_COL

; -----------------------------------------------------------------------------
; state (cleared by pickups_init)
; -----------------------------------------------------------------------------
        .virtual KSTATE
kstate
score           .fill 3                 ; BCD, low byte first
coins           .fill 2                 ; BCD, low byte first
distance        .word ?                 ; rows run
pu_timers                               ; frames left, by item 2..7
pu_magnet       .word ?
pu_turbo        .word ?
pu_slow         .word ?
pu_spring       .word ?
pu_helmet       .word ?                 ; (unused: the helmet has no timer)
pu_ticket       .word ?
fly_on          .fill FLYERS
fly_x           .fill FLYERS            ; sprite x
fly_y           .fill FLYERS            ; sprite y
fly_tx          .byte ?
fly_ty          .byte ?
fly_k           .byte ?
vis_kind        .byte ?                 ; the power-up render_row drew (0: none)
vis_lane        .byte ?
vis_row         .word ?                 ; its world row
station_seen    .word ?
station_next    .byte ?
no_pickups      .byte ?                 ; test switch: no items, no labels
msg_timer       .byte ?                 ; frames the HUD message stays (hud.asm)
spin_row        .fill SPINNERS          ; coin_spin: the coin's world row,
spin_row_hi     .fill SPINNERS
spin_lane       .fill SPINNERS          ; its lane,
spin_phase      .fill SPINNERS          ; its phase (0: not turning)
spin_wait       .fill SPINNERS          ; frames to the next phase
spin_i          .byte ?
spin_x          .byte ?
spin_seed       .byte ?
route_x         .byte ?                 ; HUD column of the runner on the route
route_sub       .byte ?                 ; rows into that column
hud_shown                               ; what the HUD shows ($ff: nothing yet)
shown_score     .fill 3
shown_hi        .fill 3
shown_coins     .fill 2
shown_lives     .byte ?
shown_route     .byte ?
shown_pu        .fill 6
HUD_SHOWN_SIZE  = * - hud_shown
KSTATE_SIZE     = * - kstate
        .endv
