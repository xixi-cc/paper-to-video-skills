"""
slides_to_video.py — PDF slides to narrated MP4 video pipeline.

Functions:
  parse_beamer_frames(tex_path) -> list[dict]
  parse_beamer_preamble(tex_path) -> dict
  get_page_plan(tex_path) -> list[dict]
  extract_narrations_from_tex(tex_path) -> dict
  write_narrations_to_files(frame_dir, tex_path, annotated_tex_path=None) -> dict
  extract_pdf_text(pdf_path) -> list[str]
  render_slides(pdf_path, output_dir, dpi=200) -> list[str]
  generate_cover(title_slide_path, output_path) -> str
  generate_metadata(preamble, frames, cover_path, output_path) -> str
  tts_slide(text, output_path, lang='zh') -> bool
  assemble_video(frame_dir, output_path, fps=30) -> None

Usage:
  python -c "from slides_to_video import render_slides; render_slides('main.pdf', 'frames')"
  python slides_to_video.py PAPER_DIR
"""

import json
import hashlib
import contextlib
import os
import re
import subprocess
import sys
import time
from pathlib import Path


DEFAULT_PLAYBACK_SPEED = 1.25


# ─── LaTeX parsing utilities ───────────────────────────────────────────────

def _strip_latex_macros(text: str) -> str:
    """Strip LaTeX macros keeping their inner text content.

    Handles: \\shl{...}, \\hlbox{...}, \\keyword{...}, \\brandemph{...},
    \\textbf{...}, \\emph{...}, \\textit{...}, \\textsuperscript{...},
    \\cite{...}, \\href{url}{text} -> text, \\metric{val}{label} -> val (label),
    \\domaintag{...}, \\cmark, \\xmark, \\tightgap, \\deckgap, \\smallskip,
    \\medskip, \\figcap{...}{...}, \\setlength{...}{...}, \\renewcommand{...}{...}.
    """
    # Remove comments
    text = re.sub(r'(?<!\\)%.*$', '', text, flags=re.MULTILINE)

    # \\href{url}{text} -> text
    text = re.sub(r'\\href\{[^}]*\}\{([^}]*)\}', r'\1', text)

    # \\cite{...} -> empty (citations add nothing to spoken narration)
    text = re.sub(r'\\cite\{[^}]*\}', '', text)

    # Strip wrapper macros keeping inner content (handle nested braces)
    wrapper_macros = [
        r'\shl', r'\hlbox', r'\keyword', r'\brandemph',
        r'\textbf', r'\emph', r'\textit', r'\textsuperscript',
        r'\domaintag', r'\thc',
    ]
    for macro in wrapper_macros:
        # Match macro{...} with balanced braces
        text = _strip_balanced_brace_macro(text, macro)

    # \\metric{val}{label} -> val (label)
    text = re.sub(r'\\metric\{([^}]*)\}\{([^}]*)\}', r'\1 (\2)', text)

    # Remove standalone symbols and spacing commands
    text = re.sub(r'\\cmark\b', '', text)
    text = re.sub(r'\\xmark\b', '', text)
    text = re.sub(r'\\tightgap\b', '', text)
    text = re.sub(r'\\deckgap\b', '', text)
    text = re.sub(r'\\smallskip\b', '', text)
    text = re.sub(r'\\medskip\b', '', text)
    text = re.sub(r'\\figcap\{[^}]*\}\{[^}]*\}', '', text)
    text = re.sub(r'\\setlength\{[^}]*\}\{[^}]*\}', '', text)
    text = re.sub(r'\\renewcommand\{\\secblurb\}\{([^}]*)\}', '', text)
    text = re.sub(r'\\begin\{[^}]*\}', '', text)
    text = re.sub(r'\\end\{[^}]*\}', '', text)

    # Remove inline math $...$
    text = re.sub(r'\$[^$]*\$', '', text)

    # Remove \\[dimension] and \vspace{...}
    text = re.sub(r'\\\\\[\d+[a-z]*\]', '', text)
    text = re.sub(r'\\vspace\{[^}]*\}', '', text)

    # Remove \\ alone at line end (but not line breaks in general)
    text = re.sub(r'\\\\$', '', text, flags=re.MULTILINE)

    # Collapse whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()

    return text


def _strip_balanced_brace_macro(text: str, macro: str) -> str:
    """Strip \\macro{...} where braces are balanced, keeping inner content."""
    pattern = re.escape(macro) + r'\{'
    result = []
    i = 0
    while i < len(text):
        m = re.search(pattern, text[i:])
        if not m:
            result.append(text[i:])
            break
        start = i + m.start()
        brace_start = start + len(macro) + 1  # after {
        result.append(text[i:start])

        # Find matching closing brace
        depth = 1
        j = brace_start
        while j < len(text) and depth > 0:
            if text[j] == '{':
                depth += 1
            elif text[j] == '}':
                depth -= 1
            if depth > 0:
                j += 1

        inner = text[brace_start:j]
        result.append(inner)
        i = j + 1  # skip past }
    return ''.join(result)


def _extract_braced_arg(text: str) -> str:
    """Extract content inside the first pair of balanced braces."""
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == '{':
            if depth == 0:
                start = i + 1
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start >= 0:
                return text[start:i]
    return ''


def _extract_bracketed_arg(text: str) -> str:
    """Extract optional [...] argument content."""
    m = re.match(r'\s*\[([^\]]*)\]', text)
    return m.group(1) if m else ''


# ─── Preamble parsing ──────────────────────────────────────────────────────

