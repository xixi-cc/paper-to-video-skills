# Voice 319 reproducibility card

Voice 319 is the bundled synthetic reference voice for the IndexTTS2
zero-shot narration backend. The exact prompt is distributed so that a public
checkout can reproduce the maintainer's voice identity instead of substituting
an arbitrary recording.

## Asset identity

- File: `../assets/voices/voice-319-reference.wav`
- SHA-256: `9c42096ff8f218d07f115b2d2d052d07b449f8d734374301e7a43d3bbc1232b5`
- Audio: PCM signed 16-bit little-endian, mono, 24,000 Hz
- Duration: 4.181333 seconds
- Preset ID: `319`
- License: repository-level [`VOICE_LICENSE.md`](../../VOICE_LICENSE.md), CC BY 4.0

Verify the public asset before use:

```bash
(cd pdf-slides-to-video/assets/voices && sha256sum -c SHA256SUMS)
```

## Tested synthesis identity

The maintainer's tested setup uses:

- IndexTTS2 source commit: `90ca4d608209584bad3a5bd5becc0b80c146e60f`
- `IndexTeam/IndexTTS-2` model revision: `740dcaff396282ffb241903d150ac011cd4b1ede`
- Voice mode: `zero_shot`
- `num_beams`: `1`
- Base seed: `42`
- Native TTS speed: `1.0`; the final video applies playback speed `1.25`

The remaining synthesis and loudness settings are recorded in
`tts-config.example.json`. Record the GPU, CUDA, PyTorch, FlashAttention, G2PW,
FFmpeg, and configuration revisions when comparing another machine.

## Reproduction boundary

The same verified WAV, pinned source/model revisions, configuration, text, and
pronunciation audit should preserve the intended Voice 319 timbre. They do not
guarantee bit-identical output across GPU architectures or library versions.
Use the same input text for an A/B comparison and evaluate speaker similarity,
pronunciation, cadence, and loudness separately.
