# Beamer content writing guide

Use this guide for every single-paper and batch-generated Beamer deck. Apply
the same reading and writing depth to each paper in a batch. Do not classify
papers or force one section order; select only the content the paper actually
supports.

## Contents

- Define the communication job
- Extract the paper's content
- Compose a coherent deck
- Give every frame a narrative job
- Write claim-led titles
- Write substantive frames
- Explain methods and equations
- Present evidence and results
- State limitations carefully
- Protect against thin sources
- Open and close the argument
- Run one cold-read revision
- Apply the guide in batches

## Define the communication job

Before selecting frames, state internally in one sentence what the intended
audience should understand by the end and which central paper result supports
that understanding:

> By the end, [audience] should understand [outcome] because [central result].

Infer the audience from the user's request and presentation setting when it is
already clear. Use this sentence to decide emphasis and depth; do not display
it as production language on a slide. Keep details that are necessary to
understand the main argument, and move secondary derivations, controls, or
references to backup frames when appropriate.

## Extract the paper's content

Before planning frames, extract and record:

- the precise research question and why it matters;
- the limitation of existing theory, methods, or evidence;
- the studied system, variables, parameters, assumptions, and regime;
- the complete method, derivation, or inference chain;
- the core equations and their physical or methodological meaning;
- the numerical, experimental, analytical, or comparative setup actually used;
- three to five principal findings, including the strongest quantitative
  values, trends, scaling relations, comparisons, or uncertainty statements;
- the authors' interpretation of those findings;
- limitations stated by the authors and the conclusions each limitation
  constrains;
- open questions or extensions, clearly marked when they are inferred rather
  than stated by the authors.

Use this content record to plan the deck. Do not write frames from the abstract
alone, and do not reuse substantive conclusions from another paper.

## Compose a coherent deck

Choose frame count and order from the paper's argument. Cover relevant items
from the following menu without treating it as a fixed outline:

- paper metadata and a faithful one-sentence summary;
- problem, motivation, and the specific gap in prior work;
- research object, notation, scales, assumptions, or boundary conditions;
- conceptual context and relationships to actual baselines or prior methods;
- method overview followed by key details when the logic cannot fit legibly on
  one frame;
- core equation, derivation step, mechanism, or algorithmic relationship;
- experimental, numerical, analytical, or comparison protocol when present;
- original figures, tables, quantitative results, and their interpretation;
- limitations, conclusion strength, and open questions;
- a final problem--mechanism--evidence--meaning synthesis.

Omit unsupported or irrelevant items. Do not create an "experiment" frame when
the paper has no experiments, and do not create a separate metadata, related
work, or appendix frame merely to satisfy a template.

Build a cumulative narrative rather than an agenda followed by disconnected
topic cards. A useful scientific sequence often moves from a question to the
objects and assumptions needed to formulate it, then to the method or
derivation, the resulting prediction, the evidence that tests it, its physical
meaning, and the boundary of the conclusion. Let each frame create the need for
the next; add a concise transition when the logic would otherwise jump.

## Give every frame a narrative job

Before writing each substantive frame, determine internally:

- the single job the frame performs in the argument;
- the primary claim the audience should retain;
- the figure, equation, table, or paper passage that supports it;
- how it answers or depends on the preceding frame;
- which question or inference the following frame will address.

Do not add a frame merely because the topic appeared in the paper or in a
generic outline. Remove repeated beats and combine content that does not
advance the argument. Keep this planning inside the same generation task; do
not expose it as audience-facing copy or require a separate user checkpoint.

## Write claim-led titles

Prefer titles that state the paper-specific conclusion or relationship rather
than only naming the topic. For example, replace "Parameter dependence" with a
claim such as "Reconstruction error follows the predicted scaling as sample
size grows" when the paper supports it.