_CONFERENCE_TID_MAP = {
    # AI / Robotics → 209 (人工智能)
    'RSS': 209,
    'ICRA': 209,
    'IROS': 209,
    'CoRL': 209,
    'RA-L': 209,
    'Science Robotics': 209,
    'Robotics: Science and Systems': 209,
    # CS / CV / ML → 208 (计算机技术)
    'CVPR': 208,
    'ICCV': 208,
    'ECCV': 208,
    'NeurIPS': 208,
    'ICML': 208,
    'ICLR': 208,
    'ACL': 208,
    'EMNLP': 208,
    'AAAI': 208,
    'IJCAI': 208,
    'SIGGRAPH': 208,
    'CHI': 208,
    # General science → 124 (科学科普)
    'Nature': 124,
    'Science': 124,
    'PNAS': 124,
    'arXiv': 124,
}


def _lookup_tid(venue: str) -> tuple:
    """Return (tid, tid_name) for a conference/journal venue."""
    for key, tid in _CONFERENCE_TID_MAP.items():
        if key.lower() in venue.lower():
            tid_names = {124: '科学科普', 208: '计算机技术', 209: '人工智能', 210: '软件应用'}
            return tid, tid_names.get(tid, '计算机技术')
    return 208, '计算机技术'


def parse_beamer_preamble(tex_path: str) -> dict:
    """Extract {title, subtitle, author, venue, year, domains, urls} from Beamer preamble.

    Parses: \\title, \\subtitle, \\author, \\setsource{venue}{year},
    \\setdomains{\\domaintag{...}...}, and \\href{url}{text} in 论文信息 frame.
    """
    with open(tex_path, 'r', encoding='utf-8') as f:
        content = f.read()

    result = {
        'title': '', 'short_title': '', 'subtitle': '',
        'author': '', 'venue': '', 'year': '',
        'domains': [], 'source_url': '', 'code_url': '', 'project_url': '',
    }

    # \\title[short]{full}
    m = re.search(r'\\title(?:\[([^\]]*)\])?\{((?:[^{}]|\{[^{}]*\})*)\}', content)
    if m:
        result['short_title'] = m.group(1) or ''
        result['title'] = _strip_latex_macros(m.group(2))

    # \\subtitle{...}
    m = re.search(r'\\subtitle\{((?:[^{}]|\{[^{}]*\})*)\}', content)
    if m:
        result['subtitle'] = _strip_latex_macros(m.group(1))

    # \\author[short]{full}
    m = re.search(r'\\author(?:\[([^\]]*)\])?\{([^}]*(?:\{[^}]*\}[^}]*)*)\}', content)
    if m:
        result['author'] = _strip_latex_macros(m.group(2))

    # \\setsource{venue}{year}
    m = re.search(r'\\setsource\{([^}]*)\}\{([^}]*)\}', content)
    if m:
        result['venue'] = m.group(1).strip()
        result['year'] = m.group(2).strip()

    # \\setdomains{\\domaintag{...}\\domaintag{...}...} — handles nested braces
    m = re.search(r'\\setdomains\{', content)
    if m:
        start = m.end()
        depth = 1
        pos = start
        while pos < len(content) and depth > 0:
            if content[pos] == '{':
                depth += 1
            elif content[pos] == '}':
                depth -= 1
            pos += 1
        domains_text = content[start:pos-1]
        for dm in re.finditer(r'\\domaintag\{([^}]*)\}', domains_text):
            result['domains'].append(dm.group(1))

    # Extract URLs from 论文信息 frame: \\href{url}{text}
    # Look for the frame: \\begin{frame}{论文信息} ... \\end{frame}
    info_frame = re.search(
        r'\\begin\{frame\}\{论文信息\}(.*?)\\end\{frame\}', content, re.DOTALL)
    if info_frame:
        frame_text = info_frame.group(1)
        hrefs = re.findall(r'\\href\{([^}]*)\}\{([^}]*)\}', frame_text)
        for url, label in hrefs:
            if 'github' in url.lower():
                result['code_url'] = url
            elif 'huggingface' in url.lower() or 'project' in label.lower() or 'website' in label.lower():
                result['project_url'] = url
            elif 'arxiv' in url.lower() or 'paper' in label.lower():
                result['source_url'] = url
            elif result['project_url']:
                pass  # already set
            elif not result['source_url']:
                result['source_url'] = url
            else:
                result['project_url'] = url

    return result


# ─── Frame parsing ─────────────────────────────────────────────────────────

