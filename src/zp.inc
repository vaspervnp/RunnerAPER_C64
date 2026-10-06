; Zero page: $02-$8F belong to the game (KERNAL keeps the rest).

ZP_START        = $02

frame_counter   = $02           ; word, +1 per raster IRQ
frame_flag      = $04           ; set by the IRQ, cleared by the main loop
frame_load      = $05           ; raster line at the end of the last frame's work

ZP_END          = $90
