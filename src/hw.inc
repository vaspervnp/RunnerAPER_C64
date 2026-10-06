; C64 hardware registers

VIC_SPR_X       = $d000
VIC_SPR_Y       = $d001
VIC_SPR_XMSB    = $d010
VIC_CTRL1       = $d011         ; RST8 ECM BMM DEN RSEL YSCROLL(3)
VIC_RASTER      = $d012
VIC_SPR_ENA     = $d015
VIC_CTRL2       = $d016         ; - - RES MCM CSEL XSCROLL(3)
VIC_SPR_YEXP    = $d017
VIC_MEM         = $d018         ; VM13-10 CB13-11 -
VIC_IRQ         = $d019
VIC_IRQ_MASK    = $d01a
VIC_SPR_PRIO    = $d01b
VIC_SPR_MC      = $d01c
VIC_SPR_XEXP    = $d01d
VIC_BORDER      = $d020
VIC_BG0         = $d021
VIC_BG1         = $d022
VIC_BG2         = $d023
VIC_SPR_MC0     = $d025
VIC_SPR_MC1     = $d026
VIC_SPR_COL     = $d027

COLOR_RAM       = $d800

CIA1_PRA        = $dc00
CIA1_PRB        = $dc01
CIA1_ICR        = $dc0d
CIA2_PRA        = $dd00
CIA2_DDRA       = $dd02
CIA2_ICR        = $dd0d

IRQ_VEC         = $0314

; colours
BLACK = 0
WHITE = 1
RED = 2
CYAN = 3
PURPLE = 4
GREEN = 5
BLUE = 6
YELLOW = 7
ORANGE = 8
BROWN = 9
LIGHT_RED = 10
DARK_GREY = 11
GREY = 12
LIGHT_GREEN = 13
LIGHT_BLUE = 14
LIGHT_GREY = 15
