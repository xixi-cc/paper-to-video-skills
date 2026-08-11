---
name: paper-to-beamer
description: Turn an academic paper PDF into a compiled, visually verified SUSTech Beamer presentation. Use when Codex must create or refine LaTeX Beamer slides from a paper, preserve technical equations, or prepare a Chinese group-meeting presentation.
---

# Paper to Beamer

Create Beamer as the primary editable artifact. Do not create PPTX unless the user separately requests it.

## Inputs and paths

- Accept a paper PDF and optional user constraints: audience, language, target duration, page budget, emphasis, and output directory.
- Default the paper root to `<pdf-parent>/<paper-stem> - presentation/` and the Beamer deck to its `slides-beamer/` subdirectory.
- Resolve this skill directory at runtime and copy `../sustech-slides-template/` resources from there. Never assume a global skill installation path.
- Keep the source PDF unchanged and place temporary extraction/render files below a task-specific temporary directory.

## 1. Read the paper

1. Use the official PDF skill to inspect the entire paper, render representative pages, and identify the research question, method, evidence, limitations, equations, and figures.
2. Use `pdf-to-markdown` when structured text, equations, captions, or references are needed. Fall back to direct PDF extraction when MinerU is unavailable.
3. Read and apply [`references/content-writing-guide.md`](references/content-writing-guide.md). Extract the paper-specific problem, prior gap, system and assumptions, method or derivation chain, principal quantitative findings, interpretation, and limitations before planning frames. Use the same depth for every paper in a batch.
4. Build an evidence map from each planned slide to paper pages, figures, equations, or references.

## 2. Plan the talk

Choose slide count separately for each paper from the requested duration,
technical density, and argument; do not force a fixed count across a batch. For
a normal 15–25 minute academic talk, start with 12–20 explicit content frames
plus necessary section dividers and backup slides, then allow the cold-read
revision to change that count.

Before creating the manifest, define internally: the intended audience, one
sentence stating what that audience should understand by the end, the central
paper result supporting that understanding, and the narrative arc connecting
the question, method or derivation, evidence, interpretation, and limitations.
For every substantive frame, identify its single narrative job, primary claim,
supporting paper artifact, connection to the preceding frame, and role in the
next inference. Keep this planning inside the same single-paper or batch task;
do not require a separate user checkpoint or emit additional planning files.

For a publishable 8–12 minute paper-explainer video, read and follow
[`../pdf-to-bilibili/references/publication-quality-standard.md`](../pdf-to-bilibili/references/publication-quality-standard.md).
Treat its slide, figure, equation, narration, evidence, and visual-review rules
as hard gates. Never use one fixed text-only outline for a multi-paper batch.

Cover only relevant sections:

1. title and paper metadata;
2. problem, background, and motivation;
3. related work or conceptual context;
4. definitions and notation;
5. method overview and core derivation;
6. experiments, evidence, or worked examples;
7. principal results and interpretation;
8. limitations and open questions;
9. takeaways;
10. references and Q&A;
11. optional backup material.

Adapt this structure to theoretical papers: replace forced “experiments” with derivations, examples, or implications.

Treat the list above as a content menu, not a required section sequence. Omit
irrelevant frames and expand a method, derivation, result, or comparison across
multiple frames when its logic would otherwise become a sparse summary. Do not
classify the paper before planning it; follow the argument and evidence in the
paper itself.

Before writing TeX, create `<paper-root>/paper_presentation.json` as the content source of truth. Follow `../pdf-to-bilibili/references/paper-presentation.schema.json`. Put paper metadata, one stable ID per slide, section/title/frame options, LaTeX body, concise narration, evidence locators, and Bilibili publication metadata in this file. Every non-title/content-transition slide requires at least one claim linked to a paper page, figure, equation, table, reference, or URL.

## 3. Create the Beamer source

1. Copy `main_template.tex`, `latexmkrc`, and `sustech-theme/` into `<paper-root>/slides-beamer/`; copy the template to `main.tex`.
2. Validate and render the manifest before compiling:

