; =============================================================================
; Sound (the CPC's sound.asm on the SID): voice 1 the melody, voice 2 the
; bass, voice 3 the effects. sound_tick runs 50 times a second from the IRQ
; (after the split), whatever the main loop is doing.
;
; The tune follows game_mode: TUNE_GAME while playing, TUNE_OVER on the game
; over screen (once), TUNE_MENU on the other screens. The game asks for an
; effect by writing its number to sfx_request; a higher priority effect
; interrupts a lower one, never the other way round.
;
; The voices' registers are worked out in sid_* (shadows) and all written
; every tick. sound_on = 0 or the pause: volume 0; music_on = 0 (M, the
; menu): voices 1 and 2 without their gate.
;
; Notes: gate on at the start, off on the last tick (so the next one
; starts again: the CPC halves the volume there). The CPC's volume decay
; from "top" to "floor" is the ADSR's decay to the sustain level. Effect
; steps set the sustain level to their volume with an instant attack and
; decay: the level follows the steps down.
; =============================================================================

SID             = $d400
SID_VOLUME      = $d418
SID_ENV3        = $d41c
WAVE_PULSE      = $41                   ; with the gate bit
WAVE_NOISE      = $81
WAVE_TRIANGLE   = $11

sound_init
        ldx #$18
        lda #0
-       sta SID,x
        dex
        bpl -
        lda #$00                        ; pulse widths: 50 %, 25 %, 50 %
        sta SID+2
        sta SID+2+7
        sta SID+2+14
        lda #$08
        sta SID+3
        sta SID+3+14
        lda #$04
        sta SID+3+7
        ldx #SSTATE_SIZE-1
        lda #0
-       sta sstate,x
        dex
        bpl -
        lda #$ff
        sta snd_tune
        ldx #1                          ; the music voices' envelopes
-       lda voice_ad,x
        sta sid_ad,x
        lda voice_sr,x
        sta sid_sr,x
        dex
        bpl -
        rts

voice_ad        .byte $03, $03          ; attack 2 ms, decay 72 ms ...
voice_sr        .byte $93, $83          ; ... to 9 / 8 (the CPC's floors), release 72 ms
voice_wave      .byte WAVE_PULSE, WAVE_PULSE

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
        jsr sfx_tick
        inc snd_ticks                   ; (tests)

        ; --- the shadows to the SID ---
        lda #$0f
        ldx sound_on
        beq _mute
        ldx paused
        beq +
_mute   lda #0
+       sta SID_VOLUME
        ldx #$ff                        ; music off: no gate on voices 1-2
        lda music_on
        bne +
        ldx #$fe
+       stx t8_irq
        .for v = 0, v < 3, v += 1
        lda sid_freq_lo+v
        sta SID+7*v
        lda sid_freq_hi+v
        sta SID+1+7*v
        lda sid_ad+v
        sta SID+5+7*v
        lda sid_sr+v
        sta SID+6+7*v
        lda sid_ctrl+v
        .if v < 2
        and t8_irq
        .endif
        sta SID+4+7*v
        .endfor
        rts

; X = tune: both channels from its start
start_tune
        stx snd_tune
        lda tune_a_lo,x
        sta ch_ptr_lo
        sta ch_start_lo
        lda tune_a_hi,x
        sta ch_ptr_hi
        sta ch_start_hi
        lda tune_b_lo,x
        sta ch_ptr_lo+1
        sta ch_start_lo+1
        lda tune_b_hi,x
        sta ch_ptr_hi+1
        sta ch_start_hi+1
        lda #1                          ; the first notes on this tick
        sta ch_ticks
        sta ch_ticks+1
        rts

; X = channel 0 (melody, voice 1) / 1 (bass, voice 2)
channel_tick
        dec ch_ticks,x
        beq _next
        lda ch_ticks,x                  ; the last tick of a note: gate off
        cmp #1
        bne _ret
        lda sid_ctrl,x
        and #$fe
        sta sid_ctrl,x
_ret    rts
_next   lda ch_ptr_lo,x
        sta snd_ptr
        lda ch_ptr_hi,x
        sta snd_ptr+1
        ldy #0
        lda (snd_ptr),y
        cmp #TUNE_LOOP
        bne _not_loop
        lda ch_start_lo,x
        sta snd_ptr
        lda ch_start_hi,x
        sta snd_ptr+1
        lda (snd_ptr),y
_not_loop
        cmp #TUNE_STOP
        bne _note
        lda #1                          ; stays on the end mark, silent
        sta ch_ticks,x
        lda sid_ctrl,x
        and #$fe
        sta sid_ctrl,x
        rts
_note   sta t8_irq                      ; note (0: rest)
        iny
        lda (snd_ptr),y
        sta ch_ticks,x
        lda snd_ptr
        clc
        adc #2
        sta ch_ptr_lo,x
        lda snd_ptr+1
        adc #0
        sta ch_ptr_hi,x
        ldy t8_irq
        beq _rest
        lda freq_lo,y
        sta sid_freq_lo,x
        lda freq_hi,y
        sta sid_freq_hi,x
        lda voice_wave,x                ; gate on
        sta sid_ctrl,x
        rts
_rest   lda sid_ctrl,x
        and #$fe
        sta sid_ctrl,x
        rts

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
        sta sid_sr+2
        lda #$00                        ; instant attack and decay
        sta sid_ad+2
        dey
        lda (snd_ptr),y
        sta sid_freq_hi+2
        dey
        lda (snd_ptr),y
        sta sid_freq_lo+2
        lda #WAVE_TRIANGLE              ; a tone ...
        bit t8_irq
        bvc +
        lda #WAVE_NOISE                 ; ... or the noise
+       sta sid_ctrl+2
        jmp _step
_silent lda sid_ctrl+2
        and #$fe
        sta sid_ctrl+2
_step   lda sfx_ptr
        clc
        adc #3
        sta sfx_ptr
        bcc +
        inc sfx_ptr+1
+       rts
_done   lda #0
        sta sfx_on
_quiet  lda sid_ctrl+2
        and #$fe
        sta sid_ctrl+2
        rts

; -----------------------------------------------------------------------------
; state (sound_init)
; -----------------------------------------------------------------------------
        .virtual SSTATE
sstate
snd_tune        .byte ?                 ; tune playing ($ff: none yet)
snd_ticks       .byte ?                 ; ticks so far (tests)
snd_env3        .byte ?
ch_ptr_lo       .fill 2                 ; next event, by channel
ch_ptr_hi       .fill 2
ch_start_lo     .fill 2                 ; loop point
ch_start_hi     .fill 2
ch_ticks        .fill 2                 ; ticks left of the note
sfx_on          .byte ?
sfx_ptr         .word ?
sfx_now_prio    .byte ?
t8_irq          .byte ?
sid_freq_lo     .fill 3                 ; the voices' registers
sid_freq_hi     .fill 3
sid_ctrl        .fill 3
sid_ad          .fill 3
sid_sr          .fill 3
SSTATE_SIZE     = * - sstate
        .endv
