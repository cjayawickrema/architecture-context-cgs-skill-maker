#!/usr/bin/env python3
"""Standards Knowledge Base & Precedence Query Engine.

Scans the peer standards repositories (cyber-sec-standards, cloud-gov-standards,
enterprise-arch-standards), extracts normative guardrails, and returns them
ordered by strict enterprise precedence (CSS > CGS > EAS).

Usage:
  python3 standards_kb.py --query "database persistence terraform"
  python3 standards_kb.py --all --json
"""
import argparse
import json
import os
import re
import subprocess
import sys


def find_workspace_root():
    """Locate the root directory containing the standards repositories."""
    current = os.path.dirname(os.path.abspath(__file__))
    # Walk upwards looking for peer directories
    while current and current != os.path.dirname(current):
        if (os.path.isdir(os.path.join(current, "cyber-sec-standards")) or
            os.path.isdir(os.path.join(current, "cloud-gov-standards")) or
            os.path.isdir(os.path.join(current, "enterprise-arch-standards"))):
            return current
        current = os.path.dirname(current)
    # Default fallback
    return os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../.."))


WORKSPACE_ROOT = find_workspace_root()

REPOS_PRECEDENCE = [
    {
        "id": "CSS",
        "name": "cyber-sec-standards",
        "rank": 1,
        "description": "Cyber Security & Information Assurance Standards (Highest Precedence)",
    },
    {
        "id": "CGS",
        "name": "cloud-gov-standards",
        "rank": 2,
        "description": "Cloud Governance & Infrastructure Topologies",
    },
    {
        "id": "EAS",
        "name": "enterprise-arch-standards",
        "rank": 3,
        "description": "Enterprise Architecture & Technology Selection Standards",
    },
]

NORMATIVE_HEADINGS = [
    "normative guardrails",
    "core principles",
    "declarative",
    "decision matrix",
    "architectural baseline",
    "resource & topology matrix",
    "finops & sizing boundaries",
    "mandatory metadata",
    "prohibited topologies",
]

STANDARD_FILE_RE = re.compile(r"^[A-Za-z]+_\d+.*\.md$")


def git(repo, *args):
    res = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    return res


def get_commit_sha(repo_path):
    if not os.path.isdir(os.path.join(repo_path, ".git")):
        return "uncommitted"
    res = git(repo_path, "rev-parse", "HEAD")
    return res.stdout.strip() if res.returncode == 0 else "uncommitted"


def is_standard_file(filename):
    return bool(STANDARD_FILE_RE.match(filename))


def extract_sections(text):
    """Extract standard sections and normative rules."""
    sections = []
    current_title = None
    buffer = []

    for line in text.splitlines():
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            if current_title is not None:
                sections.append((current_title, "\n".join(buffer).strip()))
            current_title = m.group(2).strip()
            buffer = []
        elif current_title is not None:
            buffer.append(line)

    if current_title is not None:
        sections.append((current_title, "\n".join(buffer).strip()))

    normative_parts = []
    for title, content in sections:
        if any(h in title.lower() for h in NORMATIVE_HEADINGS) and content:
            normative_parts.append(f"### {title}\n{content}")

    if normative_parts:
        return "\n\n".join(normative_parts)
    return text.strip()


def score_relevance(text, terms):
    if not terms:
        return 1.0
    text_low = text.lower()
    score = 0
    for term in terms:
        term_low = term.lower().strip()
        if not term_low:
            continue
        matches = len(re.findall(r"\b" + re.escape(term_low) + r"\b", text_low))
        score += matches
    return score


def scan_standards(query_terms=None):
    results = []

    for repo_info in REPOS_PRECEDENCE:
        repo_dir = os.path.join(WORKSPACE_ROOT, repo_info["name"])
        if not os.path.isdir(repo_dir):
            continue

        sha = get_commit_sha(repo_dir)

        for fname in sorted(os.listdir(repo_dir)):
            if not is_standard_file(fname):
                continue

            fpath = os.path.join(repo_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as fh:
                    raw_text = fh.read()
            except Exception:
                continue

            rel_score = score_relevance(raw_text, query_terms) if query_terms else 1.0
            if query_terms and rel_score == 0:
                continue

            rules = extract_sections(raw_text)

            results.append({
                "precedence_rank": repo_info["rank"],
                "standard_code": repo_info["id"],
                "repo_name": repo_info["name"],
                "file_name": fname,
                "commit_sha": sha,
                "relevance_score": rel_score,
                "rules": rules,
                "raw_text": raw_text,
            })

    # Sort strictly by Precedence Rank first, then Relevance Score descending
    results.sort(key=lambda x: (x["precedence_rank"], -x["relevance_score"]))
    return results


def main():
    parser = argparse.ArgumentParser(description="Query enterprise standards with precedence")
    parser.add_argument("--query", "-q", help="Search query or domain terms (space-separated)")
    parser.add_argument("--all", "-a", action="store_true", help="Return all standards")
    parser.add_argument("--json", "-j", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    terms = args.query.split() if args.query else None
    if not terms and not args.all:
        terms = []

    standards = scan_standards(terms)

    if args.json:
        print(json.dumps({"count": len(standards), "standards": standards}, indent=2))
        return

    print("================================================================================")
    print("                  ENTERPRISE ARCHITECTURE & GOVERNANCE KB")
    print("        Precedence Order: CyberSec (CSS) > CloudGov (CGS) > EntArch (EAS)")
    print("================================================================================\n")

    if not standards:
        print(f"No standards found matching query: {args.query or '(all)'}\n")
        return

    for item in standards:
        print(f"[{item['standard_code']}] Rank #{item['precedence_rank']} | {item['repo_name']}/{item['file_name']}")
        print(f"Commit SHA: {item['commit_sha']}")
        print("--------------------------------------------------------------------------------")
        print(item["rules"])
        print("\n")


if __name__ == "__main__":
    main()
