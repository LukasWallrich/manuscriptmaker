#!/usr/bin/env bash
set -euo pipefail
TEXBIN="$(quarto tools info tinytex | python3 -c 'import json,sys; print(json.load(sys.stdin)["bin-directory"])')"
export PATH="$TEXBIN:$PATH"
tlmgr update --self
tlmgr install carlito multirow ifoddpage tcolorbox fancyhdr tikzfill tikzpagenodes eso-pic \
  biblatex biber biblatex-apa csquotes orcidlink psnfss enumitem microtype \
  xurl placeins booktabs setspace listings listingsutf8 preprint pgf etoolbox xcolor