def parse_beamer_frames(tex_path: str) -> list:
    """Parse Beamer .tex into structured frame data.

    Returns list of dicts: {
        page_num: int, title: str, section: str, blurb: str,
        items: [str], callout: str, block_text: str,
        has_figure: bool, is_plain: bool, metrics: [(str, str)]
    }
    Pages are numbered from 1 following the frame order in the .tex file.
    """
    with open(tex_path, 'r', encoding='utf-8') as f:
        content = f.read()

    frames = []
    current_section = ''
    current_blurb = ''
    page_num = 0

    # Track \\renewcommand{\\secblurb}{...}
    blurb_positions = list(re.finditer(
        r'\\renewcommand\{\\secblurb\}\{((?:[^{}]|\{[^{}]*\})*)\}', content))
    blurb_map = {}  # char position -> blurb text
    for m in blurb_positions:
        blurb_map[m.start()] = _strip_latex_macros(m.group(1))

    # Track \\section{...}
    section_positions = list(re.finditer(r'\\section\{([^}]*)\}', content))
    sections = [(m.start(), m.group(1)) for m in section_positions]

    # Find all frames
    # Match \begin{frame}[opts]{title} or \begin{frame}[opts] (titleless, e.g. \titlepage)
    frame_starts = list(re.finditer(
        r'\\begin\{frame\}(?:\[([^\]]*)\])?(?:\{([^}]*)\})?', content))

    for idx, fm in enumerate(frame_starts):
        page_num += 1
        frame_opts = fm.group(1) or ''
        frame_title = _strip_latex_macros(fm.group(2) or '')

        # Find the matching \end{frame}
        # \end{frame} = 11 chars, \begin{frame} = 13 chars
        depth = 1
        pos = fm.end()
        while pos < len(content) and depth > 0:
            if content[pos:pos+11] == '\\end{frame}':
                depth -= 1
                if depth == 0:
                    break
                pos += 11
            elif content[pos:pos+13] == '\\begin{frame}':
                depth += 1
                pos += 13
            else:
                pos += 1
        frame_body = content[fm.end():pos]

        # Determine section context for this frame
        frame_char_start = fm.start()
        for s_start, s_name in reversed(sections):
            if s_start < frame_char_start:
                current_section = s_name
                break
        # Find most recent blurb before this frame
        for b_start in sorted(blurb_map.keys(), reverse=True):
            if b_start < frame_char_start:
                current_blurb = blurb_map[b_start]
                break

        # Extract items
        items = []
        item_matches = re.findall(r'\\item\s+(.*?)(?=\\item|\\(?:begin|end)\{|$)',
                                  frame_body, re.DOTALL)
        for item_text in item_matches:
            cleaned = _strip_latex_macros(item_text).strip()
            if cleaned and len(cleaned) > 2:
                items.append(cleaned)

        # Extract callout
        callout_text = ''
        callout_m = re.search(
            r'\\begin\{callout\}(?:\[([^\]]*)\])?\s*(.*?)\\end\{callout\}',
            frame_body, re.DOTALL)
        if callout_m:
            callout_text = _strip_latex_macros(callout_m.group(2)).strip()

        # Extract block/exampleblock text
        block_text = ''
        for block_env in ['block', 'exampleblock']:
            for block_m in re.finditer(
                    rf'\\begin\{{{block_env}\}}\{{[^}}]*\}}\s*(.*?)\\end\{{{block_env}\}}',
                    frame_body, re.DOTALL):
                block_text += _strip_latex_macros(block_m.group(1)) + '\n'

        # Extract metrics
        metrics = []
        for mm in re.finditer(r'\\metric\{([^}]*)\}\{([^}]*)\}', frame_body):
            metrics.append((mm.group(1).strip(), mm.group(2).strip()))

        # Detect figures
        has_figure = bool(re.search(r'\\includegraphics', frame_body))

        # Detect plain figure frames
        is_plain = 'plain' in frame_opts

        # Detect special frames to potentially skip
        is_titlepage = '\\titlepage' in frame_body
        is_toc = '\\tableofcontents' in frame_body
        is_qa = 'Q&A' in frame_title or 'Q\\&A' in frame_title

        frames.append({
            'page_num': page_num,
            'title': frame_title,
            'section': current_section,
            'blurb': current_blurb,
            'items': items,
            'callout': callout_text,
            'block_text': block_text.strip(),
            'has_figure': has_figure,
            'is_plain': is_plain,
            'is_titlepage': is_titlepage,
            'is_toc': is_toc,
            'is_qa': is_qa,
            'metrics': metrics,
        })

    return frames