```bash
python ../pdf-to-bilibili/scripts/presentation_manifest.py validate "$PAPER_ROOT"
python ../pdf-to-bilibili/scripts/presentation_manifest.py render "$PAPER_ROOT"
```

This generates `presentation_metadata.tex`, `presentation_frames.tex`, `video/main_with_narration.tex`, `video/narrations.json`, `video/evidence-audit.json`, and `video/video_meta.json`. Edit the manifest rather than generated fragments.

3. Set `aspectratio=1610` and use `\usetheme{sustech}`.
4. Put the complete Chinese translation in `paper.title_zh` and the complete original English title in `paper.title_en`; the generated metadata displays both on the title page.
   Make the first manifest slide `kind: "title"` with `latex_body: "\\titlepage"`.
   Do not place a section divider, outline, or promotional image before it. This
   rendered first page is also the video and upload cover.
5. Prefer paper-specific, claim-led frame titles that state the conclusion or
   relationship rather than generic topic labels. Use a question title only
   when later frames genuinely resolve it. Avoid formulaic titles repeated
   across a batch, including generic variants of "core mechanism", "three main
   results", "physical meaning", and "next steps".
6. Make every substantive frame do more than remain understandable without
   narration. Give the reader a complete local argument: the question or
   condition, the mechanism or evidence, paper-specific technical information,
   and the conclusion that follows. Do not leave any of these exclusively in
   `narration`.
7. Give every substantive frame a visible take-home sentence, normally labeled
   `本页关键` or `结论`. A viewer who sees the muted frame for five seconds
   should be able to state both its topic and its main claim.
8. Use the available 16:10 canvas instead of producing sparse title-plus-fragment
   pages. A normal text frame should commonly contain four to six distinct,
   connected information units across bullets, equations, metrics, annotations,
   or a compact table. Each unit should express a complete claim, relationship,
   condition, definition, quantitative result, or implication rather than a
   keyword. Keep bullets concise enough to scan. Split only when the supported
   content becomes hard to read, not merely to reduce authoring effort or batch
   token use, and do not enlarge sparse content to simulate density.
9. Make every bullet add a distinct paper-specific fact or relationship. Prefer
   condition--phenomenon--interpretation, method--output--meaning, or
   comparison--result--significance. Do not repeat one conclusion in several
   phrasings or use generic claims such as "the method is effective" without
   the conditions and evidence that make the claim meaningful.
10. Present methods as connected reasoning chains: identify the input or initial
   condition, key variables, major steps, output or prediction, and why the
   chain addresses the research question. Split overview and detail only when
   needed for legibility.
11. Preserve decisive quantitative content from the paper. Use real parameter
   values, trends, exponents, errors, uncertainty, or baseline differences when
   they support the conclusion. Use the existing `metric`, compact tables, and
   `callout` constructs when they communicate this evidence clearly.
12. Explain what each important figure, equation, table, or number changes in
   the interpretation: the prediction it tests, competing explanation it
   disfavors, claim it strengthens or weakens, or consequence it establishes.
   Do not present evidence as an inventory.
13. Distinguish author-stated limitations from presentation inferences. State
   which conclusion or extrapolation each limitation constrains, and label new
   open questions as interpretation or proposed follow-up.
14. When a full-text passage, derivation, caption, table, or parameter definition
   is missing or unreadable, retry extraction or narrow and mark the affected
   claim. Never fill the gap with generic prose or invented scientific detail;
   isolate that paper's failure in a batch rather than weakening every deck.
15. Open with the paper's motivating question or gap and make the last
   substantive frame answer it with the established result, mechanism, strongest
   evidence, and conclusion boundary. References and Q&A may follow, but they
   must not replace this scientific closure.
16. Use at least `\small`; never use `\tiny` to hide overflow. Prefer concise
   complete statements, diagrams, annotations, or a second evidence item over
   enlarging a small amount of text to fill the page.
17. Keep tables to roughly five columns and six rows. Move detailed tables to backup slides.
18. Do not use overlays unless the user explicitly requests them.

### Figures

