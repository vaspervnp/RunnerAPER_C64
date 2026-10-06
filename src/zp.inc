; Zero page: $02-$8F belong to the game (KERNAL keeps the rest).

ZP_START        = $02

frame_counter   = $02           ; word, +1 per frame (top IRQ)
frame_flag      = $04           ; +1 by the IRQ, cleared by the main loop
overruns        = $05           ; frames the main loop missed (frame_flag was > 1)
frame_load      = $06           ; word: raster line where the last frame's work ended
max_load        = $08           ; word: highest frame_load (lines past 312 = next frame)

ptr             = $0a           ; word, general pointer
ptr2            = $0c           ; word
tmp             = $0e

; scroll (video.asm)
scroll_y        = $10           ; fine scroll 0-7 for the next frame
scroll_frac     = $11           ; sub-pixel position
speed_lo        = $12           ; speed in pixels per frame, 8.8
speed_hi        = $13
scroll_cmd      = $14           ; main loop -> top IRQ: bits 0-2 YSCROLL, bit 3 coarse step
cur_buf         = $15           ; 0: screen A shown, 1: screen B shown (set by the IRQ)
disp_top        = $16           ; word: world row shown in screen row 0 (set by the IRQ)
copy_stage      = $18           ; next stage of the hidden buffer build (COPY_STAGES = done)
stalls          = $19           ; coarse steps that had to wait for the hidden buffer
split_w1        = $1a           ; $d011 value that starts the black band ($50 | YSCROLL)
split_delay     = $1b           ; delay before it (shorter when $d6 is a bad line)


; world (world.asm)
rng             = $20           ; word
dp              = $22           ; word: descriptor being made / drawn
chunk_ptr       = $24           ; word: the chunk's next row
ptr3            = $26           ; word
divisor         = $28
t8              = $29
t8b             = $2a
t8c             = $2b
t16             = $2c           ; word
t16b            = $2e           ; word
obs_t           = $30
coff            = $31
ck              = $32
yo              = $33
skill           = $34           ; 0 easy, 1 medium, 2 hard
restart         = $35           ; tests / menu: start a new game

; input (input.asm), player (player.asm)
keys_held       = $36
keys_pressed    = $37
test_mode       = $38           ; tests: keys come from test_keys
test_keys       = $39
shown_y         = $3a           ; YSCROLL of the picture shown this frame
irq_clip_on     = $3b           ; the clip lines of this frame (latched by the top IRQ)
irq_clip_off    = $3c
irq_ptrs        = $3d           ; 3 bytes: the sprites' frames this frame

ZP_END          = $90
