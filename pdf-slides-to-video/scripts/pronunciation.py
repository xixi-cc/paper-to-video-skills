"""Automatic Mandarin polyphone disambiguation for local TTS backends.

G2PW predicts a tone-number pinyin syllable for each Chinese character.
Only characters covered by G2PW's polyphone inventory are replaced with
backend-specific tokens such as ``[ch][óng]`` or ``CHONG2``.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from pypinyin.contrib.tone_convert import to_finals_tone3, to_initials, to_tone


_PINYIN_RE = re.compile(r"^([a-züv]+)([1-5])$")

# Phrase-level terminology whose pronunciation cannot be determined reliably
# one character at a time. Keep this list compact and domain-specific; G2PW
# remains responsible for all other polyphones.
_ACADEMIC_PHRASE_PINYIN: dict[str, tuple[str, ...]] = {
    "度量": ("du4", "liang4"),
    "重参数化": ("chong2", "can1", "shu4", "hua4"),
}


@dataclass(frozen=True)
class PronunciationReplacement:
    index: int
    character: str
    pinyin: str
    hotfix: str


def pinyin_to_cosyvoice_hotfix(pinyin: str) -> str:
    """Convert tone-number pinyin, e.g. ``chong2``, to ``[ch][óng]``."""
    normalized = pinyin.strip().lower().replace("u:", "v")
    match = _PINYIN_RE.fullmatch(normalized)
    if not match:
        raise ValueError(f"Unsupported G2PW pinyin syllable: {pinyin!r}")
    initial = to_initials(normalized, strict=True)
    numeric_final = to_finals_tone3(normalized, strict=True)
    if not numeric_final:
        raise ValueError(f"Cannot split pinyin syllable: {pinyin!r}")
    tone = numeric_final[-1] if numeric_final[-1].isdigit() else "5"
    final = numeric_final[:-1] if numeric_final[-1].isdigit() else numeric_final
    # CosyVoice uses standard written-pinyin contractions for these finals.
    final = {"iou": "iu", "uei": "ui", "uen": "un"}.get(final, final)
    toned_final = to_tone(f"{final}{tone}")
    return f"[{initial}][{toned_final}]" if initial else f"[{toned_final}]"


def pinyin_to_indextts2_token(pinyin: str) -> str:
    """Convert tone-number pinyin, e.g. ``chong2``, to ``CHONG2``."""
    normalized = pinyin.strip().lower().replace("u:", "v").replace("ü", "v")
    if not _PINYIN_RE.fullmatch(normalized):
        raise ValueError(f"Unsupported G2PW pinyin syllable: {pinyin!r}")
    return normalized.upper()


class G2PWPronouncer:
    """Load G2PW once and inject deterministic backend pronunciation tokens."""

    def __init__(
        self,
        model_dir: str | Path,
        output_style: str = "indextts2",
        pinyin_vocab: str | Path | None = None,
    ):
        from g2pw import G2PWConverter

        if output_style != "indextts2":
            raise ValueError(f"Unsupported pronunciation output style: {output_style}")
        self.model_dir = Path(model_dir).expanduser().resolve()
        self.output_style = output_style
        self.valid_pinyin: set[str] | None = None
        if pinyin_vocab:
            vocab_path = Path(pinyin_vocab).expanduser().resolve()
            self.valid_pinyin = {
                line.strip() for line in vocab_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            }
        self.model_dir.parent.mkdir(parents=True, exist_ok=True)
        self.converter = G2PWConverter(
            model_dir=str(self.model_dir),
            style="pinyin",
            enable_non_tradional_chinese=True,
        )
        # WSL may expose a Windows TMP directory where multiprocessing sockets
        # are unsupported; inference is small enough to keep data loading local.
        self.converter.num_workers = 0
        self.converter.session_g2pw.set_providers(["CPUExecutionProvider"])
        self.polyphonic_chars = set(self.converter.chars)

    def process(self, text: str) -> dict[str, Any]:
        if not text.strip():
            raise ValueError("Narration text is empty")
        predictions = self.converter(text)[0]
        if len(predictions) != len(text):
            raise RuntimeError("G2PW character alignment mismatch")

        rendered: list[str] = []
        replacements: list[PronunciationReplacement] = []
        index = 0
        phrases = sorted(_ACADEMIC_PHRASE_PINYIN, key=len, reverse=True)
        while index < len(text):
            phrase = next((item for item in phrases if text.startswith(item, index)), None)
            if phrase is not None:
                phrase_pinyin = _ACADEMIC_PHRASE_PINYIN[phrase]
                if self.output_style == "indextts2":
                    phrase_tokens = [pinyin_to_indextts2_token(item) for item in phrase_pinyin]
                    if self.valid_pinyin is not None:
                        normalized_tokens = []
                        for token in phrase_tokens:
                            if token not in self.valid_pinyin:
                                token = re.sub(r"^(J|Q|X|Y)U", r"\1V", token)
                            if token not in self.valid_pinyin:
                                raise RuntimeError(
                                    f"IndexTTS2 phrase token {token!r} is absent from pinyin.vocab"
                                )
                            normalized_tokens.append(token)
                        phrase_tokens = normalized_tokens
                else:
                    phrase_tokens = [pinyin_to_cosyvoice_hotfix(item) for item in phrase_pinyin]
                hotfix = "".join(phrase_tokens)
                rendered.append(hotfix)
                replacements.append(
                    PronunciationReplacement(
                        index, phrase, " ".join(phrase_pinyin), hotfix
                    )
                )
                index += len(phrase)
                continue

            character = text[index]
            pinyin = predictions[index]
            traditional = self.converter.s2t_dict.get(character, character)
            if traditional not in self.polyphonic_chars:
                rendered.append(character)
                index += 1
                continue
            if not pinyin:
                raise RuntimeError(
                    f"G2PW returned no pronunciation for polyphone {character!r} "
                    f"at character {index}"
                )
            if self.output_style == "indextts2":
                hotfix = pinyin_to_indextts2_token(pinyin)
                if self.valid_pinyin is not None and hotfix not in self.valid_pinyin:
                    # IndexTTS2 writes the ü final as V after j/q/x/y in its
                    # vocabulary (for example, xun2 -> XVN2 and jue2 -> JVE2),
                    # while G2PW returns standard orthographic pinyin. Resolve
                    # that systematic spelling difference before rejecting a
                    # pronunciation as unsupported.
                    vocab_hotfix = re.sub(r"^(J|Q|X|Y)U", r"\1V", hotfix)
                    if vocab_hotfix in self.valid_pinyin:
                        hotfix = vocab_hotfix
                    else:
                        raise RuntimeError(
                            f"IndexTTS2 pinyin token {hotfix!r} is absent from pinyin.vocab"
                        )
            else:
                hotfix = pinyin_to_cosyvoice_hotfix(pinyin)
            rendered.append(hotfix)
            replacements.append(
                PronunciationReplacement(index, character, pinyin, hotfix)
            )
            index += 1

        return {
            "source_text": text,
            "tts_text": "".join(rendered),
            "replacements": [asdict(item) for item in replacements],
            "polyphone_count": len(replacements),
            "engine": "g2pw",
            "output_style": self.output_style,
        }


def process_manifest(manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    pronouncer = G2PWPronouncer(
        manifest["model_dir"],
        output_style=manifest.get("output_style", "indextts2"),
        pinyin_vocab=manifest.get("pinyin_vocab"),
    )
    return {
        "items": [
            {"name": item["name"], **pronouncer.process(item["text"])}
            for item in manifest["items"]
        ]
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Inject G2PW pronunciations for local TTS")
    parser.add_argument("text", nargs="?")
    parser.add_argument("--model-dir")
    parser.add_argument("--output-style", choices=("indextts2",), default="indextts2")
    parser.add_argument("--pinyin-vocab")
    parser.add_argument("--batch-manifest", type=Path)
    args = parser.parse_args()
    if args.batch_manifest:
        result = process_manifest(args.batch_manifest.resolve())
        print("PRONUNCIATION_RESULT_JSON=" + json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return
    if not args.text or not args.model_dir:
        parser.error("text and --model-dir are required without --batch-manifest")
    result = G2PWPronouncer(
        args.model_dir,
        output_style=args.output_style,
        pinyin_vocab=args.pinyin_vocab,
    ).process(args.text)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
