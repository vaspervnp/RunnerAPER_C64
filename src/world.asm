; =============================================================================
; World: generates one row at a time (world row n, growing upwards) into a
; ring of row descriptors, and draws a row as 40 characters.
;
; The generator is the CPC's (APERRunner src/world.asm, src/chunk_pick.asm),
; decision for decision and random number for random number, so a seed
; gives the same world; tools/worldgen.py is the same in Python, and the
; tests hold the two together (and the model against the CPC itself). The
; C64 leaves out moving trains and cars; its scenery (cars, trees, bushes)
; are side tiles instead of overlays (side_tiles).
; =============================================================================

; --- row descriptor ------------------------------------------------------------
ROW_SIZE        = 16
RING_ROWS       = 64
D_FLAGS         = 0
D_LEFT          = 1                     ; left side tile (a bridge row: its index)
D_RIGHT         = 2                     ; right side tile
D_LANES         = 3                     ; 3 track tiles
D_COLL          = 6                     ; 3 collision classes
D_ITEM          = 9                     ; 3 items
D_PLAT          = 12                    ; a station's platform: rows left
F_FOREST        = $01
F_STATION       = $02
F_PLATFORM      = $10
F_BRIDGE        = $80

COL_NONE        = 0
COL_STOP        = 1
COL_SIGNAL      = 2
COL_TRAIN       = 3
COL_NOSE        = 4
COL_RAMP_UP     = 5
COL_RAMP_DOWN   = 6
COL_GAP         = 7

ITEM_COIN       = 1
ITEM_MAGNET     = 2
ITEM_TURBO      = 3
ITEM_SLOW       = 4
ITEM_SPRING     = 5
ITEM_HELMET     = 6
ITEM_TICKET     = 7

SEGMENT_MIN     = 96
BRIDGE_GAP_MIN  = 80
SCENERY_MARGIN  = 6
SPACER_START    = 24
ROUTE_SEG       = 320
ROUTE_STATIONS  = 7
PU_GAP_MIN      = 50
PU_GAP_RANGE    = 70
PU_CLEAR        = 8
PU_TURBO_ODDS   = 77
CAR_QUIET_ROWS  = 12
SCENERY_W_MAX   = 20
EASY_WINDOW     = 34                    ; the CPC's picture
PLAT_ROWS       = 22
OVERLAYS        = 16
COIN_W          = 4
POWERUP_W       = 6
CAR_W           = 4

OBJ_TREE        = 1                     ; side objects (side_tiles)
OBJ_BUSH        = 2
OBJ_CAR         = 3
OBJ_BUS         = 4

; =============================================================================
; world_init: generator state for a new game (skill set)
; =============================================================================
world_init
        lda #0
        ldx #0
-       sta WORLD_RING,x
        sta WORLD_RING+$100,x
        sta WORLD_RING+$200,x
        sta WORLD_RING+$300,x
        inx
        bne -
        ldx #0
-       sta wstate,x
        inx
        cpx #WSTATE_SIZE
        bne -
        lda #<$ace1
        sta rng
        lda #>$ace1
        sta rng+1
        lda #SEGMENT_MIN
        sta seg_left
        lda #PU_GAP_MIN
        sta pu_gap
        lda #SPACER_START
        sta spacer_len
        sta spacer_left
        jsr spacer_step
        lda #BRIDGE_GAP_MIN/2
        sta bridge_countdown
        lda #24
        sta cross_countdown
        lda #30
        sta kiosk_countdown
        lda #50
        sta kiosk_countdown+1
        lda #<ROUTE_SEG
        sta route_left
        lda #>ROUTE_SEG
        sta route_left+1
        lda #PU_CLEAR                   ; nothing behind the start
        ldx #5
-       sta clear_rows,x
        dex
        bpl -
        rts

