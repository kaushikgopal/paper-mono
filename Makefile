# Paper Mono with an oblique italic and inverted feature defaults.
#
#   make            = build + install to ~/Library/Fonts (default)
#   make build      = build the upright and italic variable fonts
#   make preview    = serve + open preview.html
#
# scripts/generate-sources.py derives both styles from the Glyphs source.
# Coding ligatures and the slashed zero are on by default; ss01 and zero turn
# them off. Python runs through `uv run`, so no venv is needed.

ANGLE ?= 10
PORT ?= 8138

FONT_DIR := $(HOME)/Library/Fonts
UPRIGHT_VF := fonts/variable/PaperMono[wght].ttf
ITALIC_VF := fonts/variable/PaperMono-Italic[wght].ttf
# Unmodified upstream release, used by `make restore`.
ORIGINAL_VF ?= $(HOME)/Library/CloudStorage/GoogleDrive-kaushikgopal@gmail.com/My Drive/syc/fonts/mono/paper-mono-v1.000/fonts/variable/PaperMono[wght].ttf
# Versions match requirements.txt. The public index overrides any private
# default index in the user's uv configuration.
UV_RUN := uv run --no-project --default-index https://pypi.org/simple \
	--with gftools==0.9.996 --with glyphslib==6.13.1 --with fontmake==3.11.1

.DEFAULT_GOAL := install
.PHONY: install build uninstall restore preview clean help

install: build                  ## build + install both fonts to ~/Library/Fonts (default)
	cp "$(UPRIGHT_VF)" "$(ITALIC_VF)" "$(FONT_DIR)/"
	@echo "Installed to $(FONT_DIR). Restart apps to pick up the fonts."

build:                          ## build both variable fonts (italic ANGLE=10 by default)
	$(UV_RUN) python3 scripts/generate-sources.py --angle $(ANGLE)
	$(UV_RUN) gftools builder sources/config-fork.yaml

uninstall:                      ## remove both fonts from ~/Library/Fonts
	rm -f "$(FONT_DIR)/PaperMono[wght].ttf" "$(FONT_DIR)/PaperMono-Italic[wght].ttf"

restore:                        ## reinstall the original upstream font and remove the italic
	@test -f "$(ORIGINAL_VF)" || { echo "Original font not found: $(ORIGINAL_VF)"; exit 1; }
	rm -f "$(FONT_DIR)/PaperMono-Italic[wght].ttf"
	cp "$(ORIGINAL_VF)" "$(FONT_DIR)/PaperMono[wght].ttf"
	@echo "Restored original Paper Mono to $(FONT_DIR). Restart apps to pick it up."

preview:                        ## serve + open preview.html (PORT=8138 by default)
	PORT=$(PORT) bun scripts/serve.ts

clean:                          ## remove generated sources and the italic font
	rm -rf sources/generated sources/instance_ufos sources/build.ninja sources/.ninja_log "$(ITALIC_VF)"

help:                           ## list targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  make %-10s %s\n", $$1, $$2}'
