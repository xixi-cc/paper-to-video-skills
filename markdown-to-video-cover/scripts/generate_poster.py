#!/usr/bin/env python3
"""
generate_poster.py — CLI: paper_dir with md_output → promotional poster (tex, pdf, png).

Usage:
  python generate_poster.py <paper_dir> [--data data.json] [--title-font N] [--no-png]

Auto-extracts title, venue, figures, and key metrics from MinerU markdown.
Gemini beamerposter theme, 16:10, 2 columns, result-card style.
"""
import sys, os, re, json, glob as _glob, subprocess, argparse, shutil

# ═══════════════════════════════════════════════════════════════
# Paths
# ═══════════════════════════════════════════════════════════════

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
TEMPLATES_DIR = os.path.join(SKILL_DIR, "templates")
LUALATEX = os.environ.get("LUALATEX") or shutil.which("lualatex")

# ═══════════════════════════════════════════════════════════════
# Markdown parser
# ═══════════════════════════════════════════════════════════════

def find_md_file(paper_dir):
    """Find the MinerU markdown file in md_output/*/auto/."""
    pattern = os.path.join(paper_dir, "md_output", "*", "auto", "*.md")
    matches = _glob.glob(pattern)
    if not matches:
        matches = _glob.glob(os.path.join(paper_dir, "md_output", "**", "*.md"), recursive=True)
    if not matches:
        raise FileNotFoundError(f"No .md found in md_output/*/auto/ under {paper_dir}")
    return matches[0]


def read_md(path):
    """Read markdown file, stripping NUL bytes and handling encoding issues."""
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    return content.replace("\0", "")


def extract_title(md_text):
    """Extract title from first # heading."""
    for line in md_text.split("\n"):
        line = line.strip()
        if line.startswith("# ") and not line.startswith("## "):
            # Strip HTML tags
            title = re.sub(r"<[^>]+>", "", line[2:]).strip()
            return title
    return "Unknown Title"


def extract_venue(paper_dir):
    """Infer venue from directory name."""
    basename = os.path.basename(os.path.normpath(paper_dir))
    # e.g., "CVPR 2025 - GROVE" → "CVPR 2025"
    match = re.match(r"([A-Z]+)\s*(\d{4})", basename)
    if match:
        return f"{match.group(1)} {match.group(2)}"
    return basename


def extract_project_url(md_text):
    """Extract first HTTP URL from the markdown header (first 20 lines)."""
    for line in md_text.split("\n")[:20]:
        match = re.search(r"https?://[^\s)\]]+", line)
        if match:
            return match.group(0).rstrip(".")
    return ""


def extract_figures(md_text, images_dir):
    """
    Find Figure N captions and map to image files.
    Returns list of (figure_number, image_filename, caption_text, file_path).
    """
    # Find all image references with their context
    # Pattern: ![](images/HASH.jpg) followed by or near "Fig. N" / "Figure N"
    figures = []
    lines = md_text.split("\n")

    for i, line in enumerate(lines):
        # Match image reference
        img_match = re.search(r"!\[\]\(images/([^)]+)\)", line)
        if img_match:
            img_file = img_match.group(1)
            img_path = os.path.join(images_dir, img_file)
            if not os.path.exists(img_path):
                continue

            # Look for Figure N in this line or next 3 lines
            fig_num = None
            caption = ""
            for j in range(i, min(i + 4, len(lines))):
                cap_match = re.search(r"(?:Fig(?:ure)?)\.?\s*(\d+)", lines[j], re.IGNORECASE)
                if cap_match:
                    fig_num = int(cap_match.group(1))
                    caption = lines[j].strip()
                    break

            if fig_num:
                figures.append((fig_num, img_file, caption, img_path))

    # Sort by figure number, deduplicate
    seen = set()
    result = []
    for f in sorted(figures, key=lambda x: x[0]):
        if f[0] not in seen:
            seen.add(f[0])
            result.append(f)
    return result


