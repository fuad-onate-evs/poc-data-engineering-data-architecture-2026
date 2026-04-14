"""Gatekeeper: reject coding-agent attribution in tracked content, commits, and PRs.

Matches attribution *phrasing* (e.g. "Co-Authored-By: Claude", "generated with AI",
":robot: generated with") rather than bare filenames like `CLAUDE.md`, so legitimate
references to gitignored fallback filenames stay usable.

Usage:
    python scripts/hooks/check_no_ai_attribution.py --files <path>...
    python scripts/hooks/check_no_ai_attribution.py --commit-msg <path>
    python scripts/hooks/check_no_ai_attribution.py --text "<inline string>"
    python scripts/hooks/check_no_ai_attribution.py --stdin

Exits 0 on clean input, 1 when any violation matches.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Attribution phrasing patterns. Compiled case-insensitive.
# Each entry: (label, regex). Order matters only for readability of output.
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "co-authored-by trailer",
        re.compile(
            r"co-authored-by:\s*(claude|anthropic|chatgpt|openai|gpt[-\s]?\d|copilot|github\s+copilot|gemini|an?\s+ai|an?\s+llm)",
            re.IGNORECASE,
        ),
    ),
    (
        "generated-with phrasing",
        re.compile(
            r"\bgenerated\s+(with|by|using)\s+(claude|anthropic|chatgpt|openai|gpt[-\s]?\d|copilot|gemini|an?\s+ai|an?\s+llm|ai\b|llm\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "authored-by phrasing",
        re.compile(
            r"\b(authored|written|created|produced|made|built)\s+(by|with)\s+(claude|anthropic|chatgpt|openai|gpt[-\s]?\d|copilot|gemini|an?\s+ai|an?\s+llm)",
            re.IGNORECASE,
        ),
    ),
    (
        "assisted-by phrasing",
        re.compile(
            r"\b(claude|anthropic|chatgpt|openai|gpt[-\s]?\d|copilot|gemini|ai|llm)[-\s]?assisted\b",
            re.IGNORECASE,
        ),
    ),
    (
        "help-of phrasing",
        re.compile(
            r"\bwith\s+(the\s+)?help\s+of\s+(claude|anthropic|chatgpt|openai|gpt[-\s]?\d|copilot|gemini|an?\s+ai|an?\s+llm)",
            re.IGNORECASE,
        ),
    ),
    (
        "robot emoji marker",
        re.compile(r"\U0001f916\s*generated", re.IGNORECASE),
    ),
    (
        "claude.ai signature URL",
        re.compile(r"https?://(www\.)?(claude\.ai|anthropic\.com/claude-code)", re.IGNORECASE),
    ),
    (
        "vendor promo tagline",
        re.compile(
            r"(powered|built)\s+with\s+(claude\s+code|claude|anthropic|openai|chatgpt|copilot)",
            re.IGNORECASE,
        ),
    ),
]

# Paths to skip — the gatekeeper itself contains the patterns literally, and
# dependency lockfiles can contain vendor strings beyond our control.
SELF_RELATIVE = "scripts/hooks/check_no_ai_attribution.py"
ALLOWLIST_SUFFIXES = (".lock",)
ALLOWLIST_CONTAINS = (
    SELF_RELATIVE,
    "uv.lock",
    "/.git/",
)


def _is_allowlisted(path: Path) -> bool:
    sp = str(path).replace("\\", "/")
    if any(tok in sp for tok in ALLOWLIST_CONTAINS):
        return True
    return path.suffix in ALLOWLIST_SUFFIXES


def scan_text(text: str, *, source: str) -> list[str]:
    """Return a list of human-readable violation messages."""
    violations: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for label, pat in PATTERNS:
            m = pat.search(line)
            if m:
                snippet = line.strip()
                if len(snippet) > 140:
                    snippet = snippet[:137] + "..."
                violations.append(
                    f"{source}:{lineno}: [{label}] matched {m.group(0)!r} in: {snippet}"
                )
    return violations


def scan_file(path: Path) -> list[str]:
    if _is_allowlisted(path):
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return [f"{path}: could not read ({e})"]
    return scan_text(text, source=str(path))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument(
        "--files", nargs="*", help="Files to scan (e.g. pre-commit passes staged paths)."
    )
    group.add_argument(
        "--commit-msg", help="Path to a commit message file (e.g. .git/COMMIT_EDITMSG)."
    )
    group.add_argument("--text", help="Inline text to scan (e.g. PR title or body).")
    group.add_argument("--stdin", action="store_true", help="Read text from stdin.")
    # Allow bare positional args for pre-commit (which passes staged file list positionally).
    parser.add_argument("positional", nargs="*", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    violations: list[str] = []

    if args.commit_msg:
        path = Path(args.commit_msg)
        if path.exists():
            violations.extend(scan_file(path))
    elif args.text is not None:
        violations.extend(scan_text(args.text, source="<text>"))
    elif args.stdin:
        data = sys.stdin.read()
        violations.extend(scan_text(data, source="<stdin>"))
    else:
        files = list(args.files or []) + list(args.positional or [])
        if not files:
            parser.print_help(sys.stderr)
            return 2
        for f in files:
            p = Path(f)
            if p.is_file():
                violations.extend(scan_file(p))

    if violations:
        print(
            "AI-attribution gatekeeper: violations found — please remove coding-agent "
            "attribution from commits, PRs, and tracked content.",
            file=sys.stderr,
        )
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        print(
            "\nIf a match is a false positive, refine the phrasing rather than "
            "allowlisting. Legitimate filenames like CLAUDE.md are not matched by "
            "design.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