def extract_narrations_from_tex(tex_path: str) -> dict:
    """Extract % NARRATION: comments from an annotated .tex file.

    Matches each narration to its nearest preceding \\end{frame} line,
    keyed by that frame's 1-indexed position among all frames.
    This correctly handles missing/extra narrations — each narration
    stays aligned to its intended frame by position, not by count.
    """
    with open(tex_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Find all \\end{frame} positions with their 1-indexed frame numbers
    frame_ends = []  # (line_index, frame_number)
    frame_count = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('\\end{frame}'):
            frame_count += 1
            frame_ends.append((i, frame_count))

    # Match each % NARRATION: to its nearest preceding \\end{frame}
    narrations = {}
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('% NARRATION:'):
            text = stripped[len('% NARRATION:'):].strip()
            # Walk backward to find the nearest preceding \\end{frame}
            nearest_frame = None
            for fe_line, fe_num in reversed(frame_ends):
                if fe_line < i:
                    nearest_frame = fe_num
                    break
            if nearest_frame is not None:
                narrations[nearest_frame] = text

    return narrations

# ─── Page plan (PDF-to-frame mapping) ──────────────────────────────────────

def get_page_plan(tex_path: str, include_section_pages: bool = True) -> list:
    """Parse .tex to predict PDF page order, accounting for \\section{} pages.

    Beamer themes (Madrid, sustech) insert a section divider frame via
    \\AtBeginSection before each \\section{}. This function tracks both
    explicit \\begin{frame} blocks and implicit section frames.

    Returns a list where each entry is:
      {'type': 'frame', 'frame_idx': N, 'title': str}
      {'type': 'section', 'section_name': str}
    in document (PDF page) order.
    """
    with open(tex_path, 'r', encoding='utf-8') as f:
        content = f.read()

    plan = []
    frame_idx = 0
    in_appendix = False

    # Find all \section{...} and \begin{frame} in document order
    # Pattern matches \section{name} (possibly with leading whitespace)
    section_pat = re.compile(r'(?<!\\)\\section\{([^}]*)\}')
    # Pattern matches \begin{frame}[opts]{title} or \begin{frame}[opts]
    frame_pat = re.compile(
        r'(?<!\\)\\begin\{frame\}(?:\[([^\]]*)\])?(?:\{([^}]*)\})?')
    # Track \appendix
    appendix_pat = re.compile(r'(?<!\\)\\appendix\b')

    # Find all occurrences and sort by position
    events = []
    for m in section_pat.finditer(content):
        # Check if line is a comment
        line_start = content.rfind('\n', 0, m.start()) + 1
        if content[line_start:line_start+1] != '%':
            events.append((m.start(), 'section', m.group(1)))
    for m in frame_pat.finditer(content):
        line_start = content.rfind('\n', 0, m.start()) + 1
        if content[line_start:line_start+1] != '%':
            events.append((m.start(), 'frame', m.group(2) or ''))
    for m in appendix_pat.finditer(content):
        line_start = content.rfind('\n', 0, m.start()) + 1
        if content[line_start:line_start+1] != '%':
            events.append((m.start(), 'appendix', ''))

    events.sort(key=lambda x: x[0])

    for _pos, kind, arg in events:
        if kind == 'appendix':
            in_appendix = True
        elif kind == 'section':
            if include_section_pages and not in_appendix:
                # Only pre-appendix sections generate section pages
                plan.append({'type': 'section', 'section_name': arg})
        elif kind == 'frame':
            frame_idx += 1
            plan.append({'type': 'frame', 'frame_idx': frame_idx, 'title': arg})

    return plan


def write_narrations_to_files(frame_dir: str, tex_path: str,
                              annotated_tex_path: str = None,
                              narrate_sections: bool = True) -> dict:
    """Extract narrations and write .txt files at correct PDF page positions.

    Handles the mismatch between frame numbering and PDF page numbering
    caused by \\AtBeginSection section divider pages.

    Args:
        frame_dir: Directory to write slide_NNN.txt files.
        tex_path: Path to the original .tex (for get_page_plan).
        annotated_tex_path: Path to the annotated .tex with % NARRATION:
            comments. Defaults to tex_path.
        narrate_sections: Create short transition scripts for implicit section
            divider pages. Existing page scripts are never overwritten.

    Returns:
        dict with keys 'count', 'frame_count', 'section_pages', 'files'
    """
    if annotated_tex_path is None:
        annotated_tex_path = tex_path
    # ``narrate_sections=False`` is used by manifest-driven decks that disable
    # Beamer's automatic section frames.  In that mode section commands are
    # structural metadata, not PDF pages, so they must not offset frame indices.
    page_plan = get_page_plan(tex_path, include_section_pages=narrate_sections)
    narrations = extract_narrations_from_tex(annotated_tex_path)

    # Build frame_idx -> pdf_page mapping
    frame_to_pdf = {}
    section_pages = []
    section_entries = []
    for pdf_page, entry in enumerate(page_plan, start=1):
        if entry['type'] == 'frame':
            frame_to_pdf[entry['frame_idx']] = pdf_page
        elif entry['type'] == 'section':
            section_pages.append(pdf_page)
            section_entries.append((pdf_page, entry['section_name']))

    # Write .txt files at correct PDF page positions
    written = []
    for frame_idx, text in narrations.items():
        pdf_page = frame_to_pdf.get(int(frame_idx))
        if pdf_page is None:
            print(f'  [WARN] Narration for frame {frame_idx} has no PDF page mapping')
            continue
        path = os.path.join(frame_dir, f'slide_{pdf_page:03d}.txt')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)
        written.append(pdf_page)

    # SUSTech inserts implicit section-divider pages that have no explicit
    # \end{frame}. Give each one a deterministic transition so every rendered
    # PDF page can receive audio. A user-authored file takes precedence.
    if narrate_sections:
        for pdf_page, section_name in section_entries:
            path = os.path.join(frame_dir, f'slide_{pdf_page:03d}.txt')
            if not os.path.exists(path):
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(f'接下来进入“{section_name}”部分。')
            written.append(pdf_page)

    return {
        'count': len(written),
        'frame_count': len(narrations),
        'section_pages': section_pages,
        'files': written,
    }
# ─── PDF utilities ─────────────────────────────────────────────────────────

def extract_pdf_text(pdf_path: str) -> list:
    """Extract text from each page of a PDF using PyMuPDF.

    Returns list of strings, one per page.
    """
    import fitz
    doc = fitz.open(pdf_path)
    texts = []
    for page in doc:
        texts.append(page.get_text('text'))
    doc.close()
    return texts


def render_slides(pdf_path: str, output_dir: str, dpi: int = 200) -> list:
    """Render PDF pages to numbered PNG images.

    Args:
        pdf_path: Path to the PDF file.
        output_dir: Directory to save PNGs (created if not exists).
        dpi: Rendering resolution (default 200).

    Returns:
        List of output PNG paths, sorted by page number.
    """
    from pdf2image import convert_from_path

    os.makedirs(output_dir, exist_ok=True)

    poppler_path = os.environ.get('POPPLER_PATH')
    kwargs = {'dpi': dpi}
    if poppler_path:
        kwargs['poppler_path'] = poppler_path
    images = convert_from_path(pdf_path, **kwargs)

    paths = []
    for i, img in enumerate(images):
        out_path = os.path.join(output_dir, f'slide_{i+1:03d}.png')
        img.save(out_path, 'PNG')
        paths.append(out_path)

    return paths


# ─── Cover image ───────────────────────────────────────────────────────────

def generate_cover(title_slide_path: str, output_path: str) -> str:
    """Copy the rendered Beamer title page as the video cover."""
    import shutil
    shutil.copy(title_slide_path, output_path)
    return os.path.abspath(output_path)


# ─── Bilibili metadata ─────────────────────────────────────────────────────

VENUE_ABBREVIATIONS = {
    'arxiv': 'arXiv',
    'physical review letters': 'PRL',
    'physical review x': 'PRX',
    'physical review e': 'PRE',
    'physical review research': 'PRR',
    'nature physics': 'Nature Physics',
    'neural information processing systems': 'NeurIPS',
    'international conference on machine learning': 'ICML',
    'international conference on learning representations': 'ICLR',
}


