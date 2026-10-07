# Runner A.P.E.R - Commodore 64 build
#   make        -> build/runner.d64
#   make run    -> x64sc with autostart
#   make test   -> headless tests (VICE binary monitor)
#   make stutter -> 10 minutes of play x 3 skills x 3 seeds: frames lost, load
#   make screenshots -> docs/screenshots/*.png (and the cover's logo)
#   make docs   -> docs/manual_*.pdf, docs/cover/ (a Chromium browser: EDGE=)
#   make shot   -> headless run, screenshot in build/shot.png
#   make gfx    -> src/data/ (charset, tiles, sprites) from gfx/png
#   make mockup -> build/mockup_*.png, game screens made from src/data
#   (gfx/png is the source art: tools/mkgfx.py drew the first version, edit
#    it in Aseprite; rerun mkgfx.py only for sheets nobody has painted over)

X64     ?= x64sc
C1541   ?= c1541
TASS    ?= 64tass
PYTHON  ?= python3

BUILD   := build
SRC     := $(wildcard src/*.asm src/*.inc)
GFX_IN  := $(wildcard gfx/png/*.png gfx/png/*.json)
GFX_TOOLS := tools/c64palette.py tools/assets64.py tools/png2c64.py tools/mklevel64.py tools/mktext64.py tools/mklogo64.py tools/mkmusic64.py
GFX_IN  += $(wildcard levels/chunks/*.txt text/*.txt music/*.txt)
GFX_STAMP := src/data/.stamp
PRG     := $(BUILD)/runner.prg
D64     := $(BUILD)/runner.d64
LABELS  := $(BUILD)/labels.txt
LIST    := $(BUILD)/runner.lst

# -C case-sensitive labels, -a ASCII source, -B long branches where needed,
# -i NMOS 6510 (illegal opcodes allowed), -Wall all warnings
TASSFLAGS := -C -a -B -i -Wall -I src

.PHONY: all run test stutter shot screenshots docs clean gfx mockup

all: $(D64)

$(BUILD):
	mkdir -p $@

gfx: $(GFX_STAMP)

$(GFX_STAMP): $(GFX_IN) $(GFX_TOOLS)
	$(PYTHON) tools/png2c64.py
	$(PYTHON) tools/mklevel64.py
	$(PYTHON) tools/mktext64.py
	$(PYTHON) tools/mklogo64.py
	$(PYTHON) tools/mkmusic64.py
	touch $@

mockup: $(GFX_STAMP)
	$(PYTHON) tools/mockup64.py
	$(PYTHON) tools/mockup64.py brown

$(PRG): $(SRC) $(GFX_STAMP) | $(BUILD)
	$(TASS) $(TASSFLAGS) src/main.asm -o $@ --vice-labels-numeric -l $(LABELS) -L $(LIST)

$(D64): $(PRG)
	rm -f $@
	$(C1541) -format "runner aper,ap" d64 $@ -write $(PRG) runner >/dev/null

run: $(D64)
	$(X64) -autostart $(D64)

test: $(D64)
	$(PYTHON) tests/run_tests.py

stutter: $(PRG)
	$(PYTHON) tests/stutter.py 10 3

screenshots: $(D64)
	$(PYTHON) tools/screenshots64.py

docs:
	$(PYTHON) tools/mkdocs64.py

shot: $(D64)
	$(X64) -console -default -warp -silent -sounddev dummy -autostartprgmode 1 -autostart $(PRG) \
	       -limitcycles 8000000 -exitscreenshot $(BUILD)/shot.png >/dev/null 2>&1 || true

clean:
	rm -rf $(BUILD) src/data
