; Runner A.P.E.R - Commodore 64 (PAL)
; Entry point, raster IRQ and main loop.

        .include "hw.inc"
        .include "zp.inc"
        .include "data/gfx.inc"

WORLD_RING      = $0400                 ; 64 row descriptors x 16 bytes
WSTATE          = $c000                 ; generator state (world.asm)
PSTATE          = $c100                 ; the runner (player.asm)
KSTATE          = $c200                 ; coins, power-ups, score (pickups.asm)

; text: our font's codes (assets64.FONT_GLYPHS: space, a-z, 0-9, ...)
        .enc "game"
        .cdef "  ", FONT_SPACE
        .cdef "az", FONT_A
        .cdef "09", FONT_N0
        .enc "none"

IRQ_LINE = 0                    ; top of the frame, above the picture

; ---------------------------------------------------------------------------
; BASIC stub: 10 SYS <start>
; ---------------------------------------------------------------------------
        * = $0801
        .word (+), 10
        .null $9e, format("%d", start)
+       .word 0

; ---------------------------------------------------------------------------
start
        sei
        cld
        ldx #$ff
        txs
        lda #$36                ; BASIC ROM out, KERNAL and I/O in
        sta $01

        lda #$7f                ; no CIA interrupts: the raster IRQ is the clock
        sta CIA1_ICR
        sta CIA2_ICR
        lda CIA1_ICR
        lda CIA2_ICR

        ldx #ZP_START           ; clear the game's zero page
        lda #0
-       sta 0,x
        inx
        cpx #ZP_END
        bne -

        jsr game_start
        jmp main_loop

; a new game at the current skill: world, screens, IRQs
game_start
        sei
        lda #0
        sta VIC_IRQ_MASK
        sta restart
        jsr world_init
        jsr pickups_init
        jsr video_init
        jsr player_init
        lda #LIVES_START
        sta lives
        ldx #0                  ; hard: jump the gaps between wagons
        lda skill
        cmp #2
        bne +
        inx
+       stx gap_hard
        jsr player_sprites

        lda #<irq_top
        sta IRQ_VEC
        lda #>irq_top
        sta IRQ_VEC+1
        lda VIC_CTRL1
        and #$7f                ; raster compare bit 8 = 0
        sta VIC_CTRL1
        lda #IRQ_LINE
        sta VIC_RASTER
        lda #1
        sta VIC_IRQ_MASK
        sta VIC_IRQ             ; drop anything pending
        lda #0
        sta frame_flag
        cli
        rts

; ---------------------------------------------------------------------------
; Main loop: one pass per frame, released by the IRQ.
; ---------------------------------------------------------------------------
main_loop
        lda restart             ; tests / menu: a new game
        beq +
        jsr game_start
+
-       lda frame_flag
        beq -
        cmp #2
        bcc +
        inc overruns            ; a whole frame went by without us
+       lda #0
        sta frame_flag

        jsr read_input
        jsr game_state_update   ; crashed / over: the world stands
        bcs +
        jsr player_update
        jsr collide
        jsr play_pickups
+       jsr move_flyers
        jsr video_frame
        jsr player_sprites
        jsr pickup_sprites

        jsr measure_load
frame_done                      ; tests put a checkpoint here
        jmp main_loop

; frame_load = raster line now (9 bits); past 311 if the IRQ of the next
; frame has already run (frame_flag set)
measure_load
-       lda VIC_RASTER
        ldx VIC_CTRL1
        cmp VIC_RASTER          ; read again: the line must not change between
        bne -
        sta frame_load
        txa
        rol a
        lda #0
        rol a
        sta frame_load+1
        lda frame_flag
        beq +
        lda frame_load          ; + 312
        clc
        adc #<312
        sta frame_load
        lda frame_load+1
        adc #>312
        sta frame_load+1
+       lda frame_load+1
        cmp max_load+1
        bcc +
        bne _new
        lda frame_load
        cmp max_load
        bcc +
_new    lda frame_load
        sta max_load
        lda frame_load+1
        sta max_load+1
+       rts

; ---------------------------------------------------------------------------
; Raster IRQ, entered through the KERNAL ($0314) with A/X/Y on the stack.
; ---------------------------------------------------------------------------
irq_top
        lda #1
        sta VIC_IRQ
        jsr video_irq_top
        jsr sprites_irq
irq_top_done                    ; tests: the picture of this frame is set
        lda clip_on             ; this frame's deck cuts
        sta irq_clip_on
        lda clip_off
        sta irq_clip_off
        ldx #2
-       lda spr_ptr,x
        sta irq_ptrs,x
        dex
        bpl -
        inc frame_counter
        bne +
        inc frame_counter+1
+       inc frame_flag
        lda irq_clip_on
        beq +
        sec
        sbc #2
        ldx #<irq_clip_on_h
        ldy #>irq_clip_on_h
        jmp irq_next
+       lda irq_clip_off
        beq irq_to_split
        sec
        sbc #2
        ldx #<irq_clip_off_h
        ldy #>irq_clip_off_h
        jmp irq_next

; A = line, X/Y = handler: the next raster IRQ
irq_next
        stx IRQ_VEC
        sty IRQ_VEC+1
        sta VIC_RASTER
        jmp $ea81               ; KERNAL: restore Y/X/A, rti
irq_to_split
        lda #SPLIT_IRQ_LINE
        ldx #<irq_split
        ldy #>irq_split
        jmp irq_next

; a bridge deck starts cutting the runner on line irq_clip_on
irq_clip_on_h
        lda #1
        sta VIC_IRQ
        lda #BLANK_BLOCK
        sta clip_ptrs
        sta clip_ptrs+1
        sta clip_ptrs+2
        lda irq_clip_on
        jsr clip_write
        lda irq_clip_off
        beq irq_to_split
        sec
        sbc #2
        ldx #<irq_clip_off_h
        ldy #>irq_clip_off_h
        jmp irq_next

; ... and ends on line irq_clip_off - 1
irq_clip_off_h
        lda #1
        sta VIC_IRQ
        ldx #2
-       lda irq_ptrs,x
        sta clip_ptrs,x
        dex
        bpl -
        lda irq_clip_off
        jsr clip_write
        jmp irq_to_split

irq_split
        lda #1
        sta VIC_IRQ
        jsr video_irq_split
        lda #<irq_top
        sta IRQ_VEC
        lda #>irq_top
        sta IRQ_VEC+1
        lda #IRQ_LINE
        sta VIC_RASTER
irq_split_end
        jmp $ea81

        .include "video.asm"
        .include "world.asm"
        .include "input.asm"
        .include "player.asm"
        .include "pickups.asm"
code_end

        .cerror code_end > $4000, "code runs into the VIC bank"

; --- VIC bank 1: charset and sprites, loaded in place --------------------------
        * = CHARSET
        .binary "data/charset.bin"
        * = $5000
sprites
        .binary "data/sprites.bin"
sprite_blank                    ; an empty block (player.asm: cut under decks)
        .fill 64, 0

; --- data ---------------------------------------------------------------------
        * = $8000
        .include "data/chunks.asm"
        .include "data/gfx.asm"
        .include "data/text.asm"
data_end
        .cerror data_end > WSTATE, "data runs into the generator state"
