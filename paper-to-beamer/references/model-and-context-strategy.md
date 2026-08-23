# Model and context strategy

Read this reference only when choosing a model profile, optimizing a batch, or
investigating excessive token use. It is not part of the ordinary per-paper
prompt.

## Route by judgment load

- Use `gpt-5.6-sol` with `medium` reasoning only for presentation-Beamer content
  quality: scientific interpretation, derivation and claim checks, narrative
  structure, slide text, equations, figure choice, information density,
  content-related layout, and the narration-hidden cold read.
- Use `gpt-5.6-terra` with `medium` reasoning for source intake, PDF extraction,
  deterministic rendering or compilation of unchanged content, mechanical
  theme/path/font/macro repair, narration, TTS, video assembly, promotional
  posters, and authorized upload handling.
- Prefer a script over any model for downloading, hashing, archive extraction,
  page counting, file conversion, compilation, rendering, cache decisions, and
  media validation.

Do not split one paper's scientific authorship across multiple workers. The
Sol owns only the content-quality gate. Terra may consume, compile, render, and
package its canonical artifacts without another Sol pass while their hashes and
review evidence remain current. A mixed Skill such as `paper-to-video` invokes
Sol only when that gate is missing, stale, or fails. Change these defaults only
after a same-paper quality, latency, retry, and token comparison demonstrates a
better route.

## Keep context evidence-shaped

1. For arXiv source, read the generated `source/source-index.json` before the
   TeX tree. Add paper-page claims to the evidence map only after checking the
   indexed source range against the rendered PDF.
2. Open only the paper sections and assets needed for the current narrative
   block. Do not preload full PDF text, MinerU Markdown, and the complete TeX
   tree together.
3. Write slide-level scientific decisions once into `paper_presentation.json`.
   Rendering and later slide revisions consume that manifest instead of asking
   a model to reconstruct the paper. Keep narration and publication metadata in
   their own stage-owned files.
4. Keep stable instructions in Skill references and retain only paper-specific
   evidence in the working context. Avoid repeating quality rules in prompts.
5. Compare quality, latency, retries, and actual runtime token counters on the
   same representative papers before changing the default model or reasoning
   effort.

Accept a lower-cost model or smaller context only when the same representative
papers still compile, preserve evidence locators, remain understandable without
narration, and produce a valid page-aligned video.
