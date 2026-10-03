#!/usr/bin/env bash
# Publish data/export as a GitHub Release asset that the Pages workflow deploys with the site.
# One release per snapshot (tag data-YYYYMM); re-running replaces that snapshot's asset.
# Run after pipeline/export.py. Needs the gh CLI, logged in.
set -euo pipefail
cd "$(dirname "$0")/.."
snap=$(python3 -c "import json; print(json.load(open('data/export/manifest.json'))['latest_snapshot'])")
tag="data-$snap"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
tar -czf "$tmp/export.tar.gz" -C data/export .
echo "export.tar.gz: $(du -h "$tmp/export.tar.gz" | cut -f1) for snapshot $snap"
if gh release view "$tag" >/dev/null 2>&1; then
  gh release upload "$tag" "$tmp/export.tar.gz" --clobber
else
  gh release create "$tag" "$tmp/export.tar.gz" --title "Data: snapshot $snap" --latest=false \
    --notes "Exported site data (pipeline/export.py) for the $snap snapshot. The Pages workflow deploys the newest data-* release."
fi
gh workflow run pages.yml >/dev/null && echo "Triggered the Pages deploy." || echo "Could not trigger pages.yml (is it pushed?)."