Write titles a human presenter could plausibly say aloud. Avoid repeated
formulaic titles such as "Core mechanism", "Three main results", "From X to
Y", "Physical meaning", or "Next steps" across a batch. Use a neutral topic
title only when the frame introduces notation or asks a question that the next
frames will genuinely resolve.

## Write substantive frames

Every substantive frame must do more than remain understandable without
narration. Give the reader a complete local argument: the question or condition,
the mechanism or evidence, paper-specific technical information, and the
conclusion that follows. Keep one narrative job per frame, but include enough
connected information to perform that job rather than stopping after a topic
label and one takeaway.

Make each bullet add a distinct piece of information. Prefer complete,
audience-facing claims in one of these forms:

- condition or assumption -> phenomenon -> interpretation;
- method step -> intermediate object -> output;
- parameter change -> measured response -> conclusion;
- baseline difference -> quantitative result -> significance;
- limitation -> affected conclusion -> safe scope.

For a normal text frame, use enough developed content to complete the local
argument, commonly four to six distinct information units expressed through
bullets, equations, metrics, annotations, or a compact table. Include the
paper-specific object, variable, condition, assumption, value, or comparison
instead of generic phrases. Use the existing `callout` environment for the main
conclusion and `metric` for a small number of decisive values when they improve
comprehension. Do not enlarge a small amount of text or add decorative spacing
to make a sparse frame look complete.

Do not produce:

- a frame containing only a title and one short block or slogan;
- three or four undeveloped one-line bullets that together still omit the
  mechanism, concrete paper information, or resulting inference;
- keyword fragments that require narration to become meaningful;
- several bullets that paraphrase the same conclusion;
- generic claims such as "the method is effective", "the theory is verified",
  or "the result is robust" without the relevant conditions and evidence;
- copied robustness, implication, limitation, or future-work text shared across
  different papers;
- longer narration as compensation for missing visible technical content.

## Explain methods and equations

Present a method as a connected chain rather than a list of component names.
Show the input or initial condition, key variables, major transformation or
reasoning steps, output or prediction, and why the chain addresses the stated
problem. Split overview and detail across frames only when needed for
legibility.

For each principal equation, show on the frame:

- its role in the argument;
- the important symbols and control parameters;
- the assumptions, regime, or boundary conditions;
- the physical or methodological interpretation;
- the result, prediction, or later evidence that depends on it.

Do not let narration carry definitions or assumptions that are necessary to
understand the displayed equation.

## Present evidence and results

Prefer the paper's real evidence over generic summaries. Preserve useful
numbers, parameter values, exponents, error measures, uncertainty, baseline
differences, or directions of change. Recreate a compact table when the central
claim depends on comparing several conditions; highlight the decisive values
and state the conclusion below it.

After a figure, table, or result, explain what changes, under which condition,
how large or consistent the change is, and what claim it supports. A figure
does not replace analysis. Keep detailed paper figures on their existing
dedicated frames, and make the visible caption or annotation state the
measured object, comparison or control condition, decisive trend or value, and
significance. Preserve the existing dedicated figure-page layout; enrich its
caption and annotations instead of creating another layout or leaving the
analysis only in narration.

Turn evidence into meaning. For every important figure, equation, table, or
number, state what it changes in the audience's understanding: which competing
explanation it disfavors, which prediction it confirms, how it changes the
claim's strength, or why it matters for the paper's central question. Do not
present evidence as an inventory of visual assets or facts.

## State limitations carefully

Separate:

- limitations explicitly stated by the authors;
- limitations directly implied by the demonstrated parameter or data range;
- new open questions inferred during the presentation.

State which claim or extrapolation each limitation affects. Label inferred
questions as interpretation or proposed follow-up, not as an author claim.

## Protect against thin sources

Do not manufacture completeness when the accessible source is insufficient.
If the full text, derivation, caption, table, parameter definition, or result is
missing or unreadable:

