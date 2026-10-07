; =============================================================================
; Sound: a SID music player and the effects. sound_tick runs 50 times a
; second from the IRQ (after the split), whatever the main loop is doing.
;
; The music (tools/mkmusic64.py, music/*.txt): three channels, one a voice.
; Each reads an order list (patterns, transposes, the loop) and its patterns
; (notes, lengths in ticks, instruments). An instrument sets the envelope,
; a wavetable (one step a tick: waveform and a note, relative or absolute:
; arpeggios, drums), a pulse width sweeping up and down, a vibrato after a
; delay and, for the bass, the low-pass filter closing from a cutoff. On a
; note's last tick the gate goes off with the envelope at 0 (a hard
; restart: the next note always starts from its attack).
;
; The tune follows game_mode: TUNE_GAME while playing, TUNE_OVER on the game
; over screen (once), TUNE_MENU on the other screens.
;
; Effects on voice 3: the game asks for one by writing its number to
; sfx_request; a higher priority effect interrupts a lower one, never the
; other way round. While one plays it has voice 3 (the music's third
; channel goes on unheard). The steps set the sustain level to their
; volume with an instant attack and decay: the level follows the steps.
;
; The registers are worked out in shadows and all written every tick.
; sound_on = 0 or the pause: volume 0; music_on = 0 (M, the menu): the
; music's voices without their gate.
; =============================================================================

SID             = $d400
SID_CUTOFF      = $d416
SID_ROUTE       = $d417                 ; resonance, the voices through the filter
SID_VOLUME      = $d418                 ; filter mode, volume
SID_ENV3        = $d41c
FILTER_LP       = $10
WAVE_NOISE      = $81
WAVE_TRIANGLE   = $11

sound_init
        ldx #$18
        lda #0
-       sta SID,x
        dex
        bpl -
        ldx #SSTATE_SIZE-1
-       sta sstate,x
        dex
        bpl -
        lda #$ff
        sta snd_tune
        rts

; -----------------------------------------------------------------------------
; sound_tick: one 1/50 s step (IRQ)
; -----------------------------------------------------------------------------
sound_tick
        lda SID_ENV3                    ; voice 3's envelope, as the SID has it (tests)
        sta snd_env3
        ldx #TUNE_GAME                  ; the tune for this screen
        lda game_mode
        beq +
        ldx #TUNE_OVER
        cmp #MODE_OVER
        beq +
        ldx #TUNE_MENU
+       cpx snd_tune
        beq +
        jsr start_tune
+       ldx #0
        jsr channel_tick
        ldx #1
        jsr channel_tick
        ldx #2
        jsr channel_tick
        jsr filter_tick
        jsr sfx_tick
        inc snd_ticks                   ; (tests)

        ; --- the shadows to the SID ---
        lda #FILTER_LP | 15
        ldx sound_on
        beq _mute
        ldx paused
        beq +
_mute   lda #FILTER_LP
+       sta SID_VOLUME
        ldx #$ff                        ; music off: no gate on its voices
        lda music_on
        bne +
        ldx #$fe
+       stx t8_irq
        .for v = 0, v < 3, v += 1
        .if v == 2
        lda sfx_on
        bne _sfx
        .endif
        lda sid_freq_lo+v
        sta SID+7*v
        lda sid_freq_hi+v
        sta SID+1+7*v
        lda ch_pw_lo+v
        sta SID+2+7*v
        lda ch_pw_hi+v
        sta SID+3+7*v
        lda sid_ad+v
        sta SID+5+7*v
        lda sid_sr+v
        sta SID+6+7*v
        lda sid_ctrl+v
        and t8_irq
        sta SID+4+7*v
        .endfor
        lda ch_flt+2                    ; the filter: voices 1-3 (3 not with an effect)
        bpl _route                      ; (always)
_sfx    lda sfx_freq_lo
        sta SID+14
        lda sfx_freq_hi
        sta SID+15
        lda sfx_ad
        sta SID+19
        lda sfx_sr
        sta SID+20
        lda sfx_ctrl
        sta SID+18
        lda #0
_route  asl a
        ora ch_flt+1
        asl a
        ora ch_flt
        ora flt_res
        sta SID_ROUTE
        lda flt_cut
        sta SID_CUTOFF
        rts

; X = tune: the three channels from its start
start_tune
        stx snd_tune
        stx t8_irq
        txa
        asl a
        adc t8_irq
        tay                             ; Y = 3 * tune
        ldx #0
-       lda tune_ord_lo,y
        sta ch_ord_lo,x
        lda tune_ord_hi,y
        sta ch_ord_hi,x
        lda #<pat_none                  ; the first tick reads the order list
        sta ch_pat_lo,x
        lda #>pat_none
        sta ch_pat_hi,x
        lda #0
        sta ch_ord_pos,x
        sta ch_trans,x
        sta ch_ins,x
        sta ch_dur,x
        sta ch_gate,x
        sta ch_live,x
        sta ch_stop,x
        sta ch_flt,x
        sta ch_pw_lo,x
        sta ch_pw_hi,x
        sta sid_freq_lo,x
        sta sid_freq_hi,x
        sta sid_ctrl,x
        sta sid_ad,x
        sta sid_sr,x
        lda #1
        sta ch_ticks,x
        iny
        inx
        cpx #3
        bne -
        lda #0
        sta flt_cut
        sta flt_spd
        sta flt_res
        rts

pat_none .byte P_END

; X = channel: a tick of its music
channel_tick
        lda ch_stop,x
        beq +
        lda sid_ctrl,x                  ; the tune is over: silent
        and #$fe
        sta sid_ctrl,x
        rts
+       dec ch_ticks,x
        beq _event
        lda ch_ticks,x
        cmp #1
        bne +
        lda #0                          ; the note's last tick: hard restart
        sta ch_gate,x
        sta sid_ad,x
        sta sid_sr,x
+       jmp effects

_event  lda ch_pat_lo,x
        sta snd_ptr
        lda ch_pat_hi,x
        sta snd_ptr+1
        ldy #0
_ev     lda (snd_ptr),y
        iny
        cmp #P_LEN
        bcc +
        sbc #P_LEN-1                    ; a length
        sta ch_dur,x
        bcs _ev                         ; (always)
+       cmp #P_END
        bcc +
        jsr next_pattern                ; the pattern's end
        bcc _ev
        lda #1                          ; the tune's end
        sta ch_stop,x
        lda #0
        sta ch_gate,x
        lda sid_ctrl,x
        and #$fe
        sta sid_ctrl,x
        rts
+       cmp #P_INS
        bcc _note
        sbc #P_INS                      ; an instrument
        sta ch_ins,x
        bcs _ev                         ; (always)

_note   sta t8_irq                      ; a note, 0: a rest
        tya
        clc
        adc snd_ptr
        sta ch_pat_lo,x
        lda snd_ptr+1
        adc #0
        sta ch_pat_hi,x
        lda ch_dur,x
        sta ch_ticks,x
        lda t8_irq
        bne _play
        sta ch_gate,x
        jmp effects
_play   clc
        adc ch_trans,x
        sta ch_note,x
        ldy ch_ins,x
        lda ins_ad,y
        sta sid_ad,x
        lda ins_sr,y
        sta sid_sr,x
        lda ins_wt,y
        sta ch_wt,x
        lda ins_pw_lo,y
        sta ch_pw_lo,x
        lda ins_pw_hi,y
        sta ch_pw_hi,x
        lda ins_pws,y
        sta ch_pws,x
        lda ins_vdel,y
        sta ch_vdel,x
        lda ins_vhalf,y
        sta ch_vcnt,x
        lda #0
        sta ch_vacc_lo,x
        sta ch_vacc_hi,x
        sta ch_vdir,x
        lda ins_vdepth,y
        beq _novib
        sta t8b_irq                     ; the vibrato's step: the semitone >> depth
        ldy ch_note,x
        lda freq_lo+1,y
        sec
        sbc freq_lo,y
        sta ch_vamt_lo,x
        lda freq_hi+1,y
        sbc freq_hi,y
-       lsr a
        ror ch_vamt_lo,x
        dec t8b_irq
        bne -
        sta ch_vamt_hi,x
        ldy ch_ins,x
_novib  lda ins_fcut,y
        beq +
        sta flt_cut                     ; the filter from this note's cutoff
        lda ins_fspd,y
        sta flt_spd
        lda ins_fres,y
        sta flt_res
        lda #1
+       sta ch_flt,x
        lda #1
        sta ch_gate,x
        sta ch_live,x
        ; (on to the effects)

; X = channel: vibrato, wavetable step, pulse sweep
effects
        lda ch_live,x
        beq _ret
        ldy ch_ins,x
        lda ins_vdepth,y
        beq _wt
        lda ch_vdel,x
        beq +
        dec ch_vdel,x
        jmp _wt
+       lda ch_vdir,x
        bne _down
        clc
        lda ch_vacc_lo,x
        adc ch_vamt_lo,x
        sta ch_vacc_lo,x
        lda ch_vacc_hi,x
        adc ch_vamt_hi,x
        sta ch_vacc_hi,x
        jmp _turn
_down   sec
        lda ch_vacc_lo,x
        sbc ch_vamt_lo,x
        sta ch_vacc_lo,x
        lda ch_vacc_hi,x
        sbc ch_vamt_hi,x
        sta ch_vacc_hi,x
_turn   dec ch_vcnt,x
        bne _wt
        lda ins_vspd,y
        sta ch_vcnt,x
        lda ch_vdir,x
        eor #1
        sta ch_vdir,x

_wt     ldy ch_wt,x
        lda wt_wave,y
        cmp #WT_JUMP
        bne +
        lda wt_note,y
        tay
        lda wt_wave,y
+       ora ch_gate,x
        sta sid_ctrl,x
        lda wt_note,y
        sta t8_irq
        iny
        tya
        sta ch_wt,x
        lda t8_irq
        bmi +
        clc                             ; relative to the note
        adc ch_note,x
        .byte $2c                       ; (bit abs: skips the and)
+       and #$7f                        ; absolute
        tay
        lda freq_lo,y
        clc
        adc ch_vacc_lo,x
        sta sid_freq_lo,x
        lda freq_hi,y
        adc ch_vacc_hi,x
        sta sid_freq_hi,x

        ldy #0                          ; the pulse sweep, turning round at $200 / $e00
        lda ch_pws,x
        beq _ret
        bpl +
        dey
+       clc
        adc ch_pw_lo,x
        sta ch_pw_lo,x
        tya
        adc ch_pw_hi,x
        sta ch_pw_hi,x
        sec
        sbc #2
        cmp #12
        bcc _ret
        lda #0
        sec
        sbc ch_pws,x
        sta ch_pws,x
_ret    rts

; X = channel: its next pattern from the order list -> snd_ptr, Y = 0, C
; clear; C set: the tune is over
next_pattern
        lda ch_ord_lo,x
        sta ord_ptr
        lda ch_ord_hi,x
        sta ord_ptr+1
        ldy ch_ord_pos,x
_o      lda (ord_ptr),y
        iny
        cmp #O_LOOP
        bcc +
        bne _end                        ; O_END (C set)
        lda (ord_ptr),y                 ; the loop
        tay
        jmp _o
_end    rts
+       cmp #$80
        bcc +
        sbc #O_TRANS                    ; a transpose
        sta ch_trans,x
        jmp _o
+       sta t8b_irq                     ; a pattern
        tya
        sta ch_ord_pos,x
        ldy t8b_irq
        lda pat_lo,y
        sta snd_ptr
        lda pat_hi,y
        sta snd_ptr+1
        ldy #0
        clc
        rts

; the filter's cutoff sweeps, between CUT_MIN and CUT_MAX
filter_tick
        lda flt_spd
        beq _r
        bmi _neg
        clc
        adc flt_cut
        bcs +
        cmp #CUT_MAX
        bcc _st
+       lda #CUT_MAX
        bne _st
_neg    clc
        adc flt_cut
        bcc +
        cmp #CUT_MIN
        bcs _st
+       lda #CUT_MIN
_st     sta flt_cut
_r      rts

; effects on voice 3: takes sfx_request, plays one step a tick
sfx_tick
        ldx sfx_request
        beq _run
        lda #0
        sta sfx_request
        dex                             ; X = effect - 1
        lda sfx_on                      ; one playing with a higher priority?
        beq _take
        lda sfx_prio,x
        cmp sfx_now_prio
        bcc _run
_take   lda sfx_lo,x
        sta sfx_ptr
        lda sfx_hi,x
        sta sfx_ptr+1
        lda sfx_prio,x
        sta sfx_now_prio
        lda #1
        sta sfx_on
        lda #0                          ; retrigger: gate off for a moment
        sta SID+4+14
_run    lda sfx_on
        beq _quiet
        lda sfx_ptr
        sta snd_ptr
        lda sfx_ptr+1
        sta snd_ptr+1
        ldy #2
        lda (snd_ptr),y                 ; volume | flags
        cmp #SFX_END
        beq _done
        sta t8_irq
        and #$0f
        beq _silent
        asl a                           ; sustain = the step's volume
        asl a
        asl a
        asl a
        sta sfx_sr
        lda #$00                        ; instant attack and decay
        sta sfx_ad
        dey
        lda (snd_ptr),y
        sta sfx_freq_hi
        dey
        lda (snd_ptr),y
        sta sfx_freq_lo
        lda #WAVE_TRIANGLE              ; a tone ...
        bit t8_irq
        bvc +
        lda #WAVE_NOISE                 ; ... or the noise
+       sta sfx_ctrl
        jmp _step
_silent lda sfx_ctrl
        and #$fe
        sta sfx_ctrl
_step   lda sfx_ptr
        clc
        adc #3
        sta sfx_ptr
        bcc +
        inc sfx_ptr+1
+       rts
_done   lda #0                          ; voice 3 back to the music
        sta sfx_on
_quiet  rts

; -----------------------------------------------------------------------------
; state (sound_init)
; -----------------------------------------------------------------------------
        .virtual SSTATE
sstate
snd_tune        .byte ?                 ; tune playing ($ff: none yet)
snd_ticks       .byte ?                 ; ticks so far (tests)
snd_env3        .byte ?
t8_irq          .byte ?
t8b_irq         .byte ?
flt_cut         .byte ?                 ; the filter: cutoff (high byte), its sweep,
flt_spd         .byte ?                 ; resonance << 4
flt_res         .byte ?
ch_ord_lo       .fill 3                 ; by channel: the order list,
ch_ord_hi       .fill 3
ch_ord_pos      .fill 3                 ; the next entry in it,
ch_pat_lo       .fill 3                 ; the next event of the pattern
ch_pat_hi       .fill 3
ch_trans        .fill 3
ch_ticks        .fill 3                 ; ticks left of the note
ch_dur          .fill 3                 ; the pattern's length
ch_ins          .fill 3
ch_note         .fill 3                 ; the note playing (transposed)
ch_gate         .fill 3
ch_live         .fill 3                 ; a note has started
ch_stop         .fill 3                 ; the tune is over
ch_wt           .fill 3                 ; wavetable step
ch_pw_lo        .fill 3                 ; pulse width and its sweep
ch_pw_hi        .fill 3
ch_pws          .fill 3
ch_vdel         .fill 3                 ; vibrato: delay, ticks to the turn,
ch_vcnt         .fill 3                 ; direction, offset, step
ch_vdir         .fill 3
ch_vacc_lo      .fill 3
ch_vacc_hi      .fill 3
ch_vamt_lo      .fill 3
ch_vamt_hi      .fill 3
ch_flt          .fill 3                 ; through the filter
sid_freq_lo     .fill 3                 ; the music's registers
sid_freq_hi     .fill 3
sid_ctrl        .fill 3
sid_ad          .fill 3
sid_sr          .fill 3
sfx_on          .byte ?                 ; the effect playing on voice 3
sfx_ptr         .word ?
sfx_now_prio    .byte ?
sfx_freq_lo     .byte ?                 ; its registers
sfx_freq_hi     .byte ?
sfx_ctrl        .byte ?
sfx_ad          .byte ?
sfx_sr          .byte ?
SSTATE_SIZE     = * - sstate
        .endv