def extract_key_metrics(md_text):
    """
    Extract key quantitative results from the abstract and experiments.
    Returns list of metric lines for result cards.
    """
    # Focus on abstract and experiments sections
    sections = md_text.split("\n## ")
    relevant = []
    for sec in sections:
        if any(kw in sec.lower() for kw in ["abstract", "experiment", "result", "evaluation"]):
            relevant.append(sec)

    text = "\n".join(relevant[:3])  # abstract + first 2 experiment sections

    metrics = []

    # Find percentage improvements with context
    pct_patterns = re.findall(
        r"(\d+\.?\d*)\s*%\s*(higher|better|improvement|more|faster|increase|completion|boost)",
        text, re.IGNORECASE
    )
    for val, ctx in pct_patterns[:3]:
        pct = float(val)
        if pct > 1:
            metrics.append(f"+{val}\\% {ctx.lower()}")

    # Find multipliers
    mult_patterns = re.findall(
        r"(\d+\.?\d*)\s*[×x]\s*(faster|speedup|less|fewer|reduction)",
        text, re.IGNORECASE
    )
    for val, ctx in mult_patterns[:2]:
        metrics.append(f"{val}$\\times$ {ctx.lower()}")

    # Find standalone percentages in results context
    std_pcts = re.findall(
        r"(\d+\.?\d*)\s*%\s+(task\s+completion|success\s+rate|accuracy|naturalness)",
        text, re.IGNORECASE
    )
    for val, ctx in std_pcts[:3]:
        metrics.append(f"{val}\\% {ctx.lower()}")
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for m in metrics:
        normalized = re.sub(r"[+\\%$\s]+", "", m).lower()
        if normalized not in seen:
            seen.add(normalized)
            unique.append(m)
    return unique[:6]


# ═══════════════════════════════════════════════════════════════
# Poster data builder
# ═══════════════════════════════════════════════════════════════

def build_poster_data(paper_dir, json_data=None):
    """Build the poster data dict from auto-extraction + optional JSON override."""
    md_path = find_md_file(paper_dir)
    md_text = read_md(md_path)
    images_dir = os.path.join(os.path.dirname(md_path), "images")
    venue = extract_venue(paper_dir)

    data = {
        "title": extract_title(md_text),
        "venue": venue,
        "project_url": extract_project_url(md_text),
        "title_font": 260 if len(extract_title(md_text)) < 60 else 200,
        "figures": {"col1": [], "col2": []},
        "cards_col1": [],
        "cards_col2": [],
        "figure_map": {},
    }

    # Auto-figure extraction
    figures = extract_figures(md_text, images_dir)
    selected = figures[:6]  # max 6 figures

    # Distribute: odd figs to col1, even to col2
    for i, (fnum, img_file, caption, img_path) in enumerate(selected):
        fig_name = f"fig{fnum}"
        data["figure_map"][fig_name] = os.path.relpath(img_path, paper_dir)
        if i % 2 == 0:
            data["figures"]["col1"].append(fig_name)
        else:
            data["figures"]["col2"].append(fig_name)

    # Auto-metric extraction → cards
    metrics = extract_key_metrics(md_text)
    if metrics and len(data["figures"]["col1"]) > 0:
        mid = len(data["figures"]["col1"]) // 2
        first_fig = data["figures"]["col1"][0] if data["figures"]["col1"] else "fig1"

        data["cards_col1"].append({
            "title": "Key Metrics",
            "lines": [
                " \\textbullet{} ".join(metrics[:3]) if len(metrics) >= 3 else metrics[0] if metrics else "",
                " \\textbullet{} ".join(metrics[3:6]) if len(metrics) > 3 else "",
            ],
            "after": first_fig,
        })

    if len(data["figures"]["col2"]) > 0:
        data["cards_col2"].append({
            "title": "Venue",
            "lines": [venue, "See paper for full results"],
            "after": data["figures"]["col2"][0],
        })

    # JSON override
    if json_data:
        for key in ["title", "venue", "project_url", "title_font"]:
            if key in json_data:
                data[key] = json_data[key]
        if "figures" in json_data:
            data["figures"] = json_data["figures"]
        if "cards_col1" in json_data:
            data["cards_col1"] = json_data["cards_col1"]
        if "cards_col2" in json_data:
            data["cards_col2"] = json_data["cards_col2"]
        if "figure_map" in json_data:
            data["figure_map"] = json_data["figure_map"]

    return data


# ═══════════════════════════════════════════════════════════════
# LaTeX generator
# ═══════════════════════════════════════════════════════════════

PAPER_WIDTH_CM = 160
PAPER_HEIGHT_CM = 100
SCALE = 1.2
SEPWIDTH_FRAC = 0.027
COLWIDTH_FRAC = 0.46


