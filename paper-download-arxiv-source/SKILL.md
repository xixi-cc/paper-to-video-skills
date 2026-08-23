---
name: paper-download-arxiv-source
description: Download a versioned or unversioned arXiv paper source package, safely extract TeX and original figures, and write a hash-backed provenance receipt. Use when a paper-to-Beamer workflow starts from an arXiv URL or ID or needs higher-fidelity source assets than PDF extraction.
---

# Download arXiv Source

Fetch an arXiv e-print into a paper workspace without modifying an existing
source tree implicitly.

## Run

```bash
python "$SKILL_DIR/scripts/download_source.py" ARXIV_URL_OR_ID --output PAPER_ROOT
```

Use `--force` only when the user explicitly wants to replace an existing source
snapshot. The command writes under `PAPER_ROOT/source/`:

- `source-provenance.json`, containing the requested identifier, retrieval URL,
  UTC timestamp, payload SHA-256, version-pinning state, and artifact paths;
- `paper.pdf` for rendered-page evidence; and
- `tex/` plus the original e-print archive when TeX source is available; and
- `source-index.json`, a compact file/section/caption/figure/equation-label
  routing index used before opening the full TeX tree.

For a PDF-only submission, the source and rendered-paper payload are the same
PDF and the receipt records that fact.

The script rejects traversal paths, links, devices, oversized archives, empty
payloads, and unrecognized content. A repeated run reuses only a complete,
matching provenance receipt.

## Downstream contract

Read [`references/source-contract.md`](references/source-contract.md) when
integrating the result with `paper-to-beamer` or `paper-to-video`. Preserve
`paper_presentation.json` as the content source of truth: TeX improves
extraction fidelity, while the rendered PDF remains the visual evidence used
to check claims, layout, and figure interpretation.
