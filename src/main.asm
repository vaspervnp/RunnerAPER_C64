; Runner A.P.E.R - Commodore 64 (PAL)
; Entry point, raster IRQ and main loop.

        .include "hw.inc"
        .include "zp.inc"

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

        ldx #ZP_END-ZP_START-1  ; clear the game's zero page
        lda #0
-       sta ZP_START,x
        dex
        bpl -

        jsr video_init

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
        cli

; ---------------------------------------------------------------------------
; Main loop: one pass per frame, released by the IRQ.
; ---------------------------------------------------------------------------
main_loop
-       lda frame_flag
        beq -
        cmp #2
        bcc +
        inc overruns            ; a whole frame went by without us
+       lda #0
        sta frame_flag

        jsr video_frame

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
irq_top_done                    ; tests: the picture of this frame is set
        inc frame_counter
        bne +
        inc frame_counter+1
+       inc frame_flag
        lda #<irq_split
        sta IRQ_VEC
        lda #>irq_split
        sta IRQ_VEC+1
        lda #SPLIT_IRQ_LINE
        sta VIC_RASTER
        jmp $ea81               ; KERNAL: restore Y/X/A, rti

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
