# Academic video publication quality

Apply this standard to every full paper-explainer video. Speed optimizations may
reuse hashes, caches, resident models, and global worker pools; they must not
remove paper-specific evidence or shorten the explanation below these gates.
All narration must use the configured IndexTTS2 runtime and reference voice;
another local backend or a network fallback does not satisfy this standard.

## Content planning

- Read the complete paper and inspect every page before planning the deck.
- Apply the paper-to-beamer
  [`content-writing-guide.md`](../../paper-to-beamer/references/content-writing-guide.md)
  in full to
  every paper in a batch. Keep content creation inside the same end-to-end
  batch workflow, but derive each deck from that paper's own argument,
  quantitative evidence, interpretation, and limitations rather than a shared
  generic manifest body.
- Choose the slide count from technical density. Use at least 14 explicit slides
  for an 8--12 minute full explainer; do not force a fixed template count.
- Explain the research question, setup, method, core equations, principal
  evidence, quantitative results, interpretation, limitations, and takeaways.
- Treat the Beamer deck as a standalone scientific summary, not a teleprompter
  background. Every substantive page must visibly communicate (1) the object,
  question, or condition, (2) the mechanism, evidence, or quantitative
  comparison, and (3) the conclusion or implication. Narration may deepen the
  explanation but may not supply a missing main claim.
- Put a visible take-home sentence on every substantive page. For ordinary text
  pages, use three or four developed bullets with complete claims rather than
  isolated keywords. Do not create sparse pages merely to shorten batch prompts
  or reduce token use.
- Use at least three dedicated visual-evidence frames containing paper figures.
  Preserve panel labels, axes, legends, and quantitative annotations. Crop away
  surrounding paper text and recompose panels only when this improves 16:10
  legibility without changing the data.
- Use at least one core equation frame when the paper contains mathematical
  definitions or derivations. Define the displayed symbols and state the
  equation's assumptions or regime and physical meaning on the page as well as
  in narration.
- Write at least 2,200 non-whitespace Chinese narration characters for an
  8--12 minute target. Do not pad with repetition, silence, reduced playback
  speed, or generic transitions.
- Link each substantive slide to exact paper pages plus a figure, equation,
  table, reference, or URL where applicable.

## Manifest gates

Set `quality.profile` to `full-explainer` and record:

```json
{
  "quality": {
    "profile": "full-explainer",
    "target_duration_minutes": [8, 12],
    "minimum_slides": 14,
    "minimum_figure_slides": 3,
    "minimum_equation_slides": 1,
    "minimum_narration_characters": 2200,
    "maximum_narration_characters": 4200
  }
}
```

Raise paper-specific minima when the paper is denser. Do not lower the baseline.

## Visual and media gates

1. Compile and render every slide. Inspect each page at readable resolution,
   then repeat a muted five-second test: without consulting narration, identify
   the page topic and its main claim. A figure page must visibly say what is
   measured, the decisive trend, and why it matters; an equation page must show
   its role, conditions, symbols, and interpretation. Revise pages that are
   keyword-only, title-plus-one-fragment, or dependent on spoken context.
2. Write `slides-beamer/visual-qa.json` with the current PDF hash, page count,
   `all_pages_reviewed: true`, `standalone_readability_reviewed: true`, empty
   `sparse_pages`, and empty `defects`, for example:

   ```json
   {
     "slides_pdf_sha256": "...",
     "page_count": 16,
     "all_pages_reviewed": true,
     "standalone_readability_reviewed": true,
     "sparse_pages": [],
     "defects": []
   }
   ```
3. Generate native TTS at speed 1.0, then assemble the final video at the fixed
   pitch-preserving 1.25× playback rate. Require one valid pronunciation audit
   per page. Do not vary the playback rate per paper to force a duration pass.
4. Require the final duration to fall inside the manifest target, integrated
   loudness from -17 to -15 LUFS, true peak no higher than -2 dBFS, and no
   unintended silence longer than two seconds.
5. Sample the opening, multiple figure/equation pages, limitations, and closing
   from the final MP4. Write `video/video-visual-qa.json` with the current video
   hash, sampled timestamps, `all_samples_reviewed: true`, and no defects.
6. Publish only when the manifest, evidence, slide visual, pronunciation,
   audio, duration, and video visual audits all match current artifact hashes.
