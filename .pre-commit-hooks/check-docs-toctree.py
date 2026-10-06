"""
Pre-commit hook that checks every top-level document under docs/ is
reachable from a ``.. toctree::`` directive in docs/index.rst.

Only checks files directly in docs/ (not subdirectories — those are
managed by their own index files or autosummary).

Files whose names start with ``_`` or ``sitevars`` are excluded
automatically (includes, static assets, templates, etc.).
"""

import re
import sys
from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
DOC_EXTENSIONS = {".rst", ".md"}
TOCTREE_RE = re.compile(r"^\.\.\s+toctree::", re.MULTILINE)
EXCLUDED_NAMES = {"index", "sitevars"}


def collect_toctree_entries(rst_file: Path) -> set[str]:
    """Return the set of document names referenced by toctree directives in *rst_file*."""
    text = rst_file.read_text(encoding="utf-8")
    entries: set[str] = set()

    for match in TOCTREE_RE.finditer(text):
        pos = match.end()
        in_options = True
        for line in text[pos:].splitlines():
            stripped = line.strip()
            if not stripped:
                if not in_options:
                    break
                continue
            if not line[0].isspace():
                break
            if stripped.startswith(":"):
                continue
            in_options = False
            # Strip leading path components — we only care about the basename
            # for top-level matching.
            entries.add(stripped)

    return entries


def main() -> int:
    # Collect top-level document files in docs/ (not in subdirectories).
    top_level_docs: dict[str, Path] = {}
    for path in DOCS_DIR.iterdir():
        if path.suffix not in DOC_EXTENSIONS:
            continue
        if path.name.startswith("_"):
            continue
        doc_name = path.stem
        if doc_name in EXCLUDED_NAMES:
            continue
        top_level_docs[doc_name] = path

    # Collect toctree references from docs/index.rst.
    index_rst = DOCS_DIR / "index.rst"
    if not index_rst.exists():
        print("docs/index.rst not found")
        return 1

    referenced: set[str] = set()
    for entry in collect_toctree_entries(index_rst):
        # toctree entries can be paths like "topics/installation" —
        # extract just the leaf name for top-level entries without a slash.
        if "/" not in entry:
            referenced.add(entry)

    missing = sorted(set(top_level_docs) - referenced)
    if missing:
        print("The following top-level documents are not included in any toctree:")
        for name in missing:
            print(f"  - docs/{top_level_docs[name].name}")
        print("\nAdd them to a toctree directive in docs/index.rst.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
