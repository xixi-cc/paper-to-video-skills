# Contributing

Thank you for improving the paper-to-presentation and paper-to-video Skills.
Keep changes focused, reproducible, and safe for users who run the workflow on
local papers and publishing accounts.

## Before opening a change

1. Open an issue or discussion for large behavior, directory-layout, licensing,
   or publication-policy changes.
2. Keep generated paper artifacts outside this repository.
3. Do not include credentials, cookies, model weights, private configuration,
   personal absolute paths, virtual environments, caches, or generated media.
4. Do not use an upload, withdrawal, or other externally consequential command
   as a smoke test.
5. Preserve existing Skill directory names because documentation and sibling
   Skill references depend on them.

Security vulnerabilities should follow [SECURITY.md](SECURITY.md), not the
public issue tracker.

## Development setup

Use Python 3.12. The repository-level validation scripts use only the Python
standard library. Install the video environment separately when changing its
runtime code:

```bash
uv sync --project pdf-slides-to-video
```

System dependencies and optional model/uploader environments are documented in
[ENVIRONMENT.md](ENVIRONMENT.md).

## Required checks

Run these checks from the repository root:

```bash
python3 scripts/validate_skills.py
python3 -m unittest discover -s tests -q
python3 scripts/check_markdown_links.py
python3 scripts/check_python_syntax.py
bash -n pdf-slides-to-video/scripts/setup_indextts2_runtime.sh
```

For Beamer or theme changes, also compile the template and visually inspect all
pages:

```bash
cd sustech-slides-template
latexmk -xelatex main_template.tex
```

For video changes, exercise the affected CLI with a small local sample, verify
the PDF page count matches the narration/audio count, and inspect the result
with `ffprobe`. Never upload the sample as part of validation.

## Skill changes

Each Skill directory must contain:

- `SKILL.md` with frontmatter fields `name` and `description`;
- a `name` matching its directory name;
- `agents/openai.yaml` with `display_name`, `short_description`, and
  `default_prompt` interface fields;
- only the scripts, references, templates, and assets needed by that Skill.

Keep descriptions concise and explicit about when the Skill should and should
not trigger. Preserve safety gates around source files, credentials, voice
cloning, and publication.

## Licensing and voice assets

By submitting a contribution, you agree that original contributions may be
distributed under the repository's [MIT License](LICENSE). Identify copied or
adapted third-party material and include its compatible license and attribution
in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Do not submit a natural person's reference voice or a voice that imitates an
identifiable person. A new synthetic or owned audio asset requires documented
provenance, explicit redistribution rights, a separate license when necessary,
and a reproducibility card. The existing Voice 319 asset remains governed by
[VOICE_LICENSE.md](VOICE_LICENSE.md).

## Pull requests

Pull requests should:

- explain the pipeline stage and user-visible behavior affected;
- list the validation commands and results;
- identify environment, model, path, credential, and license assumptions;
- include before/after screenshots for slide, poster, or cover changes;
- avoid unrelated formatting or generated-file churn.

Use a focused imperative commit message, for example
`fix: resolve Linux ffmpeg discovery`.
