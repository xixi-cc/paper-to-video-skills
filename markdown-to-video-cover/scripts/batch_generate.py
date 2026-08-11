#!/usr/bin/env python3
"""Batch run generate_poster.py for a slice of paper directories."""
import sys, os, subprocess

PYTHON = sys.executable
GENERATOR = os.path.join(os.path.dirname(__file__), "generate_poster.py")

def main():
    papers_file = sys.argv[1]
    start = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    count = int(sys.argv[3]) if len(sys.argv) > 3 else None

    with open(papers_file, "r", encoding="utf-8") as f:
        papers = [l.strip() for l in f if l.strip()]

    batch = papers[start:start + count] if count else papers[start:]
    total = len(batch)
    success = 0
    failures = []

    for i, paper_dir in enumerate(batch):
        name = os.path.basename(paper_dir)
        print(f"[{i+1}/{total}] {name[:60]} ...", flush=True)
        result = subprocess.run(
            [PYTHON, GENERATOR, paper_dir, "--no-png"],
            capture_output=True, text=True,
            timeout=120,
        )
        poster_pdf = os.path.join(paper_dir, "poster", "poster.pdf")
        if result.returncode == 0 and os.path.exists(poster_pdf):
            size_kb = os.path.getsize(poster_pdf) // 1024
            print(f"  OK ({size_kb}KB)", flush=True)
            success += 1
        else:
            last_lines = (result.stderr or result.stdout or "").split("\n")[-3:]
            reason = last_lines[0][:100] if last_lines else "unknown"
            print(f"  FAIL: {reason}", flush=True)
            failures.append((paper_dir, reason))

    print(f"\n=== Done: {success}/{total} succeeded ===")
    if failures:
        print(f"=== {len(failures)} failures ===")
        for d, r in failures:
            print(f"  FAIL {os.path.basename(d)}: {r}")

if __name__ == "__main__":
    main()
