; =============================================================================
; The runner: lane changes, jumps, heights, ramps, roofs (the CPC's
; player.asm and the support half of its collide), and its sprites.
;
; Height levels z: 0 ground, 1 low jump, 2 train roof, 3 jump over a train /
; from the roof, 4 highest jump. player_base is the level it stands on (0
; ground, 2 roof). The CPC plays at 25 frames a second: here every step of
; an arc lasts 2 frames and a lane change takes 8 (the same times).
;
; Sprites: 0 the body (multicolor), 1 its outline (hires, black), 2 the
; shadow (airborne). The main loop works out their registers for the next
; frame (spr_*); the top IRQ writes them. Under a bridge deck the three are
; cut row by row (as the CPC's clip table): their pointers go to an empty
; block on the deck's first line and back after its last (clip IRQs).
; =============================================================================

FOOT_Y          = $c8                   ; raster line of the feet at z = 0
FEET_PROBE      = FOOT_Y - 1
FRONT_PROBE     = FOOT_Y - 5
LANE_X0         = LEFT_COLS * 8         ; hires x of the first lane
LANE_W          = TRACK_COLS * 8        ; 56
MOVE_FRAMES     = 8
SPRITE_BLOCK0   = (sprites - $4000) / 64
BLANK_BLOCK     = (sprite_blank - $4000) / 64
SCREEN_FIRST    = $30                   ; raster line of screen row 0 at YSCROLL 0

player_init
        ldx #PSTATE_SIZE-1
        lda #0
-       sta pstate,x
        dex
        bpl -
        lda #1
        sta player_lane
        lda #LANE_X0 + LANE_W + LANE_W/2
        sta player_centre
        rts

; -----------------------------------------------------------------------------
; player_update: one frame of movement from keys_pressed / keys_held
; -----------------------------------------------------------------------------
player_update
        ; --- lane change: a press made while moving waits its turn ---
        lda keys_pressed
        ldx #0
        lsr a                           ; KEY_LEFT
        bcc +
        ldx #$ff
+       lsr a                           ; KEY_RIGHT
        bcc +
        ldx #1
+       txa
        beq +
        sta move_queued
+       lda move_left
        bne _moving
        lda move_queued                 ; start a queued move if possible
        beq _jump
        tax
        lda #0
        sta move_queued
        txa
        clc
        adc player_lane
        cmp #3                          ; -1 or 3: off the track
        bcs _jump
        sta player_lane
        stx move_dir
        lda #MOVE_FRAMES
        sta move_left
_moving ldx move_left                   ; 8, 8, 8, 8, 6, 6, 6, 6 pixels
        lda move_steps-1,x
        ldx move_dir
        bmi +
        clc
        adc player_centre
        jmp ++
+       eor #$ff
        sec
        adc player_centre
+       sta player_centre
        dec move_left

        ; --- jumps ---
_jump   lda arc_len
        bne _in_air
        lda keys_pressed
        and #KEY_JUMP
        beq _on_ground
        ldx #ARC_ROOF
        lda player_base
        bne +
        ldx #ARC_GROUND
        lda pu_spring                   ; springs: super jump from the ground
        beq +
        ldx #ARC_SPRING
+       stx arc_ofs
        lda arcs,x
        asl a                           ; 2 frames a step
        sta arc_len
        lda player_base                 ; (collide: not descending yet)
        sta prev_z
        lda #0
        sta arc_index
_in_air lda arc_index                   ; the last step shown: back on the base
        cmp arc_len
        bcc _airborne
        lda #0
        sta arc_len
        beq _on_ground
_airborne
        lda keys_pressed                ; fast landing: on to the descent
        and #KEY_DOWN
        beq _step
        lda arc_len
        sec
        sbc #4                          ; (2 steps)
        cmp arc_index
        bcc _step
        beq _step
        sta arc_index
_step   lda arc_index
        lsr a
        sec                             ; + 1: past the length byte
        adc arc_ofs
        tax
        lda arcs,x
        sta player_z
        inc arc_index
        jmp _animate
_on_ground
        lda player_base
        sta player_z
_animate
        inc anim_tick
        rts

move_steps      .byte 6, 6, 6, 6, 8, 8, 8, 8   ; by frames left (8 first)

; arcs: length in steps, then z per step (the CPC's, a step = 2 frames)
arcs
ARC_GROUND = * - arcs
        .byte 12, 1,1,1,1,1,1,1,1,1,1,1,1
ARC_ROOF = * - arcs
        .byte 12, 3,3,4,4,4,4,4,4,4,4,3,3
ARC_SPRING = * - arcs
        .byte 16, 1,3,4,4,4,4,4,4,4,4,4,4,4,4,3,1
ARC_FALL = * - arcs
        .byte 2, 1,1                    ; from a roof (the base already lowered)

; -----------------------------------------------------------------------------
; collide (the support half): what the runner stands on. Front obstacles and
; crashes come in phase 5; until then a crash only counts (crashes) and the
; runner takes the level under it, as when protected.
; -----------------------------------------------------------------------------
collide
        jsr runner_lane
        sta probe_lane
        lda #FEET_PROBE                 ; support under the feet
        jsr cell_at
        ldx probe_row
        stx feet_row
        ldx probe_row+1
        stx feet_row+1
        jsr support_level
        sta support

        lda arc_len
        bne _airborne
        lda was_airborne                ; landing this frame?
        beq _walking
        lda #0
        sta was_airborne
        lda prev_z                      ; land on S if the jump reached it
        cmp support
        bcc _crash_feet                 ; jumped into the side of a train
        lda player_base
        cmp support
        beq _done
        bcc _set_base                   ; landed higher (roof)
        lda support                     ; landed lower: fall the rest
        jmp _drop

_walking
        lda player_base
        cmp support
        beq _done
        bcs _lower
        clc                             ; higher: one ramp step at a time
        adc #1
        cmp support
        bne _crash_feet                 ; walked into a train
_set_base
        lda support
        sta player_base
        sta player_z
        rts
_lower  lda support                     ; the ground dropped away
_drop   sta t8                          ; new base
        lda player_base
        sec
        sbc t8                          ; drop
        ldx t8
        stx player_base
        cmp #2
        bcc _small
        lda #ARC_FALL                   ; a visible fall from the roof
        sta arc_ofs
        lda #4
        sta arc_len
        lda #0
        sta arc_index
        lda t8
        clc
        adc #2
        sta player_z
        lda #1
        sta was_airborne
        rts
_small  stx player_z
        rts

_airborne
        lda prev_z                      ; descending onto a higher level?
        cmp player_z
        bcc _rising
        beq _rising
        lda support
        cmp player_z
        bcc _rising                     ; still above it
        lda prev_z
        cmp support
        bcc _rising                     ; was below it last frame
        lda player_base
        cmp support
        bcs _rising                     ; not higher than the base
        lda #0
        sta arc_len
        sta was_airborne
        lda support
        sta player_base
        sta player_z
        rts
_rising lda #1
        sta was_airborne
        lda player_z
        sta prev_z
_done   rts

_crash_feet
        inc crashes                     ; phase 5: crash / helmet / invulnerable
        lda support
        sta player_base
        sta player_z
        rts

; A = support level S of the cell class A / ramp row (cell_at)
support_level
        cmp #COL_GAP                    ; between two wagons: a roof, or a gap
        bne +                           ; to jump on hard
        ldx skill
        cpx #2
        bne _roof
        lda #0
        rts
+       cmp #COL_TRAIN
        beq _roof
        cmp #COL_NOSE
        beq _roof
        cmp #COL_RAMP_UP
        beq _up
        cmp #COL_RAMP_DOWN
        beq _down
        lda #0
        rts
_roof   lda #2
        rts
_up     lda ramp_row
        rts
_down   lda #2
        sec
        sbc ramp_row
        rts

; A = the lane under the runner (the one whose span holds its centre)
runner_lane
        lda player_centre
        sec
        sbc #LANE_X0
        ldx #0
-       sec
        sbc #LANE_W
        bcc +
        inx
        bne -
+       txa
        rts

; A = raster line, probe_lane = lane -> A = collision class, ramp_row,
; probe_row = its world row (the picture shown this frame)
cell_at
        sec
        sbc #SCREEN_FIRST
        sec
        sbc shown_y
        lsr a
        lsr a
        lsr a                           ; screen row
        sta t8
        lda disp_top
        sec
        sbc t8
        sta probe_row
        lda disp_top+1
        sbc #0
        sta probe_row+1
        lda probe_row
        jsr desc_index                  ; dp = its descriptor
        lda probe_lane
        clc
        adc #D_COLL
        tay
        lda (dp),y
        pha
        lsr a
        lsr a
        lsr a
        lsr a
        sta ramp_row
        pla
        and #15
        rts

; -----------------------------------------------------------------------------
; player_sprites: the sprite registers for the next frame (spr_*), and the
; lines where a bridge deck cuts them (clip_on / clip_off). After
; video_frame: scroll_cmd says where the picture will be.
; -----------------------------------------------------------------------------
player_sprites
        jsr runner_frame
        tax
        clc
        adc #SPRITE_BLOCK0
        sta spr_ptr
        txa
        adc #SPRITE_BLOCK0 + SPR_RUNNER_OUTLINE_S1_RUN0
        sta spr_ptr+1
        lda player_centre               ; x = centre - 12 + 24
        clc
        adc #12
        sta spr_x
        sta spr_x+1
        sta spr_x+2
        lda player_z                    ; y: bottom row on FOOT_Y - 2z
        asl a
        sta t8
        lda #FOOT_Y - 20
        sec
        sbc t8
        sta spr_y
        sta spr_y+1
        sta runner_top
        lda #%011                       ; the shadow only in the air
        ldx arc_len
        beq _shadow_done
        ldx #SPRITE_BLOCK0 + SPR_SHADOW_SH_GROUND
        lda player_base
        beq +
        ldx #SPRITE_BLOCK0 + SPR_SHADOW_SH_ROOF
+       stx spr_ptr+2
        asl a                           ; on the level it left
        sta t8
        lda #FOOT_Y - 20
        sec
        sbc t8
        sta spr_y+2
        lda #%111
_shadow_done
        sta spr_ena
        ; fall through

; bridge decks in lines runner_top .. FOOT_Y of the next picture
clip_lines
        lda #0
        sta clip_top                    ; cut from the top line on
        sta clip_on
        sta clip_off
        lda scroll_cmd
        and #7
        sta t8b                         ; next YSCROLL
        lda scroll_cmd
        lsr a
        lsr a
        lsr a
        and #1                          ; next top row = disp_top (+ 1)
        clc
        adc disp_top
        sta t16
        lda disp_top+1
        adc #0
        sta t16+1
        lda runner_top                  ; first screen row of the span
        sec
        sbc #SCREEN_FIRST
        sec
        sbc t8b
        lsr a
        lsr a
        lsr a
        sta t8c
_row    lda t16                         ; world row = next top - screen row
        sec
        sbc t8c
        jsr desc_index
        ldy #D_FLAGS
        lda (dp),y
        bpl _open
        ldy #D_LEFT                     ; the shadow rows do not cut
        lda (dp),y
        cmp #B_FOOTBRIDGE_SHADOW
        beq _open
        cmp #B_ROADBRIDGE_SHADOW
        beq _open
        jsr _row_line                   ; a deck row
        ldx clip_on
        bne +
        ldx clip_top                    ; (already cutting from the top)
        bne +
        cmp runner_top
        bcc _from_top
        beq _from_top
        sta clip_on
        jmp +
_from_top
        inc clip_top
+       clc
        adc #8
        sta clip_off                    ; the line after this deck row
        jmp _next
_open   lda clip_on                     ; a deck ended above this row
        ora clip_top
        bne _end
_next   inc t8c
        jsr _row_line
        cmp #FOOT_Y + 1
        bcc _row
_end    lda clip_off
        cmp #FOOT_Y + 1                 ; a deck to the bottom: no turning back
        bcc +
        lda #0
        sta clip_off
+       rts
; A = first line of screen row t8c in the next picture
_row_line
        lda t8c
        asl a
        asl a
        asl a
        clc
        adc #SCREEN_FIRST
        adc t8b
        rts

; A = the runner's frame (index of its sprite)
runner_frame
        lda arc_len
        beq _running
        lsr a                           ; rising: the first half of the arc
        cmp arc_index
        ldx player_z
        bcc +
        beq +
        lda jump_frames_up,x
        rts
+       lda jump_frames_down,x
        rts
_running
        lda move_left
        beq _run
        lda #SPR_RUNNER_S1_LEAN_L
        ldx move_dir
        bmi +
        lda #SPR_RUNNER_S1_LEAN_R
+       ldx player_base
        beq +
        clc
        adc #SPR_RUNNER_S3_RUN0 - SPR_RUNNER_S1_RUN0
+       rts
_run    lda anim_tick                   ; 4 frames, 4 picture frames each
        lsr a
        lsr a
        and #3
        ldx player_base
        beq +
        clc
        adc #SPR_RUNNER_S3_RUN0 - SPR_RUNNER_S1_RUN0
+       rts

jump_frames_up
        .byte SPR_RUNNER_S1_RUN0, SPR_RUNNER_S2_JUMP_UP, SPR_RUNNER_S3_JUMP_UP
        .byte SPR_RUNNER_S4_JUMP_UP, SPR_RUNNER_S5_JUMP
jump_frames_down
        .byte SPR_RUNNER_S1_RUN0, SPR_RUNNER_S2_JUMP_DOWN, SPR_RUNNER_S3_JUMP_DOWN
        .byte SPR_RUNNER_S4_JUMP_DOWN, SPR_RUNNER_S5_JUMP

; -----------------------------------------------------------------------------
; IRQ side: sprite registers (top IRQ), and the deck cuts (clip IRQs: the
; pointer of a line is fetched at the end of the line before, so the write
; happens on line L-1 for line L; the IRQ comes on L-2 and waits).
; -----------------------------------------------------------------------------
sprites_irq
        lda spr_ena
        sta VIC_SPR_ENA
        ldx #2
-       txa
        asl a
        tay
        lda spr_x,x
        sta VIC_SPR_X,y
        lda spr_y,x
        sta VIC_SPR_Y,y
        lda spr_ptr,x
        ldy clip_top
        beq +
        lda #BLANK_BLOCK
+       sta SCREEN_A + $3f8,x
        sta SCREEN_B + $3f8,x
        dex
        bpl -
        rts

; A = line L: wait for L-1, then the three pointers (empty or the frames)
clip_write
        sec
        sbc #1
-       cmp VIC_RASTER
        bne -
        ldx #2
-       lda clip_ptrs,x
        sta SCREEN_A + $3f8,x
        sta SCREEN_B + $3f8,x
        dex
        bpl -
        rts

; -----------------------------------------------------------------------------
; state
; -----------------------------------------------------------------------------
        .virtual PSTATE
pstate
player_lane     .byte ?
player_centre   .byte ?                 ; hires x of the feet
move_dir        .byte ?                 ; $ff left, 1 right
move_left       .byte ?                 ; frames of the lane change left
move_queued     .byte ?
player_base     .byte ?                 ; 0 ground, 2 roof
player_z        .byte ?
arc_ofs         .byte ?                 ; its arc in arcs
arc_len         .byte ?                 ; frames (0: not in the air)
arc_index       .byte ?
anim_tick       .byte ?
prev_z          .byte ?
was_airborne    .byte ?
support         .byte ?
probe_lane      .byte ?
ramp_row        .byte ?
probe_row       .word ?
feet_row        .word ?
crashes         .byte ?                 ; for tests
pu_spring       .byte ?                 ; phase 6
runner_top      .byte ?
spr_ena         .byte ?                 ; sprite registers for the next frame
spr_x           .fill 3
spr_y           .fill 3
spr_ptr         .fill 3
clip_top        .byte ?                 ; cut from the first line on
clip_on         .byte ?                 ; line where a deck starts cutting (0: none)
clip_off        .byte ?                 ; line after the deck (0: none)
clip_ptrs       .fill 3                 ; what clip_write writes
PSTATE_SIZE     = * - pstate
        .endv
