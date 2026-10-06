; =============================================================================
; The high score table on the disk (KERNAL, device 8): file SCORES = "APER"
; and the table (scores_file, screens.asm). Loaded at boot, saved after a
; new record has its name. No drive or no file: the defaults stay.
;
; While the KERNAL talks to the drive the raster IRQ is masked and the
; screen blanked (the serial bus wants the CPU to itself); then the IRQ
; chain starts again from the top IRQ.
; =============================================================================

SETMSG          = $ff90
SETLFS          = $ffba
SETNAM          = $ffbd
LOAD            = $ffd5
SAVE            = $ffd8
DISK_DEVICE     = 8
SCORES_BUF      = WORLD_RING            ; load here at boot, before the world

; at boot (no IRQ yet): SCORES -> the table, if it is ours
load_scores
        jsr disk_open
        ldx #<scores_load_name
        ldy #>scores_load_name
        lda #SCORES_LOAD_LEN
        jsr SETNAM
        lda #0                          ; load, to X/Y
        ldx #<SCORES_BUF
        ldy #>SCORES_BUF
        jsr LOAD
        bcs _ret                        ; no drive, no file
        cpx #<(SCORES_BUF + SCORES_SIZE) ; X/Y = end: the right size?
        bne _ret
        cpy #>(SCORES_BUF + SCORES_SIZE)
        bne _ret
        ldx #3
-       lda SCORES_BUF,x
        cmp score_magic,x
        bne _ret
        dex
        bpl -
        ldx #SCORES_SIZE-1
-       lda SCORES_BUF,x
        sta scores_file,x
        dex
        bpl -
_ret    rts

; the table -> SCORES (replaced)
save_scores
        sei
        lda #0
        sta VIC_IRQ_MASK
        lda #$ff
        sta VIC_IRQ
        lda #$0b                        ; screen off: the border's colour
        sta VIC_CTRL1
        jsr disk_open
        lda #SCORES_SAVE_LEN
        ldx #<scores_save_name
        ldy #>scores_save_name
        jsr SETNAM
        lda #<scores_file
        sta ptr2
        lda #>scores_file
        sta ptr2+1
        lda #ptr2
        ldx #<(scores_file + SCORES_SIZE)
        ldy #>(scores_file + SCORES_SIZE)
        jsr SAVE
        sei                             ; the IRQ chain from the top again
        lda #<irq_top
        sta IRQ_VEC
        lda #>irq_top
        sta IRQ_VEC+1
        lda VIC_CTRL1
        and #$7f
        sta VIC_CTRL1
        lda #IRQ_LINE
        sta VIC_RASTER
        lda #$ff
        sta VIC_IRQ
        lda #1
        sta VIC_IRQ_MASK
        lda #0
        sta frame_flag
        cli
        rts

; no KERNAL messages (they would print into $0400), file 1 on device 8
disk_open
        lda #0
        jsr SETMSG
        lda #1
        ldx #DISK_DEVICE
        ldy #0
        jmp SETLFS

scores_load_name
        .text "SCORES"
SCORES_LOAD_LEN = * - scores_load_name
scores_save_name
        .text "@0:SCORES"
SCORES_SAVE_LEN = * - scores_save_name
