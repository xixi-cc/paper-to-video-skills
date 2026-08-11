# Codex Single-Task Checklist

This file retains the original relative path for repository compatibility. Use it as a checklist in the active Codex task; do not require a subagent.

## Slides

1. Inspect the source PDF with the official PDF skill.
2. Extract structured Markdown when useful.
3. Read `../../paper-to-beamer/references/content-writing-guide.md`. Extract the
   paper-specific problem, prior gap, variables and assumptions, connected
   method or derivation chain, quantitative findings, interpretation, and
   author-stated limitations before planning pages. Apply this independently to
   every paper in a batch without leaving the end-to-end batch workflow.
4. Define internally the intended audience, the understanding they should leave
   with, the central paper result, and the narrative arc. Give each substantive
   page one job, one primary claim, supporting evidence, and a logical
   connection to neighboring pages. Do not emit separate planning files or
   pause the batch for approval.
5. Create or refine the 16:10 SUSTech Beamer source. Choose page count, order,
   titles, evidence, and takeaways from this paper rather than a fixed manifest.
   Prefer paper-specific, claim-led titles over generic topic labels and avoid
   formulaic title patterns repeated across papers. In a batch, make these
   choices independently for every paper without classifying papers.
6. Make every substantive page do more than remain understandable without
   narration. Give the reader a complete local argument: the question or
   condition, mechanism or evidence, paper-specific technical information, and
   the resulting conclusion. Use enough connected definitions, assumptions,
   values, comparisons, or reasoning steps to perform that page's narrative job
   rather than stopping after sparse keywords and one takeaway. Give figure
   pages the measured quantity, comparison condition, decisive trend or value,
   and significance; give equation pages definitions, conditions, and physical
   meaning without changing the established page layouts.
7. Preserve decisive values, parameter dependence, comparisons, errors, or
   uncertainty from the paper. Do not reuse substantive frame bodies or generic
   robustness, limitation, implication, and future-work text across papers.
   Explain what each major evidence item changes in the interpretation.
8. If the source is too thin or an essential derivation, caption, table, or
   definition is unreadable, retry extraction or narrow and report the claim.
   Never fill the gap with generic or invented scientific detail. Make the last
   substantive page resolve the opening question with the result, mechanism,
   strongest evidence, and boundary.
9. Compile with XeLaTeX and render every page. Treat this first complete render
   as a draft.
10. Perform one cold-read revision for this paper before narration or TTS. Hide
    narration, read the contact sheet in order as a first-time viewer, and then
    inspect every substantive page. Recover the opening question, cumulative
    reasoning, central result, and conclusion boundary from the visible deck.
    Perform an information-density revision: find large unused canvas,
    title-plus-one-block pages, undeveloped bullets, and figure pages with only
    generic captions. Reopen the paper evidence for weak, ambiguous, overstrong,
    or incomplete local arguments and restore supported definitions,
    assumptions, parameter values, quantitative comparisons, intermediate
    reasoning, uncertainty, or conclusion scope that was omitted or left only
    in narration. Edit `paper_presentation.json` directly. Merge adjacent sparse
    frames when they form one argument; split only when supported content is
    genuinely hard to read. Do not preserve an initial or batch-wide page count,
    pad with generic prose, emit a separate critique artifact, or pause the batch
    for approval.
11. Rerender, recompile, and inspect the complete revised deck. Fix pages whose
    topic and main claim are not clear within five seconds, as well as errors,
    overflow, unreadable formulas, and weak figures. Record the required
    standalone-readability QA only from this revised render. In a batch, perform
    this full pass independently for each paper rather than one aggregate skim.

## Video

1. Parse explicit frames and implicit section-divider pages.
2. Write self-contained narration for every rendered page.
3. Verify PNG/TXT/MP3 one-to-one coverage.
4. Assemble and inspect the MP4 with FFmpeg/FFprobe.

## Upload

1. Validate MP4, cover, and metadata.
2. Show the proposed upload fields to the user.
3. Upload only after explicit confirmation using:

   ```bash
   python path/to/bilibili-video-uploader/scripts/upload.py PAPER_DIR --confirm-upload
   ```

Resolve every path at runtime. Never insert usernames, drive letters, credentials, or global skill locations.