- Select figures only after inspecting the complete PDF and reading their captions plus the surrounding result discussion.
- Copy figures into `figures/` with semantic names.
- Put each detailed paper figure on a dedicated `[plain,c]` frame.
- Do not place paper figures inside `columns`, `block`, or beside dense bullets.
- Use `\fitfigure{file}` and `\figcap{N}{caption}`; retain panel labels, axes, and legends at readable size.
- Make the visible caption or annotation state what is varied/measured, the
  comparison or control condition, decisive trend or value, and why it matters.
  A figure number plus a generic caption is not self-contained. Preserve this
  dedicated figure-page layout and keep the figure dominant, but make its
  concise annotations and take-home conclusion complete the local argument.
- If extraction fails, insert an explicit placeholder and report it.
- For publication, a placeholder does not satisfy the minimum figure count. Re-render or crop the source PDF at sufficient resolution instead.

### Equations

- Preserve symbols and assumptions from the paper; do not invent missing steps.
- Put the principal equation or equivalence near the visual center of the frame.
- Prefer one principal displayed equation, or at most two short related equations, per frame.
- Split derivations across frames instead of shrinking below `\small`.
- Define symbols before using them and include a one-line interpretation after a major equation.
- Put the equation's role, assumptions or regime, and physical interpretation
  on the frame itself. Do not defer symbol definitions or the meaning of the
  result exclusively to narration.
- Put mathematical operators such as `\times` in math mode and write degrees as `$^\circ$`.

## 4. Compile, cold-read revise, and visually verify

Use the official `latex:latex-doctor` and `latex:latex-compile` skills. In this template directory, prefer:

```bash
latexmk -xelatex main.tex
```

Check the log for fatal errors, undefined controls/references, missing assets,
and overfull boxes. Render every PDF page with Poppler.

After the first complete render, perform one embedded cold-read revision before
writing the final visual receipt or starting narration. Hide narration and read
the contact sheet in order as an informed first-time viewer, then inspect every
substantive page individually. Recover the opening question, reasoning chain,
central result, and conclusion boundary from visible content alone. Identify
repetition, missing inference steps, unsupported or overstrong claims, and pages
whose figure, equation, evidence, or implication is unclear. Also perform an
information-density revision: find large unused canvas, title-plus-one-block
pages, undeveloped short bullets, and figure pages with only generic captions.
Reopen the relevant paper pages and evidence locators, then restore supported
definitions, assumptions, parameter values, quantitative comparisons,
intermediate reasoning, uncertainty, or conclusion scope that was omitted or
left only in narration. Merge adjacent sparse frames when they form one local
argument; split only when supported content is genuinely hard to read. Edit
`paper_presentation.json` directly, and never fill space with generic or
invented prose. Merge, split, reorder, add, or delete frames when the paper's
argument requires it; the revised page count need not match the initial plan.
Rerender, recompile, and inspect the complete deck again. Keep this inside the
same task and do not emit a separate critique artifact or request another
approval.

In a batch, run this full pass independently for each paper when its first
render becomes ready. Do not use one aggregate batch skim, a shared fixed page
count, or another paper's frame order. Other batch workers may continue, but
that paper must complete its own cold-read revision before narration and TTS.

Fix clipping, unreadable equations, excessive density, weak contrast, and
inconsistent figure sizing before delivery.

After the revised render has been inspected, write
`slides-beamer/visual-qa.json` as specified by the publication quality standard.
Record `standalone_readability_reviewed: true` only when every substantive
page's topic and key claim are recoverable from the frame itself. List unresolved
pages in `sparse_pages`; this list must be empty. Do not create this receipt from
the first draft or before checking every revised page; the batch pipeline
validates its PDF hash and these readability fields.

## 5. Refine from a follow-up prompt

When the user asks for changes:

1. inspect the current `main.tex` and latest rendered pages;
2. map the request to exact frames;
3. edit only the affected entries in `paper_presentation.json` and preserve stable slide IDs;
4. rerender generated fragments; do not hand-edit them;
5. recompile and rerender the complete deck;
6. compare changed pages with neighboring pages and rerun log checks;
7. report modified frame titles and the final page count.

## Deliverables

Return `main.tex`, compiled `main.pdf`, `figures/`, theme files, and a concise QA report. State the explicit-frame count separately from automatically inserted section-divider pages.
