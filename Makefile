# Runner A.P.E.R - Commodore 64 build
#   make        -> build/runner.d64
#   make run    -> x64sc with autostart
#   make test   -> headless tests (VICE binary monitor)
#   make shot   -> headless run, screenshot in build/shot.png

X64     ?= x64sc
C1541   ?= c1541
TASS    ?= 64tass
PYTHON  ?= python3

BUILD   := build
SRC     := $(wildcard src/*.asm src/*.inc)
PRG     := $(BUILD)/runner.prg
D64     := $(BUILD)/runner.d64
LABELS  := $(BUILD)/labels.txt
LIST    := $(BUILD)/runner.lst

# -C case-sensitive labels, -a ASCII source, -B long branches where needed,
# -i NMOS 6510 (illegal opcodes allowed), -Wall all warnings
TASSFLAGS := -C -a -B -i -Wall -I src

.PHONY: all run test shot clean

all: $(D64)

$(BUILD):
	mkdir -p $@

$(PRG): $(SRC) | $(BUILD)
	$(TASS) $(TASSFLAGS) src/main.asm -o $@ --vice-labels-numeric -l $(LABELS) -L $(LIST)

$(D64): $(PRG)
	rm -f $@
	$(C1541) -format "runner aper,ap" d64 $@ -write $(PRG) runner >/dev/null

run: $(D64)
	$(X64) -autostart $(D64)

test: $(D64)
	$(PYTHON) tests/run_tests.py

shot: $(D64)
	$(X64) -console -default -warp -silent -sounddev dummy -autostart $(D64) \
	       -limitcycles 8000000 -exitscreenshot $(BUILD)/shot.png >/dev/null 2>&1 || true

clean:
	rm -rf $(BUILD)