- do not replace it with generic scientific prose;
- do not invent numbers, variables, assumptions, baselines, or author views;
- narrow the visible claim to what the inspected evidence supports;
- mark the missing anchor explicitly and report it;
- retry extraction or use another available paper artifact before drafting the
  affected frame.

Treat an abstract-only understanding as insufficient for a polished full-paper
deck. In a batch, isolate the affected paper rather than lowering the content
quality of the whole batch.

## Open and close the argument

Open with the question, gap, tension, or unexplained observation that makes the
paper worth understanding. Make the closing resolve that opening by stating:

- what the paper establishes;
- which method or mechanism produces the result;
- which evidence most strongly supports it;
- where the conclusion stops and what remains open.

Do not end the scientific argument on an unframed technical detail, a generic
summary, references, or "Thank you". References and Q&A may follow, but the
last substantive frame must complete the problem--evidence--meaning loop.

## Run one cold-read revision

After the first complete deck has compiled and every page has been rendered,
perform one full revision from the perspective of an informed reader who has
not heard the narration. Hide the narration and initially avoid consulting the
planning notes or evidence map. Read the contact sheet in order, then inspect
each substantive page at readable size.

During this pass, revise the deck itself rather than merely listing defects:

- recover the opening question, cumulative argument, central result, and
  conclusion boundary from the visible pages alone;
- remove repeated narrative beats and repair jumps where one inference lacks
  the definition, method step, comparison, or evidence needed to follow it;
- make every page visibly identify its object or question, primary claim,
  supporting evidence or mechanism, and implication;
- perform an information-density revision on every substantive page: identify
  large unused canvas, a title plus one short block, several undeveloped bullets,
  or a figure with only a generic caption as signs that the local argument is
  incomplete;
- restore source-supported technical content that was omitted or left only in
  narration, such as definitions, assumptions, parameter values, quantitative
  comparisons, intermediate reasoning steps, uncertainty, or conclusion scope;
- merge adjacent sparse frames when their combined material forms one coherent
  local argument; split a frame only when the supported content is genuinely
  difficult to scan or read, not to preserve a planned page count;
- check that figure and equation pages explain what the artifact establishes,
  not only what it contains;
- reopen the source paper and evidence locator for every ambiguous, weak, or
  overstrong claim, then correct the visible wording to match the source;
- merge, split, reorder, add, or delete frames when that paper's argument
  requires it. Let the revised page count differ from the initial plan.

Do not fill space with generic background, repeated conclusions, invented
details, longer narration, or cosmetic enlargement. Increase density only with
information that advances the paper-specific local argument and is supported by
the inspected source.

Apply revisions directly to `paper_presentation.json`, preserve stable IDs for
unchanged frames, rerender the generated TeX, and compile and inspect the whole
deck again. Do not create a separate critique document or pause for approval.
Create the final visual-review receipt only from this revised render. Narration
and TTS may begin only after this embedded revision is complete.

## Apply the guide in batches

Keep content authorship inside the same end-to-end batch task. For each paper,
perform the extraction, planning, manifest writing, compilation, and visual
review before or while the shared batch queues advance. Reuse extraction tools,
rendering infrastructure, caches, TTS workers, and FFmpeg workers, but never
reuse substantive frame bodies or paper conclusions.

Do not generate a batch by changing only the title, equation, and three figures
inside one fixed manifest. Each paper must have its own argument, content depth,
page count, page titles, quantitative evidence, limitations, and takeaways.
Apply the communication job, narrative arc, frame jobs, claim-led titles,
source protection, and opening--closing loop independently to every paper while
keeping them inside the same continuous batch workflow.

Run the cold-read revision separately for each paper as soon as that paper's
first complete render is ready; do not replace it with one aggregate skim of the
batch. Reconsider that paper's frame count, order, and depth during the pass
without classifying it or borrowing another paper's structure. Shared workers
may continue extraction, rendering, TTS, and encoding for other ready papers,
but a paper must finish its own cold-read revision before entering narration and
TTS.
