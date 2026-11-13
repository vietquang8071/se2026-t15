#!/usr/bin/env bash
set -euo pipefail
root="$(git rev-parse --show-toplevel)"
report="$root/docs/assignments/23001922-vt-060/report"
tmp="$(mktemp -d -t vt060-pdf-XXXXXX)"
trap 'rm -rf "$tmp"' EXIT
pandoc "$report/BT3_23001922_VT-060.md" -f markdown+raw_html -t html5 -s --metadata title='BT3 23001922 VT-060' --css="$report/report.css" -o "$tmp/report.html"
google-chrome --headless --no-sandbox --disable-gpu --disable-dev-shm-usage --no-pdf-header-footer --print-to-pdf="$tmp/raw.pdf" "file://$tmp/report.html"
python3 - "$tmp/raw.pdf" "$report/BT3_23001922_VT-060.pdf" <<'PY'
import fitz,sys
doc=fitz.open(sys.argv[1])
for i,page in enumerate(doc):
    page.insert_text((page.rect.width/2-12,page.rect.height-22),f'{i+1} / {len(doc)}',fontsize=8,fontname='helv',color=(.3,.35,.4))
doc.save(sys.argv[2],garbage=4,deflate=True)
PY