def format_bilibili_title(
    venue: str,
    year: str,
    title_zh: str,
    max_length: int = 80,
) -> str:
    """Return ``VENUE YEAR｜Chinese title`` within Bilibili's title limit."""
    venue_clean = str(venue).strip()
    venue_label = VENUE_ABBREVIATIONS.get(venue_clean.casefold(), venue_clean)
    year_label = str(year).strip()
    title_label = str(title_zh).strip()
    prefix = f"{venue_label} {year_label}｜" if venue_label and year_label else ""
    if len(prefix) >= max_length:
        raise ValueError("Venue/year prefix leaves no room for a paper title")
    if len(prefix) + len(title_label) <= max_length:
        return prefix + title_label
    available = max_length - len(prefix)
    if available <= 1:
        raise ValueError("Bilibili title limit leaves no room for a paper title")
    return prefix + title_label[:available - 1].rstrip() + '…'

def generate_metadata(preamble: dict, frames: list, cover_path: str, output_path: str) -> str:
    """Generate video_meta.json for Bilibili upload.

    Args:
        preamble: Dict from parse_beamer_preamble().
        frames: List from parse_beamer_frames().
        cover_path: Relative path to cover.png (e.g. 'cover.png').
        output_path: Path to save video_meta.json.

    Returns:
        Absolute path to the generated JSON file.
    """
    venue = preamble.get('venue', '')
    year = preamble.get('year', '')
    title = preamble.get('title', 'Unknown Paper')
    title_en = preamble.get('subtitle', '')
    if not title_en:
        title_en = title  # fallback

    tid, tid_name = _lookup_tid(venue)

    # Tags from domains + venue + paper name
    tags = preamble.get('domains', [])
    if venue:
        tags.append(f'{venue} {year}'.strip())
    tags.append('论文分享')
    # Add paper short name if any
    short_title = preamble.get('short_title', '')
    if short_title and short_title not in tags:
        # Truncate to fit
        if len(short_title) <= 20:
            tags.insert(0, short_title)
    # Max 10 tags
    tags = tags[:10]

    # Find the 一句话概括 callout from 论文信息 frame
    one_line_summary = ''
    highlights_items = []
    links = {}

    for f in frames:
        if f['title'] == '论文信息':
            one_line_summary = f.get('callout', '')
        if '研究背景' in f.get('title', '') or '在做什么' in f.get('title', ''):
            highlights_items = f.get('items', [])[:5]

    # Extract links from preamble
    if preamble.get('source_url'):
        links['论文链接'] = preamble['source_url']
    if preamble.get('code_url'):
        links['代码'] = preamble['code_url']
    if preamble.get('project_url'):
        links['项目网站'] = preamble['project_url']

    # Build description
    desc_lines = []
    desc_lines.append(f"【论文分享】{title_en} ({venue} {year}) — {one_line_summary}" if one_line_summary
                      else f"【论文分享】{title_en} ({venue} {year})")

    if highlights_items:
        desc_lines.append('')
        for item in highlights_items[:5]:
            desc_lines.append(f"- {item}")

    if links:
        desc_lines.append('')
        for label, url in links.items():
            desc_lines.append(f"{label}：{url}")

    desc_lines.append('')
    desc_lines.append('本视频由 AI 自动生成，仅供学术交流使用。')
    desc = '\n'.join(desc_lines)

    # Dynamic feed text
    short_for_dynamic = preamble.get('short_title', title_en)
    if len(short_for_dynamic) > 50:
        short_for_dynamic = short_for_dynamic[:47] + '...'
    summary_short = one_line_summary[:100] if one_line_summary else ''
    dynamic = f"新一期论文分享：{short_for_dynamic} ({venue} {year}) — {summary_short}"
    if len(dynamic) > 256:
        dynamic = dynamic[:253] + '...'

    meta_title = format_bilibili_title(venue, year, title)

    meta = {
        'title': meta_title,
        'title_en': title_en,
        'tid_name': tid_name,
        'tag': tags,
        'desc': desc,
        'copyright': 1,
        'source': '',
        'dynamic': dynamic,
        'no_reprint': 0,
        'cover_path': cover_path,
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    return os.path.abspath(output_path)


# ─── TTS ───────────────────────────────────────────────────────────────────
# IndexTTS2 is the only supported narration backend.


def tts_slide(text: str, output_path: str, lang: str = 'zh',
              backend: str | None = None, config_path: str | None = None) -> bool:
    """Convert one narration to speech with the configured backend."""
    from tts_backends import resolve_backend, run_local_tts_batch

    selected = resolve_backend(backend, config_path)
    result = run_local_tts_batch(
        selected,
        [{'name': Path(output_path).stem, 'text': text, 'output': output_path}],
        config_path=config_path,
    )
    statuses = {item['status'] for item in result.get('tasks', [])}
    return bool(statuses & {'generated', 'cached'})


def batch_tts_parallel(frame_dir: str, lang: str = 'zh', max_workers: int = 8,
                       backend: str | None = None,
                       config_path: str | None = None,
                       return_summary: bool = False) -> int | dict:
    """Run all slide_NNN.txt files through one local IndexTTS2 batch worker.

    Args:
        frame_dir: Directory containing slide_NNN.txt files.
        lang: Voice language ('zh' or 'en').
        max_workers: Retained for call compatibility; IndexTTS2 inference is serial.

    Returns:
        Number of slides processed.
    """
    from tts_backends import resolve_backend, run_local_tts_batch

    started = time.perf_counter()
    selected = resolve_backend(backend, config_path)
    tasks = []
    for fname in sorted(os.listdir(frame_dir)):
        if not re.fullmatch(r'slide_\d+\.txt', fname):
            continue
        basename = fname[:-4]
        txt_path = os.path.join(frame_dir, fname)
        mp3_path = os.path.join(frame_dir, f'{basename}.mp3')
        with open(txt_path, 'r', encoding='utf-8') as f:
            text = f.read()
        if text.strip():
            tasks.append((basename, text, mp3_path))

    if not tasks:
        summary = {
            'backend': selected, 'requested': 0, 'completed': 0,
            'generated': 0, 'cached': 0, 'failed': 0,
            'elapsed_seconds': round(time.perf_counter() - started, 3),
        }
        print('  TTS: all MP3s already present, skipping')
        return summary if return_summary else 0

    print(f'  TTS: {len(tasks)} slides, local IndexTTS2 batch...')
    result = run_local_tts_batch(
        selected,
        [
            {'name': name, 'text': text, 'output': mp3}
            for name, text, mp3 in tasks
        ],
        config_path=config_path,
    )
    completed = sum(
        item.get('status') in {'generated', 'cached'}
        for item in result.get('tasks', [])
    )
    statuses = [item.get('status') for item in result.get('tasks', [])]
    summary = {
        'backend': selected,
        'device': result.get('device'),
        'requested': len(tasks),
        'completed': completed,
        'generated': statuses.count('generated'),
        'cached': statuses.count('cached'),
        'failed': statuses.count('failed'),
        'preflight': result.get('preflight'),
        'preflight_report': result.get('preflight_report'),
        'elapsed_seconds': round(time.perf_counter() - started, 3),
    }
    print('  TTS summary: ' + json.dumps(summary, ensure_ascii=False, separators=(',', ':')))
    return summary if return_summary else completed


# ─── Video assembly ────────────────────────────────────────────────────────

def _sha256_path(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _video_segment_cache_key(png_path, mp3_path, vf_filter, pad_sec):
    payload = {
        'pipeline_version': 1,
        'png_sha256': _sha256_path(png_path),
        'mp3_sha256': _sha256_path(mp3_path) if os.path.exists(mp3_path) else None,
        'vf_filter': vf_filter,
        'pad_sec': float(pad_sec),
        'video_codec': 'libx264',
        'preset': 'medium',
        'crf': 23,
        'pixel_format': 'yuv420p',
        'audio_codec': 'aac',
        'audio_bitrate': '128k',
        'audio_sample_rate': 44100,
        'target_lufs': -16,
        'target_true_peak_db': -4.0,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _encode_one_slide(png_path, frame_dir, vf_filter, pad_sec, ffmpeg_semaphore=None):
    """Encode one slide: ffmpeg still-image + audio. Called in parallel.
    Assumes .mp3 already exists (TTS done beforehand)."""
    import subprocess as _sp
    basename = os.path.splitext(os.path.basename(png_path))[0]
    mp3_path = os.path.join(frame_dir, f'{basename}.mp3')
    final_mp4 = os.path.join(frame_dir, f'{basename}_final.mp4')
    cache_path = os.path.join(frame_dir, f'{basename}.video-cache.json')
    txt_path = os.path.join(frame_dir, f'{basename}.txt')


    has_audio = os.path.exists(mp3_path)
    cache_key = _video_segment_cache_key(png_path, mp3_path, vf_filter, pad_sec)
    if os.path.exists(final_mp4) and os.path.getsize(final_mp4) > 1000 and os.path.exists(cache_path):
        try:
            cache = json.loads(Path(cache_path).read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            cache = {}
        if cache.get('key') == cache_key:
            print(f'  {basename} (cached segment)')
            return {'path': final_mp4, 'status': 'cached'}
    if has_audio:
        probe_cmd = [
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', mp3_path,
        ]
        probe_result = _sp.run(probe_cmd, capture_output=True, text=True)
        try:
            audio_dur = float(probe_result.stdout.strip())
        except ValueError:
            audio_dur = 10.0
        total_dur = audio_dur + pad_sec
        cmd = [
            'ffmpeg', '-y', '-loglevel', 'error',
            '-loop', '1', '-i', png_path, '-i', mp3_path,
            '-c:v', 'libx264', '-tune', 'stillimage',
            '-preset', 'medium', '-crf', '23',
            '-pix_fmt', 'yuv420p', '-t', str(total_dur),
            '-vf', vf_filter,
            '-af', (
                'aformat=sample_rates=44100:channel_layouts=stereo,'
                f'loudnorm=I=-16:TP=-4.0:LRA=11,apad=whole_dur={total_dur}'
            ),
            '-ar', '44100', '-c:a', 'aac', '-b:a', '128k', final_mp4,
        ]
    else:
        total_dur = 2.0 + pad_sec
        cmd = [
            'ffmpeg', '-y', '-loglevel', 'error',
            '-loop', '1', '-i', png_path,
            '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=stereo',
            '-c:v', 'libx264', '-tune', 'stillimage',
            '-preset', 'medium', '-crf', '23',
            '-pix_fmt', 'yuv420p', '-t', str(total_dur),
            '-vf', vf_filter, final_mp4,
        ]

    kind = "audio" if has_audio else "silent"
    print(f'  {basename} ({kind}, {total_dur:.1f}s)...')
    guard = ffmpeg_semaphore if ffmpeg_semaphore is not None else contextlib.nullcontext()
    with guard:
        result = _sp.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f'  [WARN] ffmpeg failed for {basename}: {result.stderr[-100:]}')
        return None
    Path(cache_path).write_text(
        json.dumps({'key': cache_key, 'pipeline_version': 1}, indent=2),
        encoding='utf-8',
    )
    return {'path': final_mp4, 'status': 'encoded'}


def assemble_video(frame_dir: str, output_path: str, fps: int = 30,
                   pad_sec: float = 0.5, speed: float = DEFAULT_PLAYBACK_SPEED,
                   max_workers: int = None, require_audio: bool = True,
                   tts_backend: str | None = None,
                   tts_config: str | None = None,
                   run_tts: bool = True, segment_executor=None,
                   ffmpeg_semaphore=None) -> dict:
    """Assemble slide PNGs and MP3 audio into a narrated MP4 video.

    Parallel ffmpeg encode per slide via ThreadPoolExecutor.
    TTS must already be done (MP3 files present). Optional speedup via setpts + atempo.

    Args:
        frame_dir: Directory containing slide_NNN.png, .txt, .mp3.
        output_path: Output MP4 path.
        pad_sec: Freeze-frame extension per slide (default 0.5).
        speed: Pitch-preserving playback multiplier (default 1.25).
        max_workers: Parallel ffmpeg workers when no shared executor is supplied.
        require_audio: Fail when any rendered slide lacks a nonempty MP3.
        segment_executor: Optional batch-scoped executor shared by all papers.
        ffmpeg_semaphore: Optional batch-scoped limit for all ffmpeg subprocesses.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import glob as glob_mod
    from PIL import Image

    if max_workers is None:
        max_workers = min(8, (os.cpu_count() or 4))

    png_files = sorted(glob_mod.glob(os.path.join(frame_dir, 'slide_*.png')))
    if not png_files:
        raise FileNotFoundError(f'No slide PNGs found in {frame_dir}')

    first_img = Image.open(png_files[0])
    print(f'Source slide dimensions: {first_img.size[0]}x{first_img.size[1]}')

    vf_filter = (
        'scale=1920:1200:force_original_aspect_ratio=decrease,'
        'pad=1920:1200:(ow-iw)/2:(oh-ih)/2:black'
    )
    # The standalone batch orchestrator performs TTS once and passes
    # run_tts=False. Keep the default for direct callers and the full pipeline.
    if run_tts:
        batch_tts_parallel(
            frame_dir, backend=tts_backend, config_path=tts_config,
        )

    if require_audio:
        missing_audio = []
        for png_path in png_files:
            mp3_path = os.path.splitext(png_path)[0] + '.mp3'
            if not os.path.exists(mp3_path) or os.path.getsize(mp3_path) == 0:
                missing_audio.append(os.path.basename(png_path))
        if missing_audio:
            preview = ', '.join(missing_audio[:8])
            raise RuntimeError(f'Missing audio for {len(missing_audio)} slide(s): {preview}')

    # --- Parallel encode each slide ---
    worker_label = 'shared pool' if segment_executor is not None else f'{max_workers} workers'
    print(f'  Parallel encoding {len(png_files)} slides ({worker_label})...')
    results = []
    def collect(executor):
        futures = {
            executor.submit(
                _encode_one_slide, p, frame_dir, vf_filter, pad_sec, ffmpeg_semaphore,
            ): p
            for p in png_files
        }
        for future in as_completed(futures):
            r = future.result()
            if r:
                results.append(r)
    if segment_executor is not None:
        collect(segment_executor)
    elif max_workers == 1:
        for path in png_files:
            result = _encode_one_slide(
                path, frame_dir, vf_filter, pad_sec, ffmpeg_semaphore,
            )
            if result:
                results.append(result)
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            collect(executor)

    if len(results) != len(png_files):
        raise RuntimeError(
            f'Video segment coverage mismatch: {len(results)}/{len(png_files)} encoded'
        )

    results.sort(key=lambda item: os.path.basename(item['path']))
    encoded_count = sum(item['status'] == 'encoded' for item in results)
    cached_count = sum(item['status'] == 'cached' for item in results)

    # Concat
    concat_list_path = os.path.join(frame_dir, 'filelist.txt')
    with open(concat_list_path, 'w') as f:
        for item in results:
            f.write(f"file '{os.path.abspath(item['path'])}'\n")

    concat_output = output_path.replace('.mp4', '_concat.mp4')

    print(f'  Concatenating {len(results)} segments...')
    concat_cmd = [
        'ffmpeg', '-y', '-loglevel', 'error',
        '-f', 'concat', '-safe', '0',
        '-i', os.path.abspath(concat_list_path),
        '-c', 'copy', os.path.abspath(concat_output),
    ]
    guard = ffmpeg_semaphore if ffmpeg_semaphore is not None else contextlib.nullcontext()
    with guard:
        result = subprocess.run(concat_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f'ffmpeg concat failed: {result.stderr}')

    if speed <= 0:
        raise ValueError(f'speed must be positive, got {speed}')

    # Apply the fixed presentation cadence after native-speed TTS.  Keep this
    # separate from model inference so every backend receives the same
    # pitch-preserving FFmpeg treatment.
    continuous_input = concat_output
    speed_output = None
    if speed != 1.0:
        print(f'  Applying {speed}x speedup...')
        speed_output = output_path.replace('.mp4', '_speed.mp4')
        speed_cmd = [
            'ffmpeg', '-y', '-loglevel', 'error',
            '-i', os.path.abspath(concat_output),
            '-vf', f'setpts=PTS/{speed}',
            '-af', f'atempo={speed}',
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
            '-c:a', 'aac', '-b:a', '128k',
            os.path.abspath(speed_output),
        ]
        guard = ffmpeg_semaphore if ffmpeg_semaphore is not None else contextlib.nullcontext()
        with guard:
            result = subprocess.run(speed_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f'ffmpeg speedup failed: {result.stderr}')
        continuous_input = speed_output

    # Concatenating independently encoded AAC segments can create decoder
    # boundary peaks even when every segment passes its own true-peak gate.
    # Always normalize and limit the complete final-speed timeline.
    normalized_output = output_path.replace('.mp4', '_normalized.mp4')
    normalize_cmd = [
        'ffmpeg', '-y', '-loglevel', 'error',
        '-i', os.path.abspath(continuous_input),
        '-c:v', 'copy',
        '-af', 'loudnorm=I=-15.2:TP=-1.5:LRA=11',
        '-ar', '44100', '-c:a', 'aac', '-b:a', '128k',
        os.path.abspath(normalized_output),
    ]
    guard = ffmpeg_semaphore if ffmpeg_semaphore is not None else contextlib.nullcontext()
    with guard:
        result = subprocess.run(normalize_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f'ffmpeg final audio normalization failed: {result.stderr}')
    limited_output = output_path.replace('.mp4', '_limited.mp4')
    limiter_cmd = [
        'ffmpeg', '-y', '-loglevel', 'error',
        '-i', os.path.abspath(normalized_output),
        '-c:v', 'copy',
        '-af', 'alimiter=limit=0.5:attack=5:release=50:level=false',
        '-ar', '44100', '-c:a', 'aac', '-b:a', '128k',
        os.path.abspath(limited_output),
    ]
    guard = ffmpeg_semaphore if ffmpeg_semaphore is not None else contextlib.nullcontext()
    with guard:
        result = subprocess.run(limiter_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f'ffmpeg final true-peak limiting failed: {result.stderr}')
    safety_cmd = [
        'ffmpeg', '-y', '-loglevel', 'error',
        '-i', os.path.abspath(limited_output),
        '-c:v', 'copy',
        '-af', 'alimiter=limit=0.5:attack=5:release=50:level=false',
        '-ar', '44100', '-c:a', 'aac', '-b:a', '128k',
        os.path.abspath(output_path),
    ]
    guard = ffmpeg_semaphore if ffmpeg_semaphore is not None else contextlib.nullcontext()
    with guard:
        result = subprocess.run(safety_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f'ffmpeg final safety limiting failed: {result.stderr}')
    for temporary_output in (
        concat_output, speed_output, normalized_output, limited_output,
    ):
        if temporary_output and os.path.exists(temporary_output):
            os.unlink(temporary_output)

    import json as _json
    probe_cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                 '-of', 'json', os.path.abspath(output_path)]
    probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
    try:
        dur = float(_json.loads(probe_result.stdout)['format']['duration'])
        print(f'Video assembled: {os.path.abspath(output_path)} ({dur:.1f}s)')
    except Exception:
        dur = None
        print(f'Video assembled: {os.path.abspath(output_path)}')
    return {
        'output': os.path.abspath(output_path),
        'segments': len(results),
        'encoded': encoded_count,
        'cached': cached_count,
        'duration_seconds': dur,
        'speed': float(speed),
    }

# ─── Main (full pipeline) ──────────────────────────────────────────────────

def run_full_pipeline(paper_dir: str) -> dict:
    """Run the full slides-to-video pipeline.

    Args:
        paper_dir: Paper directory containing slides-beamer/ (with main.tex, main.pdf).
                   Example: '论文分享/RSS 2026 - LDA-1B/'

    All video outputs go into <paper_dir>/video/.

    Returns:
        Dict with output paths and stats.
    """
    paper_dir = os.path.abspath(paper_dir)
    tex_path = os.path.join(paper_dir, 'slides-beamer', 'main.tex')
    pdf_path = os.path.join(paper_dir, 'slides-beamer', 'main.pdf')
    video_dir = os.path.join(paper_dir, 'video')
    frame_dir = os.path.join(video_dir, 'video_frames')
    cover_path = os.path.join(video_dir, 'cover.png')
    meta_path = os.path.join(video_dir, 'video_meta.json')

    paper_name = os.path.basename(paper_dir.rstrip('/\\'))
    paper_name = paper_name.split(' - ')[-1] if ' - ' in paper_name else paper_name
    video_path = os.path.join(video_dir, f'{paper_name}_narrated.mp4')

    os.makedirs(video_dir, exist_ok=True)
    os.makedirs(frame_dir, exist_ok=True)

    print(f'=== Pipeline: {paper_name} ===')
    print(f'Paper dir:  {paper_dir}')
    print(f'Video dir:  {video_dir}')

    # 1. Parse preamble and frames
    print('\n[1/6] Parsing LaTeX...')
    preamble = parse_beamer_preamble(tex_path)
    frames = parse_beamer_frames(tex_path)
    print(f'  Preamble: {preamble["title"][:60]}...')
    print(f'  Frames: {len(frames)}')

    # 2. Render slides
    print('\n[2/6] Rendering slides...')
    slide_paths = render_slides(pdf_path, frame_dir, dpi=200)
    print(f'  Rendered {len(slide_paths)} slides')

    # 3. Generate cover
    print('\n[3/6] Generating cover...')
    cover = generate_cover(slide_paths[0], cover_path)
    print(f'  Cover: {cover}')

    # 4. Generate metadata
    print('\n[4/6] Generating metadata...')
    meta = generate_metadata(preamble, frames, 'cover.png', meta_path)
    print(f'  Metadata: {meta}')

    # 5. Narration and TTS — one local IndexTTS2 batch inside assemble_video
    print('\n[5/6] TTS + Video: local G2PW + IndexTTS2...')

    # 6. Assemble at the fixed presentation cadence while preserving pitch.
    print(f'\n[6/6] Assembling video (parallel, {DEFAULT_PLAYBACK_SPEED}x)...')
    assemble_video(
        frame_dir, video_path, pad_sec=0.5, speed=DEFAULT_PLAYBACK_SPEED,
    )

    return {
        'paper_name': paper_name,
        'paper_dir': paper_dir,
        'video_dir': video_dir,
        'video': video_path,
        'cover': cover_path,
        'metadata': meta_path,
        'frames': frame_dir,
        'num_slides': len(slide_paths),
    }


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python slides_to_video.py <paper_dir>')
        print('  <paper_dir> must contain slides-beamer/main.tex and slides-beamer/main.pdf')
        print('  Example: python slides_to_video.py "论文分享/RSS 2026 - LDA-1B"')
        sys.exit(1)

    paper_dir = sys.argv[1]
    result = run_full_pipeline(paper_dir)
    print(f'\nDone! Output: {result["video"]}')
