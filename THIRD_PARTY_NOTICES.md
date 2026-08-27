# Third-party notices

The repository-level MIT license covers original material in this repository.
It does not replace the licenses of the projects, models, services, fonts, or
tools listed below.

## Upstream paper-to-video Skill suite

The original seven-Skill paper-to-video workflow was created and shared by the
Bilibili creator [白拾的物理AI组会](https://space.bilibili.com/98639326), also
referred to as "白拾的物理组会." This repository adapts that workflow for
Codex Desktop, Codex CLI, WSL/Linux, and physics-plus-AI research use.

The source archive originally available to this maintainer did not include a
license for the Skill suite as a whole. On 2026-08-11, the maintainer confirmed
receipt of explicit written authorization from the original creator permitting
modification, public redistribution, and distribution of the upstream and
derived Skill content under this repository's MIT License. The maintainer
retains the authorization record.

This authorization applies to the original seven-Skill workflow. The separate
arXiv source-intake Skill in this repository is an independently implemented
Codex adaptation informed by the public workflow shape of the later upstream
`paper-share-skills` release; no upstream source file is vendored. It does not
replace the separate licenses or terms of the templates, models, services,
fonts, tools, or voice assets identified below.

## SUSTech slides template

The reusable SUSTech Beamer theme is distributed under the MIT License:

- Copyright (c) 2026 杨昊波 (Haobo Yang)
- Local license: `sustech-slides-template/LICENSE`

Keep the original author notice when redistributing or modifying this theme.
The repository does not bundle an institutional logo, and use of the name
SUSTech does not imply endorsement by Southern University of Science and
Technology.

## Gemini Beamer poster theme

`markdown-to-video-cover/templates/beamerthemegemini.sty` contains material
adapted from the Gemini Beamer poster theme:

- Copyright (c) Anish Athalye (me@anishathalye.com)
- License: MIT
- Upstream: https://github.com/anishathalye/gemini
- Local license copy: `third_party_licenses/GEMINI-MIT.txt`

## IndexTTS2

IndexTTS2 source code, model weights, and generated outputs are not licensed by
this repository's MIT License and are not distributed in this repository.
Users who install or run IndexTTS2 must review and comply with
the separate Bilibili Model Use License Agreement:

https://github.com/index-tts/index-tts/blob/main/LICENSE

The upstream license includes use restrictions and downstream obligations.
Use only reference audio that you own or are authorized to clone and publish.

## Voice 319 reference audio

The repository does distribute one synthetic reference prompt:
`pdf-slides-to-video/assets/voices/voice-319-reference.wav`. It is provided by
the project maintainer under CC BY 4.0, separately from the MIT-licensed code.
See `VOICE_LICENSE.md` and
`pdf-slides-to-video/references/voice-319.md`. This grant does not replace or
expand the IndexTTS2 model license, including its terms for generated outputs.

## Other external dependencies

MinerU and the optional MinerU Open API service, G2PW, biliup, FFmpeg, Poppler,
TeX Live, uv, PyMuPDF, Pillow,
pdf2image, Requests, CUDA, PyTorch, FlashAttention, and their transitive
dependencies are installed separately. Each remains subject to its own
license and terms. The hosted MinerU route transmits input documents to the
configured service and must be selected explicitly. Bilibili upload and
withdrawal functions also require the user to comply with applicable Bilibili
platform rules. No platform,
dependency project, university, or model publisher endorses this repository.
