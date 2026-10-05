#!/usr/bin/env python3
"""Standards Knowledge Base & Vector Precedence Query Engine.

Indexes enterprise standards (CSS, CGS, EAS) into a persistent SQLite Vector DB
and performs vector semantic search with strict enterprise precedence ranking.

Usage:
  python3 standards_kb.py --query "relational database CMEK encryption"
  python3 standards_kb.py --reindex
  python3 standards_kb.py --all --json
"""
import argparse
import json
import os
import re
import subprocess
import sys

# Import local vector database
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vector_db import StandardsVectorDB, PRECEDENCE_WEIGHTS


def find_workspace_root():
    """Locate the root directory containing the standards repositories."""
    current = os.path.dirname(os.path.abspath(__file__))
    while current and current != os.path.dirname(current):
        if (os.path.isdir(os.path.join(current, "cyber-sec-standards")) or
            os.path.isdir(os.path.join(current, "cloud-gov-standards")) or
            os.path.isdir(os.path.join(current, "enterprise-arch-standards"))):
            return current
        current = os.path.dirname(current)
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


def chunk_standard_document(repo_info, filename, raw_text, commit_sha):
    """Break standard markdown into section-level semantic chunks for vector indexing."""
    chunks = []
    current_title = "Overview & Context"
    buffer = []

    for line in raw_text.splitlines():
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            if buffer:
                content = "\n".join(buffer).strip()
                if content:
                    chunk_id = f"{repo_info['id']}::{filename}::{current_title}"
                    chunks.append({
                        "id": chunk_id,
                        "repo_name": repo_info["name"],
                        "standard_code": repo_info["id"],
                        "precedence_rank": repo_info["rank"],
                        "file_name": filename,
                        "commit_sha": commit_sha,
                        "section_title": current_title,
                        "content": content,
                    })
            current_title = m.group(2).strip()
            buffer = []
        else:
            buffer.append(line)

    if buffer:
        content = "\n".join(buffer).strip()
        if content:
            chunk_id = f"{repo_info['id']}::{filename}::{current_title}"
            chunks.append({
                "id": chunk_id,
                "repo_name": repo_info["name"],
                "standard_code": repo_info["id"],
                "precedence_rank": repo_info["rank"],
                "file_name": filename,
                "commit_sha": commit_sha,
                "section_title": current_title,
                "content": content,
            })

    return chunks


def sync_vector_db(vdb, force=False):
    """Scan peer standards repos and update the vector database if commit SHAs changed."""
    total_indexed = 0

    for repo_info in REPOS_PRECEDENCE:
        repo_dir = os.path.join(WORKSPACE_ROOT, repo_info["name"])
        if not os.path.isdir(repo_dir):
            continue

        sha = get_commit_sha(repo_dir)
        last_sha = vdb.get_sync_state(repo_info["name"])

        if not force and last_sha == sha and vdb.count() > 0:
            continue

        # Re-index all standard files in this repo
        for fname in sorted(os.listdir(repo_dir)):
            if not is_standard_file(fname):
                continue

            fpath = os.path.join(repo_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as fh:
                    raw_text = fh.read()
            except Exception:
                continue

            chunks = chunk_standard_document(repo_info, fname, raw_text, sha)
            vdb.index_chunks(chunks)
            total_indexed += len(chunks)

        vdb.update_sync_state(repo_info["name"], sha)

    return total_indexed


def main():
    parser = argparse.ArgumentParser(description="Query enterprise standards with Vector DB & Precedence")
    parser.add_argument("--query", "-q", help="Semantic search query (natural language or keywords)")
    parser.add_argument("--reindex", "-r", action="store_true", help="Force re-indexing of all standards into Vector DB")
    parser.add_argument("--all", "-a", action="store_true", help="Return all standards chunks")
    parser.add_argument("--top-k", "-k", type=int, default=8, help="Number of vector results to retrieve")
    parser.add_argument("--json", "-j", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    vdb = StandardsVectorDB()
    indexed = sync_vector_db(vdb, force=args.reindex)

    if not args.query and not args.all:
        if args.reindex:
            print(f"✅ Re-indexed {indexed} chunks into Vector DB ({vdb.db_path})")
            return
        args.query = "database security cloud governance architecture"

    if args.all:
        matches = vdb.query("", top_k=100, min_score=0.0)
    else:
        matches = vdb.query(args.query, top_k=args.top_k, min_score=0.10)

    if args.json:
        print(json.dumps({
            "query": args.query,
            "vector_db_path": vdb.db_path,
            "total_chunks_in_db": vdb.count(),
            "results_count": len(matches),
            "results": matches,
        }, indent=2))
        return

    print("================================================================================")
    print("           ENTERPRISE STANDARDS VECTOR DATABASE (SEMANTIC RAG)")
    print("        Precedence: CSS (1.0x) > CGS (0.85x) > EAS (0.70x)")
    print(f"        Vector DB: {vdb.db_path} | Indexed Chunks: {vdb.count()}")
    print("================================================================================\n")
    print(f"🔍 Semantic Query: \"{args.query}\"\n")

    if not matches:
        print("No matching standards found in Vector DB.\n")
        return

    for item in matches:
        print(f"[{item['standard_code']}] Rank #{item['precedence_rank']} | {item['repo_name']}/{item['file_name']}")
        print(f"Section:    {item['section_title']}")
        print(f"Commit SHA: {item['commit_sha']}")
        print(f"Vector Sim: {item['cosine_similarity']:.4f} | Weighted Score: {item['final_score']:.4f}")
        print("--------------------------------------------------------------------------------")
        print(item["content"])
        print("\n")


if __name__ == "__main__":
    main()
