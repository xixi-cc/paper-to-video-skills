# Model and context strategy

Read this reference only when choosing a model profile, optimizing a batch, or
investigating excessive token use. It is not part of the ordinary per-paper
prompt.

## Route by judgment load

- Use the strongest available reasoning model for scientific interpretation,
  derivation checks, conflicting evidence, claim calibration, and the final
  narration-hidden cold read.
- A balanced model is appropriate for bounded manifest revisions when the
  evidence locators, required changes, and validation criteria are already
  explicit.
- Use a high-throughput model only for low-risk classification or normalization
  whose output is completely checked by a deterministic schema or script.
- Prefer a script over any model for downloading, hashing, archive extraction,
  page counting, file conversion, compilation, rendering, cache decisions, and
  media validation.

Do not split one paper's scientific authorship across models merely to reduce
headline token cost. Style drift, duplicated context, and a second review can
cost more than one coherent pass. Escalate after a failed evidence, equation,
or cold-read gate rather than using maximum reasoning for every mechanical step.

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
