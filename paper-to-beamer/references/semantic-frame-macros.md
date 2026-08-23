# Semantic frame macros

Use these content-level macros in `slides[].latex_body`. The manifest renderer
creates the outer `frame`; never wrap these examples in another `frame`.

## Dedicated paper figure

Set `kind` to `figure` and `frame_options` to `plain,c`:

```latex
\paperfigure{figures/phase-diagram.pdf}{2b}{Temperature is varied at fixed
density; the ordered region ends continuously at $T_c$.}{The boundary supports
a continuous, rather than first-order, transition.}
```

The four arguments are asset path, paper figure/panel label, evidence-bearing
caption, and visible takeaway. Keep a figure evidence locator and asset hash in
the manifest.

## Equation derivation

Set `kind` to `equation`. The second argument is the body of an `aligned`
environment, without outer math delimiters:

```latex
\equationderivation
  {$k\ell\ll1$ and linear response; boundary terms vanish.}
  {\partial_t \rho &= -\nabla\!\cdot J \\
   &= D\nabla^2\rho}
  {$J=-D\nabla\rho$ closes conservation and fixes the sign of diffusion.}
  {The assumptions reduce the dynamics to a stable diffusive mode.}
```

## Baseline comparison

Set `kind` to `comparison`:

```latex
\baselinecomparison
  {Same dataset, split, backbone, and evaluation budget.}
  {Top-1 accuracy}
  {$81.2\%$}
  {$84.7\%$}
  {$+3.5$ percentage points}
  {The gain survives a matched-budget comparison.}
```

Keep scientific wording and values paper-specific. The macros standardize
layout and validation, not the evidence or interpretation.
