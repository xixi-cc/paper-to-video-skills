# arXiv source and provenance contract

Use the downloaded source as an evidence input, not as a replacement for the
presentation manifest or rendered-paper review.

## Required intake

1. Keep `source/source-provenance.json` beside the downloaded artifacts.
2. Prefer a versioned arXiv identifier. If `version_pinned` is false, disclose
   that a later rerun may retrieve a different revision.
3. Keep the source archive and its SHA-256 until the paper is finalized.
4. Do not combine TeX from one revision with a PDF from another without
   recording the mismatch in the manifest and reviewing affected claims.

For a new `paper_presentation.json`, include:

```json
{
  "source": {
    "primary_format": "tex",
    "provenance_path": "source/source-provenance.json",
    "arxiv_id": "2509.07996v4",
    "version_pinned": true,
    "pdf_path": "source/paper.pdf",
    "tex_root": "source/tex",
    "source_index_path": "source/source-index.json"
  }
}
```

Omit paths that do not exist. Legacy manifests without `source` remain valid,
but newly downloaded inputs must carry the source block.

## Content and figure priority

Use sources in this order when they are mutually consistent:

1. original vector figure from the TeX source (`.pdf`, `.svg`, `.eps` after a
   verified conversion);
2. original raster figure from the TeX source;
3. lossless crop from the rendered paper PDF;
4. MinerU-extracted image;
5. screenshot only when no higher-fidelity artifact exists.

Never choose an asset only because it has higher resolution. Verify that its
caption, panel labels, revision, and plotted values match the rendered paper.
Record the figure locator and asset SHA-256 in the slide evidence entry. Keep
detailed paper figures on dedicated `[plain,c]` frames and add a visible caption
or annotation stating the comparison condition, key trend or value, and meaning.

## Token-efficient reading

Do not place the full PDF extraction, full TeX tree, and full Markdown in model
context simultaneously. Read the generated `source/source-index.json` first,
then open only the indexed TeX ranges and assets needed for the current
argument. The index routes reading but is not itself claim evidence. Use scripts for
hashing, extraction, rendering, counting, and validation; reserve model context
for scientific interpretation, claim selection, and cold-read revision.
