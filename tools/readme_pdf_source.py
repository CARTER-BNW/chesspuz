"""README.md -> build/README-<version>.md, the markdown make-pdf turns into the README PDF.

    python tools\\readme_pdf_source.py 0.4.2 "30 September 2026"

Rules (docs/STATUS.md, "How to ship a release"): a "Version X.Y.Z, date. Downloads: ..." line
under the H1, relative links made absolute to github.com/CARTER-BNW/chesspuz/blob/main/...,
every bare URL as an explicit [text](url) link (make-pdf's typography pass breaks on bare ones),
the HTML <img> blocks turned into ![..](..){width=..} images, the "Created ... template" line
replaced by a source link plus a "More screenshots" section; the screenshots are copied to
build/docs/screenshots so the relative image paths resolve from build/.
"""

import re
import shutil
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
version = sys.argv[1]
date = sys.argv[2]
text = root.joinpath("README.md").read_text(encoding="utf-8")
repo = "https://github.com/CARTER-BNW/chesspuz"
lines = text.splitlines()
out = []
i = 0
while i < len(lines):
    line = lines[i]
    if i == 0 and line.startswith("# "):
        out += [
            line,
            "",
            f"Version {version}, {date}. Downloads: "
            f"[github.com/CARTER-BNW/chesspuz/releases]({repo}/releases)",
        ]
        i += 1
        continue
    if line.startswith('<p align="center"><img src="docs/screenshots/desktop-run.png"'):
        out.append("![A Survival run on the desktop](docs/screenshots/desktop-run.png){width=full}")
        i += 1
        continue
    if line == '<p align="center">':  # the phone trio -> one phone image
        while lines[i] != "</p>":
            i += 1
        out.append("![A run on the phone](docs/screenshots/phone-run.png){width=45%}")
        i += 1
        continue
    if line.startswith("Created 2026-09-22 from the"):
        out += [
            "Created 2026-09-22. Source code and releases: "
            f"[github.com/CARTER-BNW/chesspuz]({repo})",
            "",
            "## More screenshots",
            "",
            "![Reviewing a run](docs/screenshots/desktop-review.png){width=full}",
            "",
            "![Leaderboard](docs/screenshots/desktop-leaderboard.png){width=full}",
            "",
            "![Stats](docs/screenshots/desktop-stats.png){width=full}",
        ]
        i += 1
        continue
    # relative links -> absolute on github
    line = re.sub(
        r"\]\((?!https?://)([^)]+)\)", lambda m: f"]({repo}/blob/main/{m.group(1)})", line
    )
    # bare URLs -> explicit links
    line = re.sub(
        r"(?<![(\[`])https?://([^\s,)]+)", lambda m: f"[{m.group(1)}]({m.group(0)})", line
    )
    out.append(line)
    i += 1
target = root / "build" / f"README-{version}.md"
target.parent.mkdir(exist_ok=True)
target.write_text("\n".join(out) + "\n", encoding="utf-8")
shots = root / "build" / "docs" / "screenshots"
shots.mkdir(parents=True, exist_ok=True)
for png in (root / "docs" / "screenshots").glob("*.png"):
    shutil.copy(png, shots / png.name)
print("wrote", target, "and", len(list(shots.glob("*.png"))), "screenshots")
