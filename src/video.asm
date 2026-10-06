; VIC-II setup and per-frame video work.

video_init
        lda #BLACK
        sta VIC_BORDER
        sta VIC_BG0
        lda #0
        sta VIC_SPR_ENA
        rts

video_irq
        rts

video_frame
        rts
