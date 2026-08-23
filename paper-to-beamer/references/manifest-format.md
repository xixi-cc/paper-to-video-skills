# Beamer manifest format

`paper_presentation.json` contains only paper metadata, source provenance, and
Beamer frames. Narration, video QA, and publication metadata belong to later
Skills.

```json
{
  "schema_version": 2,
  "paper": {
    "title_zh": "中文题目",
    "title_en": "English title",
    "short_title": "Short title",
    "authors": ["A. Author"],
    "venue": "arXiv",
    "year": "2026"
  },
  "source": {
    "primary_format": "tex",
    "provenance_path": "source/source-provenance.json",
    "tex_root": "source/tex",
    "pdf_path": "source/paper.pdf"
  },
  "slides": [
    {
      "id": "title",
      "kind": "title",
      "latex_body": "\\titlepage",
      "evidence": []
    },
    {
      "id": "main-result",
      "kind": "content",
      "title": "The measured scaling agrees with the prediction",
      "latex_body": "Supported Beamer content.",
      "evidence": [{"claim": "Claim shown on the frame", "paper_page": 5}]
    }
  ]
}
```

The executable contract is
`paper-to-video/scripts/presentation_manifest.py`. It checks required fields,
source paths and provenance, stable slide IDs, evidence locators, figure assets,
and semantic-frame layout. It deliberately imposes no fixed slide, figure,
equation, narration, duration, or publication quota.