def build_card(latex, t):
    latex.append(f"  \\begin{{block}}{{{t['title']}}}")
    latex.append("    \\centering")
    latex.append("    \\huge")
    for line in t["lines"]:
        if line.strip():
            latex.append(f"    {line} \\par")
    latex.append("  \\end{block}")
    latex.append("")


def build_column(latex, figures, cards):
    card_map = {c["after"]: c for c in cards}
    for fig in figures:
        latex.append(f"  \\posterfig{{figures/{fig}.jpg}}")
        latex.append("")
        if fig in card_map:
            build_card(latex, card_map[fig])


def generate_tex(poster_dir, data):
    """Generate poster.tex from data dict."""
    title_font = data.get("title_font", 240)
    venue = data.get("venue", "")
    project_url = data.get("project_url", "")

    lines = []
    lines.extend([
        r"\RequirePackage{luatex85}",
        r"\documentclass[final]{beamer}",
        "",
        r"% ── Packages ──",
        r"\usepackage[size=custom,"
        rf"width={PAPER_WIDTH_CM},height={PAPER_HEIGHT_CM},scale={SCALE}]{{beamerposter}}",
        r"\usetheme{gemini}",
        r"\usecolortheme{sustech}",
        rf"\setbeamerfont{{headline title}}{{size=\fontsize{{{title_font}}}{{{title_font + 40}}}\selectfont,series=\bfseries}}",
        r"\usepackage{graphicx}",
        r"\usepackage{booktabs}",
        r"\usepackage{qrcode}",
        r"\usepackage{hyperref}",
        r"\usepackage{amsmath}",
        "",
        r"% ── Column layout ──",
        r"\newlength{\sepwidth}",
        r"\newlength{\colwidth}",
        rf"\setlength{{\sepwidth}}{{{SEPWIDTH_FRAC}\paperwidth}}",
        rf"\setlength{{\colwidth}}{{{COLWIDTH_FRAC}\paperwidth}}",
        r"\newcommand{\separatorcolumn}{\begin{column}{\sepwidth}\end{column}}",
        "",
        r"% ── Figure macro ──",
        r"\newcommand{\posterfig}[1]{\includegraphics[width=\linewidth]{#1}}",
        "",
        rf"\title{{{data['title']}}}",
        r"\author{}",
        r"\institute{}",
        "",
        r"% ── Footer ──",
    ])

    # Footer
    footer_left = rf"\href{{{project_url}}}{{Project Page}}" if project_url else venue
    footer_center = venue
    if project_url:
        footer_right = rf"\href{{{project_url}}}{{Paper}}"
    else:
        footer_right = ""
    lines.append(rf"\footercontent{{{footer_left} \hfill {footer_center} \hfill {footer_right}}}")

    lines.extend([
        "",
        r"\begin{document}",
        r"\begin{frame}[t]",
        r"\begin{columns}[t]",
        r"\separatorcolumn",
        "",
        r"% ═══════════ COLUMN 1 ═══════════",
        r"\begin{column}{\colwidth}",
        "",
    ])

    build_column(lines, data["figures"].get("col1", []), data.get("cards_col1", []))

    lines.extend([
        r"\end{column}",
        r"\separatorcolumn",
        "",
        r"% ═══════════ COLUMN 2 ═══════════",
        r"\begin{column}{\colwidth}",
        "",
    ])

    build_column(lines, data["figures"].get("col2", []), data.get("cards_col2", []))

    # QR code
    if project_url:
        lines.extend([
            r"  \vspace{0.5cm}",
            r"  \begin{center}",
            rf"    \qrcode[height=2.5cm]{{{project_url}}}",
            r"  \end{center}",
        ])

    lines.extend([
        "",
        r"\end{column}",
        r"\separatorcolumn",
        r"\end{columns}",
        r"\end{frame}",
        r"\end{document}",
    ])

    tex = "\n".join(lines) + "\n"
    tex_path = os.path.join(poster_dir, "poster.tex")
    with open(tex_path, "w", encoding="utf-8") as f:
        f.write(tex)
    return tex_path


