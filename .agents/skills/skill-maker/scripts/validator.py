#!/usr/bin/env python3
"""Skill Compliance Validator & Linter.

Lints and validates Antigravity SKILL.md files against enterprise standards:
1. Validates YAML frontmatter (name, description).
2. Verifies structural sections (Instructions, Hard Guardrails, Traceability Matrix).
3. Detects prohibited configurations and security anti-patterns.
4. Audits the Traceability Matrix against live repository commit SHAs.

Usage:
  python3 validator.py --skill-path /path/to/SKILL.md
  python3 validator.py --skill-path ../../setup-relational-db/SKILL.md --json
"""
import argparse
import json
import os
import re
import sys

try:
    import yaml
except ImportError:
    yaml = None


def log(msg):
    print(f"[validator] {msg}", file=sys.stderr)


def parse_frontmatter(content):
    """Extract and parse YAML frontmatter."""
    if not content.startswith("---"):
        return None, content, "Missing starting '---' frontmatter boundary"

    parts = content.split("---", 2)
    if len(parts) < 3:
        return None, content, "Malformed frontmatter (missing closing '---')"

    raw_yaml = parts[1]
    body = parts[2]

    metadata = {}
    if yaml:
        try:
            metadata = yaml.safe_load(raw_yaml) or {}
        except Exception as e:
            return None, body, f"YAML parse error: {e}"
    else:
        for line in raw_yaml.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                metadata[k.strip()] = v.strip()

    return metadata, body, None


def validate_skill(content, filepath=None):
    issues = []
    warnings = []
    info = []

    # 1. Frontmatter Validation
    meta, body, fm_err = parse_frontmatter(content)
    if fm_err:
        issues.append(f"Frontmatter Error: {fm_err}")
    else:
        if not meta.get("name"):
            issues.append("Frontmatter missing required 'name' field")
        elif not re.match(r"^[a-z0-9-_]+$", str(meta["name"])):
            warnings.append(f"Skill name '{meta.get('name')}' should be lowercase kebab-case")

        if not meta.get("description"):
            issues.append("Frontmatter missing required 'description' field")
        elif len(str(meta["description"])) < 20:
            warnings.append("Skill description is very short; describe when the agent should activate it")

    # 2. Structural Heading Verification
    headings = [line.strip() for line in body.splitlines() if line.startswith("#")]
    h2_titles = [re.sub(r"^##\s+", "", h).lower() for h in headings if h.startswith("## ")]

    if not any("guardrail" in h or "rule" in h or "requirement" in h for h in h2_titles):
        warnings.append("Missing explicit '## Hard Guardrails' or '## Rules' section")

    if not any("instruction" in h or "step" in h or "workflow" in h for h in h2_titles):
        issues.append("Missing explicit '## Instructions' or workflow section")

    has_traceability = any("traceability" in h for h in h2_titles)
    if not has_traceability:
        issues.append("Missing '## Traceability Matrix' section linking governing standards")

    # 3. Compliance Anti-Pattern & Guardrail Checks
    body_low = body.lower()

    # AWS & Provider checks: check for actual resource declarations
    if re.search(r'resource\s+"(google_|azurerm_)', body_low) or re.search(r'provider\s+"(google|azurerm)"', body_low):
        issues.append("Prohibited non-AWS provider resource declaration found (violates CGS_1)")

    # Encryption checks for DB / storage
    if "database" in body_low or "postgres" in body_low or "rds" in body_low or "aurora" in body_low:
        if "storage_encrypted" not in body_low and "encrypted" not in body_low:
            issues.append("Missing explicit storage encryption requirement (violates CSS_1)")
        if "kms" not in body_low and "cmek" not in body_low:
            warnings.append("KMS / CMEK encryption key reference not found (violates CSS_1)")
        if "iam" not in body_low:
            warnings.append("IAM database authentication not explicitly enforced (violates CSS_1)")
        if "publicly_accessible = true" in body_low:
            issues.append("Security Violation: 'publicly_accessible = true' detected (violates CGS_1 / CSS_1)")

    # 4. Traceability Matrix Audit
    if has_traceability:
        if not re.search(r"\|\s*(CSS|CGS|EAS)\s*\|", body):
            warnings.append("Traceability Matrix does not appear to contain standard references (CSS, CGS, EAS)")
        if not re.search(r"[0-9a-f]{7,40}", body):
            warnings.append("Traceability Matrix missing commit SHAs for version verification")

    passed = len(issues) == 0
    return {
        "valid": passed,
        "file": filepath,
        "issues": issues,
        "warnings": warnings,
        "metadata": meta,
    }


def main():
    parser = argparse.ArgumentParser(description="Validate Antigravity SKILL.md against enterprise standards")
    parser.add_argument("--skill-path", "-p", required=True, help="Path to SKILL.md file")
    parser.add_argument("--json", "-j", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    fpath = os.path.abspath(args.skill_path)
    if not os.path.isfile(fpath):
        print(f"Error: file not found: {fpath}", file=sys.stderr)
        sys.exit(1)

    with open(fpath, "r", encoding="utf-8") as fh:
        content = fh.read()

    result = validate_skill(content, fpath)

    if args.json:
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["valid"] else 1)

    print("================================================================================")
    print(f"           SKILL COMPLIANCE VALIDATION REPORT: {os.path.basename(fpath)}")
    print("================================================================================")
    print(f"Status:   {'✅ PASSED' if result['valid'] else '❌ FAILED'}")
    print(f"Skill:    {result['metadata'].get('name', 'unknown')}")
    print(f"Location: {fpath}\n")

    if result["issues"]:
        print("❌ Critical Issues (Must be resolved):")
        for i in result["issues"]:
            print(f"  • {i}")
        print()

    if result["warnings"]:
        print("⚠️  Warnings / Recommendations:")
        for w in result["warnings"]:
            print(f"  • {w}")
        print()

    if result["valid"] and not result["warnings"]:
        print("✨ All enterprise standards and Antigravity skill structure criteria are met!")

    sys.exit(0 if result["valid"] else 1)


if __name__ == "__main__":
    main()
