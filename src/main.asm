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

        lda #<irq
        sta IRQ_VEC
        lda #>irq
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
        lda #0
        sta frame_flag

        jsr video_frame

        lda VIC_RASTER          ; load: raster line where this frame's work ended
        sta frame_load
frame_done                      ; tests put a checkpoint here
        jmp main_loop

; ---------------------------------------------------------------------------
; Raster IRQ, entered through the KERNAL ($0314) with A/X/Y on the stack.
; ---------------------------------------------------------------------------
irq
        lda #1
        sta VIC_IRQ
        jsr video_irq
        inc frame_counter
        bne +
        inc frame_counter+1
+       inc frame_flag
        jmp $ea81               ; KERNAL: restore Y/X/A, rti

        .include "video.asm"
