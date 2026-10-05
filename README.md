# Enterprise Agent Skills Catalog

This repository hosts the centralized, version-controlled library of compliant **Antigravity Skills** for engineering teams. Every skill in this catalog is grounded in enterprise governance policies across Cyber Security, Cloud Governance, and Enterprise Architecture.

---

## Precedence Hierarchy

All skills in this catalog strictly enforce the enterprise standards precedence order:
$$\text{Cyber Security (CSS)} \succ \text{Cloud Governance (CGS)} \succ \text{Enterprise Architecture (EAS)}$$

---

## Active Skills Catalog

| Skill Name | Directory | Description | Precedence / Standards Grounding |
| :--- | :--- | :--- | :--- |
| **`skill-maker`** | [`.agents/skills/skill-maker`](.agents/skills/skill-maker/) | Interactive pair-programming agent that assists developers in crafting compliant Antigravity skills. | CSS, CGS, EAS Knowledge Base & Precedence Engine |
| **`setup-relational-db`** | [`.agents/skills/setup-relational-db`](.agents/skills/setup-relational-db/) | Provisions compliant PostgreSQL databases via Terraform (Aurora Serverless v2 + RDS with KMS CMEK, IAM auth, private subnets, Multi-AZ). | `CSS_1`, `CGS_1`, `EAS_1` |

---

## How to Consume These Skills

### 1. In Your Local Workspace
Clone or symlink this repository's `.agents/` folder into your project workspace:
```bash
# Option A: Copy into your project's .agents directory
cp -r enterprise-agent-skills/.agents/skills/<skill-name> my-service/.agents/skills/

# Option B: Add as a Git Submodule
git submodule add https://github.com/org/enterprise-agent-skills.git .agents
```

### 2. Crafting New Skills
Use the included `skill-maker` agent interactively in Antigravity chat:
> *"I want to create a skill for provisioning an SQS event-driven dead letter queue architecture."*

The `skill-maker` will:
1. Query peer standards repositories (`cyber-sec-standards`, `cloud-gov-standards`, `enterprise-arch-standards`).
2. Present mandatory guardrails and architectural constraints.
3. Interactively draft and validate the new `SKILL.md`.
4. Include an auditable Traceability Matrix linked to commit SHAs.