; =============================================================================
; rnd: A = next pseudo-random byte (xorshift16 7,9,8, as the CPC's).
; Preserves X, Y.
; =============================================================================
rnd
        lda rng+1
        lsr a
        lda rng
        ror a
        eor rng+1
        sta rng+1
        ror a
        eor rng
        sta rng
        eor rng+1
        sta rng+1
        rts

; A = random mod divisor. Preserves X, Y.
random_below
        jsr rnd
mod_divisor
-       cmp divisor
        bcc +
        sbc divisor
        bcs -
+       rts

; ring index A (0-63) -> dp = its descriptor
desc_index
        and #RING_ROWS-1
        tay
        lda desc_lo,y
        sta dp
        lda desc_hi,y
        sta dp+1
        rts

; =============================================================================
; generate_row: gen_row = world row; fills its descriptor (dp)
; =============================================================================
generate_row
        lda gen_row
        jsr desc_index
        ldy #ROW_SIZE-1
        lda #0
-       sta (dp),y
        dey
        bpl -
        sta base
        sta base+1
        sta started
        sta started+1

        ; difficulty 1..5: hi(n + skill * n/2) + 1
        lda gen_row+1
        lsr a
        sta t16b+1
        lda gen_row
        ror a
        sta t16b
        lda gen_row
        sta t16
        lda gen_row+1
        sta t16+1
        ldx skill
        beq _diff
-       clc
        lda t16
        adc t16b
        sta t16
        lda t16+1
        adc t16b+1
        sta t16+1
        bcs _diff_max
        dex
        bne -
_diff   lda t16+1
        clc
        adc #1
        cmp #6
        bcc _diff_ok
_diff_max
        lda #5
_diff_ok
        sta difficulty

        dec spacer_tick
        bne +
        jsr spacer_step
+
        ldx #BUSY_COUNT-1               ; cars, trees: rows until free again
-       lda busy_counters,x
        beq +
        dec busy_counters,x
+       dex
        bpl -

        lda route_left                  ; a station every ROUTE_SEG rows
        bne +
        dec route_left+1
+       dec route_left
        lda route_left
        ora route_left+1
        bne _route_done
        ldy #D_FLAGS
        lda (dp),y
        ora #F_STATION
        sta (dp),y
        lda #PLAT_ROWS
        sta plat_left
        ldx route_station
        inx
        cpx #ROUTE_STATIONS-1
        bcc +
        ldx #0
+       stx route_station
        lda #<ROUTE_SEG
        sta route_left
        lda #>ROUTE_SEG
        sta route_left+1
_route_done
        lda pu_gap                      ; rows to the next power-up
        ora pu_gap+1
        beq _pu_done
        lda pu_gap
        bne +
        dec pu_gap+1
+       dec pu_gap
_pu_done
        lda plat_left                   ; a platform: no scenery starts
        beq _no_plat
        ldy #D_PLAT
        sta (dp),y
        dec plat_left
        ldy #D_FLAGS
        lda (dp),y
        ora #F_PLATFORM
        sta (dp),y
        ldx #7                          ; car_busy, tree_busy
        lda #1
-       sta busy_counters,x
        dex
        bpl -
_no_plat

        ; --- environment ---
        lda trans_left
        beq +
        jsr transition_sides
        jmp _lanes
+       lda seg_left
        bne +
        dec seg_left+1
+       dec seg_left
        lda seg_left
        ora seg_left+1
        bne +
        lda #2
        sta trans_left
        jsr rnd
        and #63
        clc
        adc #SEGMENT_MIN
        sta seg_left
+       lda env
        bne +
        jsr urban_sides
        jmp _lanes
+       jsr forest_sides

        ; --- track ---
_lanes  lda bridge_countdown
        ora bridge_countdown+1
        beq _bc_done
        lda bridge_countdown
        bne +
        dec bridge_countdown+1
+       dec bridge_countdown
_bc_done
        lda bridge_left
        beq +
        jsr bridge_row
        jmp _done
+       lda chunk_left
        beq +
        jsr chunk_row
        jmp _done
+       lda spacer_left
        beq +
        jsr spacer_row
        jmp _done
+       lda bridge_countdown
        ora bridge_countdown+1
        bne +
        jsr start_bridge
        jmp _done
+       jsr pick_chunk
        lda spacer_len                  ; and the empty rows after it: a power-up
        ldx pu_gap                      ; overdue gets a clear stretch for it
        bne +
        ldx pu_gap+1
        bne +
        cmp #PU_CLEAR*2+1
        bcs +
        lda #PU_CLEAR*2+1
+       sta spacer_left
        jsr chunk_row

_done   jsr side_tiles
        jsr count_clear
        jmp expire_overlays

spacer_step
        ldx skill
        lda spacer_steps,x
        sta spacer_tick
        lda spacer_fewest,x
        cmp spacer_len
        bcs +
        dec spacer_len
+       rts
spacer_steps    .byte 96, 40, 24        ; rows per step: easy, medium, hard
spacer_fewest   .byte 8, 0, 0

; --- overlays (the CPC's: only their width is kept, for add_scenery) ----------
; A = width, X = rows: C set if added (top row = gen_row + rows - 1)
add_overlay
        sta t8
        ldy #OVERLAYS-1
-       lda ov_width,y
        beq +
        dey
        bpl -
        clc
        rts
+       lda t8
        sta ov_width,y
        dex
        txa
        clc
        adc gen_row
        sta ov_top_lo,y
        lda #0
        adc gen_row+1
        sta ov_top_hi,y
        lda scenery_width
        clc
        adc t8
        sta scenery_width
        sec
        rts

; A = width, X = rows: as add_overlay, unless the row's overlays would get
; wider than SCENERY_W_MAX
add_scenery
        sta t8
        clc
        adc scenery_width
        cmp #SCENERY_W_MAX+1
        bcc +
        clc
        rts
+       lda t8
        jmp add_overlay

; the overlays whose top row this is are done
expire_overlays
        ldy #OVERLAYS-1
_ov     lda ov_width,y
        beq _next
        lda gen_row+1                   ; top <= gen_row?
        cmp ov_top_hi,y
        bcc _next
        bne +
        lda gen_row
        cmp ov_top_lo,y
        bcc _next
+       lda scenery_width
        sec
        sbc ov_width,y
        sta scenery_width
        lda #0
        sta ov_width,y
_next   dey
        bpl _ov
        rts

; A = rows: C set if scenery may start (no transition or bridge near)
scenery_allowed
        sta t8
        lda trans_left
        ora bridge_left
        bne _no
        lda seg_left+1
        bne +
        lda seg_left
        sec
        sbc #SCENERY_MARGIN
        bcc _no
        cmp t8
        bcc _no
+       lda bridge_countdown+1
        bne _yes
        lda bridge_countdown
        sec
        sbc #SCENERY_MARGIN
        bcc _no
        cmp t8
        bcc _no
_yes    sec
        rts
_no     clc
        rts

; =============================================================================
; Sides
; =============================================================================
transition_sides
        ldy #D_FLAGS
        lda (dp),y
        ora #F_FOREST
        sta (dp),y
        lda #S_TRANS_UF_0
        ldx env
        beq +
        lda #S_TRANS_FU_0
+       ldx trans_left
        cpx #2
        beq +
        clc
        adc #1
+       sta base
        sta base+1
        dec trans_left
        bne +
        lda env
        eor #1
        sta env
+       rts

urban_sides
        lda gen_row
        and #1
        clc
        adc #S_ROAD_A                   ; road_a, road_b
        sta base
        sta base+1
        lda cross_phase
        bne _crossing
        dec cross_countdown
        bne _kiosks
        jsr rnd
        and #63
        clc
        adc #40
        sta cross_countdown
        lda #2
        sta cross_phase
_crossing
        ldx cross_phase
        dec cross_phase
        lda #S_ROAD_CROSS_0
        cpx #2
        beq +
        lda #S_ROAD_CROSS_1
+       sta base
        sta base+1
        jmp _cars
_kiosks ldx #0
        jsr kiosk
        ldx #1
        jsr kiosk
_cars   ldx #0
        jsr spawn_car
        ldx #1
        jmp spawn_car

; X = side
kiosk
        lda kiosk_phase,x
        bne _row
        dec kiosk_countdown,x
        bne _ret
        lda #40                         ; retry later if the outer lane is busy
        sta kiosk_countdown,x
        ldy side3,x
        lda car_busy,y
        bne _ret
        lda #3                          ; keep cars away from the kiosk
        sta car_busy,y
        jsr rnd
        and #127
        clc
        adc #60
        sta kiosk_countdown,x
        lda #2
        sta kiosk_phase,x
_row    ldy kiosk_phase,x
        dec kiosk_phase,x
        lda #S_KIOSK_0
        cpy #2
        beq +
        lda #S_KIOSK_1
+       sta base,x
_ret    rts

; X = side: maybe a vehicle in a free lane of that side
spawn_car
        jsr rnd
        and #7
        bne _ret
        lda #4
        jsr scenery_allowed
        bcc _ret
        lda #3
        sta divisor
        jsr random_below
        clc
        adc side3,x
        tay                             ; Y = car_busy index
        lda car_busy,y
        bne _ret
        jsr rnd                      ; 1/8 bus, 1/8 trolley, else a car
        and #7
        cmp #2
        lda #2
        bcs +
        lda #4
+       sta t8b                         ; rows
        jsr rnd
        and #3
        sec
        adc t8b
        sta car_busy,y
        lda #CAR_QUIET_ROWS
        sta car_recent,y
        stx t8c
        ldx t8b
        lda #CAR_W
        jsr add_scenery
        ldx t8c
        bcc _ret
        lda #OBJ_CAR
        ldy t8b
        cpy #4
        bne +
        lda #OBJ_BUS
+       sta started,x
_ret    rts

forest_sides
        ldy #D_FLAGS
        lda (dp),y
        ora #F_FOREST
        sta (dp),y
        ldx #0
        jsr forest_side
        ldx #1
        jsr forest_side
        ldx #0
        jsr spawn_tree
        ldx #1
        jmp spawn_tree

; X = side
forest_side
        lda path_left,x
        beq +
        dec path_left,x
        lda #S_PATH
        sta base,x
        rts
+       lda fence_left,x
        beq +
        dec fence_left,x
        lda #S_FENCE
        sta base,x
        rts
+       jsr rnd                      ; start a path or a fence now and then
        and #31
        bne _ground
        jsr rnd
        and #3
        clc
        adc #3
        sta t8
        jsr rnd
        lsr a
        lda t8
        bcc +
        sta path_left,x
        bcs _ground
+       sta fence_left,x
_ground jsr rnd
        and #2
        lsr a
        clc
        adc #S_GROUND_A                 ; ground_a, ground_b
        sta base,x
        rts

; X = side: maybe a tree, bush or rock
spawn_tree
        lda tree_busy,x
        bne _ret
        jsr rnd
        and #3
        bne _ret
        lda #3
        jsr scenery_allowed
        bcc _ret
        lda #5
        sta divisor
        jsr random_below
        tay
        lda tree_rows,y
        sta t8b
        clc
        adc #1
        sta tree_busy,x
        lda #15                         ; its column on the CPC
        sec
        sbc tree_w,y
        sta divisor
        jsr random_below
        stx t8c
        ldx t8b
        lda tree_w,y
        jsr add_scenery
        ldx t8c
        bcc _ret
        lda #OBJ_BUSH
        ldy t8b
        cpy #3
        bne +
        lda #OBJ_TREE
+       sta started,x
_ret    rts

tree_w          .byte 8, 12, 4, 4, 4    ; pine, oak, cypress, bush, rock (CPC bytes)
tree_rows       .byte 3, 3, 3, 1, 1
side3           .byte 0, 3

; the row's side tiles: a platform, else scenery (started here or still
; going), else the ground or the road
side_tiles
        ldx #1
_side   lda started,x
        beq +
        ldy obj_left,x
        bne +
        sta obj_kind,x
        tay
        lda obj_rows-1,y
        sta obj_left,x
        lda #0
        sta obj_pos,x
+       lda base,x
        ldy obj_left,x
        beq _plat
        dec obj_left,x
        lda obj_kind,x
        asl a
        asl a
        ora obj_pos,x
        tay
        lda obj_tiles-4,y
        inc obj_pos,x
_plat   sta t8
        ldy #D_PLAT
        lda (dp),y
        tay
        lda plat_tiles,y
        bmi +
        sta t8
+       txa
        bne _store
        ldy #D_FLAGS                    ; a bridge row keeps its index
        lda (dp),y
        bmi _skip
_store  txa
        clc
        adc #D_LEFT
        tay
        lda t8
        sta (dp),y
_skip   dex
        bpl _side
        rts

obj_rows        .byte 3, 1, 2, 4
obj_tiles       .byte S_TREE_0, S_TREE_1, S_TREE_2, 0
                .byte S_BUSH, 0, 0, 0
                .byte S_CAR_0, S_CAR_1, 0, 0
                .byte S_CAR_0, S_CAR_1, S_CAR_0, S_CAR_1
; D_PLAT -> side tile ($ff: none), the CPC's PLATFORM_SEQ
plat_tiles      .byte $ff, S_PLAT_END, S_PLAT_PLAIN, S_PLAT_BENCH, S_PLAT_PLAIN, S_PLAT_PLAIN
                .byte S_PLAT_BENCH, S_PLAT_PLAIN, S_PLAT_ROOF, S_PLAT_SIGN, S_PLAT_ROOF, S_PLAT_ROOF
                .byte S_PLAT_SIGN, S_PLAT_ROOF, S_PLAT_ROOF, S_PLAT_PLAIN, S_PLAT_BENCH, S_PLAT_PLAIN
                .byte S_PLAT_END, $ff, $ff, $ff, $ff

; =============================================================================
; Bridges
; =============================================================================
start_bridge
        jsr rnd
        and #127
        clc
        adc #BRIDGE_GAP_MIN
        sta bridge_countdown
        lda #0
        sta bridge_countdown+1
        ldx #0                          ; footbridge
        lda env
        bne +
        jsr rnd
        lsr a
        bcc +
        ldx #FOOT_ROWS                  ; road bridge, in the city half the time
+       stx bridge_pos
        lda #FOOT_ROWS
        cpx #0
        beq +
        lda #ROAD_ROWS
+       sta bridge_left
        ; fall through
bridge_row
        ldx bridge_pos
        lda bridge_rows,x
        ldy #D_LEFT
        sta (dp),y
        ldy #D_FLAGS
        lda (dp),y
        ora #F_BRIDGE
        sta (dp),y
        jsr rail_lanes
        inc bridge_pos
        dec bridge_left
        rts

FOOT_ROWS       = 4
ROAD_ROWS       = 7
bridge_rows     .byte B_FOOTBRIDGE_SHADOW, B_FOOTBRIDGE_0, B_FOOTBRIDGE_1, B_FOOTBRIDGE_2
                .byte B_ROADBRIDGE_SHADOW, B_ROADBRIDGE_0, B_ROADBRIDGE_1, B_ROADBRIDGE_2
                .byte B_ROADBRIDGE_3, B_ROADBRIDGE_4, B_ROADBRIDGE_5

rail_lanes
        lda #T_RAIL_A
        ldy #D_LANES
        sta (dp),y
        iny
        sta (dp),y
        iny
        sta (dp),y
        rts

; =============================================================================
; Chunks
; =============================================================================
pick_chunk
        lda gen_row+1                   ; a new game: no obstacles behind
        bne +
        lda gen_row
        cmp #SPACER_START+1
        bcs +
        jsr easy_reset
+       lda difficulty                  ; the weights of this difficulty and
        asl a                           ; environment (src/data/chunks.asm)
        ora env
        tax
        lda weights_lo,x
        sta ptr2
        lda weights_hi,x
        sta ptr2+1
        lda weights_total,x
        sta divisor
        jsr random_below                ; A = 0 .. total-1
        ldy #0
-       cmp (ptr2),y
        bcc +
        sbc (ptr2),y
        iny
        cpy #CHUNK_COUNT
        bne -
        ldy #0                          ; (rounding safety) chunk 0
+       tya
        tax
_found  lda chunk_lo,x
        sta chunk_ptr
        lda chunk_hi,x
        sta chunk_ptr+1
        ldy #0
        lda (chunk_ptr),y
        sta chunk_left
        ldy #3
        lda (chunk_ptr),y
        sta t8                          ; env | ramp | side by side
        and #CHUNK_RAMP
        sta roofs_reachable
        lda chunk_ptr
        clc
        adc #4
        sta chunk_ptr
        bcc +
        inc chunk_ptr+1
+       lda #6                          ; lane order: any, or as it is /
        bit t8                          ; mirrored for trains side by side
        bpl +
        lda #2
+       sta divisor
        jsr random_below
        sta t8
        asl a
        adc t8                          ; * 3
        tax
        ldy #0
-       lda lane_orders,x
        sta chunk_lanes,y
        sty t8b
        tay                             ; and back: chunk_src[lane] = k
        lda t8b
        sta chunk_src,y
        ldy t8b
        inx
        iny
        cpy #3
        bne -
        lda #3                          ; livery shift 0-2: 64 tiles each
        sta divisor
        jsr random_below
        lsr a
        ror a
        ror a
        sta livery
        rts

lane_orders     .byte 0,1,2, 2,1,0, 1,0,2, 0,2,1, 1,2,0, 2,0,1

; a new game: no obstacles below, the starts long ago
easy_reset
        ldx #2
-       lda #0
        sta ez_obj,x
        lda gen_row
        sec
        sbc #<1000
        sta ez_newer_lo,x
        sta ez_older_lo,x
        lda gen_row+1
        sbc #>1000
        sta ez_newer_hi,x
        sta ez_older_hi,x
        dex
        bpl -
        rts

; --- next row of the current chunk: its 3 cells in the chunk's lane order -----
chunk_row
        ldx #0                          ; X = chunk lane k, its cell at k*3
_cell   stx ck
        lda chunk_lanes,x
        sta row_lane
        clc
        adc #D_LANES
        sta yo                          ; Y of the lane's tile in the descriptor
        lda cell3,x
        sta coff
        lda skill
        bne _put
        ldy coff
        iny
        lda (chunk_ptr),y
        ldx row_lane
        jsr easy_cell
        bcc _put
        ldy yo                          ; dropped: rail
        lda #T_RAIL_A
        sta (dp),y
        lda #0
        iny
        iny
        iny
        sta (dp),y                      ; D_COLL
        iny
        iny
        iny
        sta (dp),y                      ; D_ITEM
        jmp _next
_put    ldy coff
        lda (chunk_ptr),y               ; tile, in the chunk's livery
        clc
        adc livery
        tax
        lda livery_tiles,x
        ldy yo
        sta (dp),y
        ldy coff
        iny
        lda (chunk_ptr),y               ; collision
        pha
        lda yo
        clc
        adc #D_COLL-D_LANES
        tay
        pla
        sta (dp),y
        ldy coff
        iny
        iny
        lda (chunk_ptr),y               ; item
        pha
        lda yo
        clc
        adc #D_ITEM-D_LANES
        tay
        pla
        sta (dp),y
        beq _next
        jsr spawn_item
_next   ldx ck
        inx
        cpx #3
        bne _cell
        lda chunk_ptr                   ; the next row
        clc
        adc #9
        sta chunk_ptr
        bcc +
        inc chunk_ptr+1
+       jsr place_powerup
        dec chunk_left
        rts

; Easy: a buffer stop or signal that would be the third obstacle of its lane
; within EASY_WINDOW rows becomes rail (both its rows). X = lane, A =
; collision. C set: drop it.
easy_cell
        and #15
        beq _clear
        cmp #COL_RAMP_UP
        bcc _obstacle                   ; stop, signal, train, cab
        cmp #COL_GAP
        beq _obstacle                   ; coupler
_clear  lda #0
        sta ez_obj,x
        clc
        rts
_obstacle
        tay
        lda ez_obj,x                    ; the same one as the row below?
        lsr a
        bcc _start
        lsr a                           ; C = being dropped
        rts
_start  lda #1
        sta ez_obj,x
        cpy #COL_TRAIN
        bcs _record                     ; a train stays
        lda gen_row                     ; rows since the older one < window?
        sec
        sbc ez_older_lo,x
        sta t8
        lda gen_row+1
        sbc ez_older_hi,x
        bne _record
        lda t8
        cmp #EASY_WINDOW
        bcs _record
        lda #3
        sta ez_obj,x
        sec
        rts
_record lda ez_newer_lo,x
        sta ez_older_lo,x
        lda ez_newer_hi,x
        sta ez_older_hi,x
        lda gen_row
        sta ez_newer_lo,x
        lda gen_row+1
        sta ez_newer_hi,x
        clc
        rts

; --- empty track between chunks ---------------------------------------------------
spacer_row
        dec spacer_left
        jsr rail_lanes
        lda pu_gap                      ; a power-up due and PU_CLEAR more
        ora pu_gap+1                    ; empty rows: any lane
        bne _ret
        lda spacer_left
        cmp #PU_CLEAR
        bcc _ret
        lda #3
        sta divisor
        jsr random_below
        tax
        lda #0
        sta pu_roof
        jsr clear_behind
        bcs _ret
        jmp put_powerup
_ret    rts

; =============================================================================
; Power-ups
; =============================================================================
; A = collision class: C set if it blocks a power-up spot. On the ground
; (pu_roof 0): stop, signal, train, cab, coupler; on a roof: off the train.
obstacle
        and #15
        sta obs_t
        lda pu_roof
        bne _roof
        lda obs_t
        beq _free
        cmp #COL_GAP
        beq _blocked
_ramps  cmp #COL_RAMP_UP                ; 1-4 blocked (C clear -> set below)
        bcc _blocked
_free   clc
        rts
_blocked
        sec
        rts
_roof   lda obs_t
        cmp #COL_TRAIN
        beq _free
        bne _ramps

; X = lane: C set if one of the PU_CLEAR rows below gen_row has an obstacle
; there (for pu_roof: on the ground or on a roof). Preserves X, Y.
clear_behind
        lda pu_roof
        bne +
        lda clear_rows,x
        jmp ++
+       lda clear_rows+3,x
+       cmp #PU_CLEAR                   ; C clear if fewer than PU_CLEAR
        rol a                           ; (C into bit 0)
        eor #1
        lsr a                           ; C set if blocked
        rts

; the row is done: per lane, clean rows behind it, on the ground and on a roof
count_clear
        ldx #2
_lane   txa
        clc
        adc #D_COLL
        tay
        lda (dp),y
        sta t8
        ldy #0
        sty pu_roof
        jsr obstacle
        bcc +
        lda #0
        sta clear_rows,x
        beq ++
+       lda clear_rows,x
        cmp #PU_CLEAR
        bcs +
        inc clear_rows,x
+       lda #COL_TRAIN
        sta pu_roof
        lda t8
        jsr obstacle
        bcc +
        lda #0
        sta clear_rows+3,x
        beq ++
+       lda clear_rows+3,x
        cmp #PU_CLEAR
        bcs +
        inc clear_rows+3,x
+       dex
        bpl _lane
        rts

; when pu_gap is 0: a power-up on a free lane of this chunk row (rail, or a
; wagon roof in a chunk with a ramp), clear PU_CLEAR rows behind and ahead
place_powerup
        lda pu_gap
        ora pu_gap+1
        bne _ret
        ldx chunk_left                  ; rows ahead in this chunk
        dex
        beq _ret
        txa
        clc
        adc spacer_len
        bcs +
        cmp #PU_CLEAR
        bcc _ret
+       txa                             ; the chunk rows to check
        cmp #PU_CLEAR
        bcc +
        lda #PU_CLEAR
+       sta pu_check
        lda #3
        sta divisor
        jsr random_below
        tax                             ; X = lane
        lda #3
        sta pu_tries
_try    txa
        clc
        adc #D_ITEM
        tay
        lda (dp),y
        bne _next
        tya
        sec
        sbc #D_ITEM-D_COLL
        tay
        lda (dp),y
        and #15
        beq +
        cmp #COL_TRAIN
        bne _next
        ldy roofs_reachable
        beq _next
+       sta pu_roof
        jsr clear_behind
        bcs _next
        ldy chunk_src,x                 ; the lane in the chunk's data
        lda cell3,y
        sta t8b
        tay
        iny
        iny
        lda (chunk_ptr),y               ; no item on the next row (2 rows)
        bne _next
        dey
        lda pu_roof                     ; on a roof: not over a coupler
        beq +
        lda (chunk_ptr),y
        and #15
        cmp #COL_TRAIN
        bne _next
+       lda pu_check                    ; no obstacle in the rows ahead
        sta t8
-       lda (chunk_ptr),y
        jsr obstacle
        bcs _next
        tya
        clc
        adc #9
        tay
        dec t8
        bne -
        jmp put_powerup
_next   inx
        cpx #3
        bcc +
        ldx #0
+       dec pu_tries
        bne _try
_ret    rts

cell3           .byte 0, 3, 6

; X = lane: a power-up there, then 50-120 rows to the next one
put_powerup
        jsr rnd
        cmp #PU_TURBO_ODDS
        lda #ITEM_TURBO
        bcc +
-       jsr rnd
        and #7
        cmp #5
        bcs -
        tay
        lda pu_kinds,y
+       sta t8
        txa
        clc
        adc #D_ITEM
        tay
        lda t8
        sta (dp),y
        jsr spawn_item
        lda #PU_GAP_RANGE+1
        sta divisor
        jsr random_below
        clc
        adc #PU_GAP_MIN
        sta pu_gap
        lda #0
        sta pu_gap+1
        rts
pu_kinds        .byte ITEM_MAGNET, ITEM_SLOW, ITEM_SPRING, ITEM_HELMET, ITEM_TICKET

; A = item: its overlay (a coin a row, a power-up two). Preserves X.
spawn_item
        stx t8c
        cmp #ITEM_COIN
        bne +
        lda #COIN_W
        ldx #1
        bne ++
+       lda #POWERUP_W
        ldx #2
+       jsr add_overlay
        ldx t8c
        rts

; =============================================================================
; render_row: the descriptor of world row A (low byte) -> 40 characters at
; (ptr). Coins are their character in the lane's middle column.
; =============================================================================
render_row
        jsr desc_index
        ldy #D_FLAGS
        lda (dp),y
        bpl _sides
        ldy #D_LEFT                     ; a bridge: one 40-character row
        lda (dp),y
        tax
        lda bridge_chars_lo,x
        sta ptr2
        lda bridge_chars_hi,x
        sta ptr2+1
        ldy #39
-       lda (ptr2),y
        sta (ptr),y
        dey
        bpl -
        rts
_sides  ldy #D_LEFT
        lda (dp),y
        tax
        lda side_l_chars_lo,x
        sta ptr2
        lda side_l_chars_hi,x
        sta ptr2+1
        lda #0
        ldx #LEFT_COLS
        jsr _copy
        ldy #D_RIGHT
        lda (dp),y
        tax
        lda side_r_chars_lo,x
        sta ptr2
        lda side_r_chars_hi,x
        sta ptr2+1
        lda #RIGHT_X
        ldx #RIGHT_COLS
        jsr _copy
        ldx #0                          ; lanes
_lane   stx ck
        txa
        clc
        adc #D_LANES
        tay
        lda (dp),y
        tay
        lda track_chars_lo,y
        sta ptr2
        lda track_chars_hi,y
        sta ptr2+1
        lda lane_x,x
        ldx #TRACK_COLS
        jsr _copy
        ldx ck                          ; a coin in the middle column
        txa
        clc
        adc #D_ITEM
        tay
        lda (dp),y
        cmp #ITEM_COIN
        bne _nocoin
        tya
        sec
        sbc #D_ITEM-D_COLL
        tay
        lda (dp),y
        and #15
        cmp #COL_TRAIN
        beq _roof
        lda #CH_COIN_RAIL
        bne +
_roof   lda #CH_COIN_ROOF
+       ldy #COIN_COL
        sta (ptr3),y
_nocoin inx
        cpx #3
        bne _lane
        rts
; X characters (ptr2) -> (ptr) + A; leaves ptr3 = (ptr) + A
_copy   clc
        adc ptr
        sta ptr3
        lda ptr+1
        adc #0
        sta ptr3+1
        txa
        tay
        dey
-       lda (ptr2),y
        sta (ptr3),y
        dey
        bpl -
        rts

LEFT_COLS       = 9
TRACK_COLS      = 7
RIGHT_COLS      = 10
RIGHT_X         = LEFT_COLS + 3*TRACK_COLS
COIN_COL        = 3
lane_x          .byte LEFT_COLS, LEFT_COLS+TRACK_COLS, LEFT_COLS+2*TRACK_COLS

; ring index -> descriptor address
desc_lo         .byte <(WORLD_RING + range(RING_ROWS) * ROW_SIZE)
desc_hi         .byte >(WORLD_RING + range(RING_ROWS) * ROW_SIZE)

; =============================================================================
; generator state (cleared by world_init), above the code and data
; =============================================================================
        .virtual WSTATE
wstate
gen_row         .word ?
pu_gap          .word ?
seg_left        .word ?
bridge_countdown .word ?
route_left      .word ?
spacer_len      .byte ?
spacer_left     .byte ?
spacer_tick     .byte ?
difficulty      .byte ?
env             .byte ?
trans_left      .byte ?
chunk_left      .byte ?
bridge_left     .byte ?
bridge_pos      .byte ?
cross_countdown .byte ?
cross_phase     .byte ?
kiosk_countdown .byte ?, ?
kiosk_phase     .byte ?, ?
path_left       .byte ?, ?
fence_left      .byte ?, ?
route_station   .byte ?
plat_left       .byte ?
scenery_width   .byte ?
busy_counters
car_busy        .fill 6
tree_busy       .fill 2
car_recent      .fill 6
BUSY_COUNT      = * - busy_counters
ov_width        .fill OVERLAYS
ov_top_lo       .fill OVERLAYS
ov_top_hi       .fill OVERLAYS
clear_rows      .fill 6                 ; per lane: clean rows behind, ground / roof
chunk_lanes     .fill 3
chunk_src       .fill 3
livery          .byte ?                 ; offset of its table in livery_tiles
roofs_reachable .byte ?
ez_obj          .fill 3                 ; per lane: bit 0 obstacle below, bit 1 dropped
ez_newer_lo     .fill 3
ez_newer_hi     .fill 3
ez_older_lo     .fill 3
ez_older_hi     .fill 3
pu_roof         .byte ?
pu_check        .byte ?
pu_tries        .byte ?
row_lane        .byte ?
base            .byte ?, ?              ; the sides' ground / road tile of the row
started         .byte ?, ?              ; scenery started on the row (OBJ_*)
obj_kind        .byte ?, ?              ; scenery being drawn, per side
obj_pos         .byte ?, ?
obj_left        .byte ?, ?
WSTATE_SIZE     = * - wstate
        .cerror WSTATE_SIZE > 255, "world_init clears 255 bytes at most"
        .endv
