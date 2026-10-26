# Paper Mono with an oblique italic.
#
#   make            = build + install to ~/Library/Fonts (default)
#   make build      = build fonts/variable/PaperMono-Italic[wght].ttf
#   make preview    = serve + open preview.html
#
# The upright variable font is the one upstream commits in fonts/variable/.
# The italic is generated from the same Glyphs source by
# scripts/make-italic.py. Python runs through `uv run`, so no venv is needed.

ANGLE ?= 10
PORT ?= 8138

FONT_DIR := $(HOME)/Library/Fonts
UPRIGHT_VF := fonts/variable/PaperMono[wght].ttf
ITALIC_VF := fonts/variable/PaperMono-Italic[wght].ttf
# Versions match requirements.txt. The public index overrides any private
# default index in the user's uv configuration.
UV_RUN := uv run --no-project --default-index https://pypi.org/simple \
	--with gftools==0.9.996 --with glyphslib==6.13.1 --with fontmake==3.11.1

.DEFAULT_GOAL := install
.PHONY: install build uninstall preview clean help

install: build                  ## build + install both fonts to ~/Library/Fonts (default)
	cp "$(UPRIGHT_VF)" "$(ITALIC_VF)" "$(FONT_DIR)/"
	@echo "Installed to $(FONT_DIR). Restart apps to pick up the fonts."

build:                          ## build the italic VF (ANGLE=10 by default)
	$(UV_RUN) python3 scripts/make-italic.py --angle $(ANGLE)
	$(UV_RUN) gftools builder sources/config-italic.yaml

uninstall:                      ## remove both fonts from ~/Library/Fonts
	rm -f "$(FONT_DIR)/PaperMono[wght].ttf" "$(FONT_DIR)/PaperMono-Italic[wght].ttf"

preview:                        ## serve + open preview.html (PORT=8138 by default)
	PORT=$(PORT) bun scripts/serve.ts

clean:                          ## remove generated italic files
	rm -rf sources/italic sources/instance_ufos sources/build.ninja sources/.ninja_log "$(ITALIC_VF)"

help:                           ## list targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  make %-10s %s\n", $$1, $$2}'