# ═══════════════════════════════════════════════════════════════
# Main pipeline
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Generate promotional poster from paper md_output")
    parser.add_argument("paper_dir", help="Path to paper directory with md_output/")
    parser.add_argument("--data", help="Optional JSON config for overrides", default=None)
    parser.add_argument("--title-font", type=int, help="Override title font size in pt", default=None)
    parser.add_argument("--no-png", action="store_true", help="Skip PNG render")
    args = parser.parse_args()

    paper_dir = os.path.abspath(args.paper_dir)
    poster_dir = os.path.join(paper_dir, "poster")
    figures_dir = os.path.join(poster_dir, "figures")

    print(f"[1/6] Parsing markdown from {paper_dir}...")
    json_data = None
    if args.data:
        with open(args.data, "r", encoding="utf-8") as f:
            json_data = json.load(f)

    data = build_poster_data(paper_dir, json_data)
    if args.title_font:
        data["title_font"] = args.title_font

    print(f"  Title: {data['title'][:80]}...")
    print(f"  Venue: {data['venue']}")
    print(f"  Figures: {len(data['figure_map'])} found")
    print(f"  Title font: {data['title_font']}pt")

    # Create directories
    print(f"\n[2/6] Setting up {poster_dir}...")
    os.makedirs(figures_dir, exist_ok=True)

    # Copy figures
    src_images_dir = os.path.join(os.path.dirname(find_md_file(paper_dir)), "images")
    for fig_name, rel_path in data["figure_map"].items():
        # rel_path is like "md_output/.../images/HASH.jpg" — resolve from paper_dir
        src = os.path.join(paper_dir, rel_path) if not os.path.isabs(rel_path) else rel_path
        dst = os.path.join(figures_dir, f"{fig_name}.jpg")
        if os.path.exists(src) and not os.path.exists(dst):
            shutil.copy2(src, dst)
            print(f"  Copied {fig_name}.jpg")
        elif not os.path.exists(src):
            print(f"  WARNING: source not found: {src}")

    # Copy templates
    print(f"\n[3/6] Copying LaTeX templates...")
    for sty in ["beamerthemegemini.sty", "beamercolorthemesustech.sty"]:
        src = os.path.join(TEMPLATES_DIR, sty)
        dst = os.path.join(poster_dir, sty)
        if os.path.exists(src):
            shutil.copy2(src, dst)
            print(f"  Copied {sty}")
        else:
            print(f"  WARNING: template not found: {src}")

    # Generate tex
    print(f"\n[4/6] Generating poster.tex...")
    tex_path = generate_tex(poster_dir, data)
    print(f"  Wrote {tex_path}")

    # Compile
    print(f"\n[5/6] Compiling with lualatex...")
    if not LUALATEX:
        raise SystemExit("lualatex not found on PATH; run the Codex LaTeX doctor first")
    for pass_num in [1, 2]:
        result = subprocess.run(
            [LUALATEX, "-interaction=nonstopmode", "poster.tex"],
            cwd=poster_dir,
            capture_output=True, text=True,
        )
        errors = [l for l in result.stdout.split("\n") + result.stderr.split("\n")
                  if "Error" in l and "Fatal" not in l]
        if errors:
            print(f"  Pass {pass_num}: {len(errors)} Error(s)")
            for e in errors[:3]:
                print(f"    {e.strip()[:120]}")
        else:
            print(f"  Pass {pass_num}: OK")

    pdf_path = os.path.join(poster_dir, "poster.pdf")
    if os.path.exists(pdf_path):
        size_kb = os.path.getsize(pdf_path) // 1024
        print(f"  Output: {pdf_path} ({size_kb}KB)")
    else:
        print("  ERROR: poster.pdf not generated")
        sys.exit(1)

    # Render PNG
    if not args.no_png:
        print(f"\n[6/6] Rendering PNG...")
        if not shutil.which("pdftoppm"):
            raise SystemExit("pdftoppm not found on PATH")
        result = subprocess.run(
            ["pdftoppm", "-png", "-r", "150", "-f", "1", "-l", "1",
             "poster.pdf", "poster"],
            cwd=poster_dir,
            capture_output=True, text=True,
        )
        png_path = os.path.join(poster_dir, "poster-1.png")
        if os.path.exists(png_path):
            target = os.path.join(poster_dir, "poster.png")
            if os.path.exists(target):
                os.remove(target)
            os.rename(png_path, target)
            print(f"  Output: {target}")
        else:
            print("  WARNING: PNG render failed")

    print(f"\nDone. Poster at {poster_dir}/")


if __name__ == "__main__":
    main()
