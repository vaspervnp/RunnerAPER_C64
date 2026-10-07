; =============================================================================
; Runner A.P.E.R - the boot file (RUNNER on the disk, loaded first).
;
; Shows the REVIVE8BIT screen (a multicolor bitmap, tools/mksplash64.py)
; for 10 seconds or until SPACE (or FIRE on port 2), then loads the game
; (GAME_FILE) with the KERNAL, the screen still showing, and starts it.
;
; The game loads over $0801-$bfff, so the screen lives in VIC bank 3:
; matrix $cc00, bitmap $e000 (the RAM under the KERNAL: the KERNAL reads
; its ROM, the VIC-II the RAM), and the loader runs from $c800. None of it
; is in the game's file.
;
; Assembled on its own: 64tass ... -D GAME_START=$080d src/boot.asm
; =============================================================================

SETMSG          = $ff90
SETLFS          = $ffba
SETNAM          = $ffbd
LOAD            = $ffd5
LAST_DEVICE     = $ba

VIC_CTRL1       = $d011
VIC_RASTER      = $d012
VIC_SPR_ENA     = $d015
VIC_CTRL2       = $d016
VIC_MEM         = $d018
VIC_BORDER      = $d020
VIC_BG0         = $d021
CIA1_PRA        = $dc00
CIA1_PRB        = $dc01
CIA2_PRA        = $dd00
COLOUR_RAM      = $d800

GAME_FILE       = "aper"                ; the game on the disk (PETSCII $41..: as c1541 writes it)
STUB            = $c800                 ; the loader
SPLASH_SCREEN   = $cc00
SPLASH_BITMAP   = $e000
SPLASH_FRAMES   = 500                   ; 10 s at 50 Hz
WAIT_LINE       = 251                   ; below the picture

src             = $fb                   ; (free for programs)
dst             = $fd
count           = $fb                   ; the stub's frame counter (after the copies)

        * = $0801
        .word (+), 10
        .null $9e, format("%d", start)
+       .word 0

start
        sei
        lda #$0b                        ; screen off while the copies run
        sta VIC_CTRL1
        ldx #0
-       lda copies,x                    ; source, destination, length
        sta src
        lda copies+1,x
        sta src+1
        lda copies+2,x
        sta dst
        lda copies+3,x
        sta dst+1
        lda copies+4,x
        sta len_lo
        lda copies+5,x
        sta len_hi
        stx copy_i
        jsr copy
        lda copy_i
        clc
        adc #6
        tax
        cpx #copies_end - copies
        bne -
        jmp show

copies  .word splash_data, SPLASH_BITMAP, 8000
        .word splash_data + 8000, SPLASH_SCREEN, 1000
        .word splash_data + 9000, COLOUR_RAM, 1000
        .word stub_code, STUB, stub_end - show
copies_end

; (src) -> (dst), len_hi pages and len_lo bytes
copy    ldy #0
        ldx len_hi
        beq _rest
-       lda (src),y
        sta (dst),y
        iny
        bne -
        inc src+1
        inc dst+1
        dex
        bne -
_rest   ldx len_lo
        beq _done
-       lda (src),y
        sta (dst),y
        iny
        dex
        bne -
_done   rts

len_lo  .byte 0
len_hi  .byte 0
copy_i  .byte 0

; -----------------------------------------------------------------------------
; the loader, run at STUB
; -----------------------------------------------------------------------------
stub_code
        .logical STUB
show
        lda #0
        sta VIC_BORDER
        sta VIC_BG0
        sta VIC_SPR_ENA
        lda CIA2_PRA                    ; VIC bank 3 ($c000-$ffff)
        and #$fc
        sta CIA2_PRA
        lda #(SPLASH_SCREEN & $3c00) >> 6 | (SPLASH_BITMAP & $2000) >> 10
        sta VIC_MEM
        lda #$18                        ; multicolor, 40 columns
        sta VIC_CTRL2
        lda #$3b                        ; bitmap, screen on
        sta VIC_CTRL1
        lda #<SPLASH_FRAMES
        sta count
        lda #>SPLASH_FRAMES
        sta count+1

wait_frame                              ; a frame: until the raster reaches WAIT_LINE
        lda #WAIT_LINE
-       cmp VIC_RASTER
        beq -
-       cmp VIC_RASTER
        bne -
        lda #$7f                        ; SPACE: column 7, row 4
        sta CIA1_PRA
        lda CIA1_PRB
key_read                                ; (tests: A = the rows read)
        and #$10
        beq go
        lda CIA1_PRA                    ; FIRE on port 2
        and #$10
        beq go
        lda count
        bne +
        dec count+1
+       dec count
        lda count
        ora count+1
        bne wait_frame

go      lda #$ff
        sta CIA1_PRA
load_game
        lda #0                          ; no "LOADING" on a screen nobody sees
        jsr SETMSG
        lda #game_name_end - game_name
        ldx #<game_name
        ldy #>game_name
        jsr SETNAM
        ldx LAST_DEVICE                 ; the drive RUNNER came from (8 if unknown)
        cpx #8
        bcs +
        ldx #8
+       lda #1
        ldy #1                          ; to the file's own address
        jsr SETLFS
        lda #0
        jsr LOAD
        bcs failed
loaded
        sei
        lda #$0b                        ; screen off: the game sets its own
        sta VIC_CTRL1
        jmp GAME_START

failed  lda #2                          ; a red border: SPACE tries again
        sta VIC_BORDER
-       lda #$7f
        sta CIA1_PRA
        lda CIA1_PRB
        and #$10
        bne -
        lda #0
        sta VIC_BORDER
        jmp load_game

game_name
        .text GAME_FILE
game_name_end
stub_end
        .endlogical

        .cerror stub_end > SPLASH_SCREEN, "the loader runs into the screen"

splash_data
        .binary "data/splash.bin"
boot_end
        .cerror boot_end > $8000, "the boot file is too long"
