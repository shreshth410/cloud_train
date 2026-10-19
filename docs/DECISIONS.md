# Decisions Log

This file records design decisions made during implementation, especially where the spec was ambiguous or deviations were necessary.

| # | Decision | Rationale | Date |
|---|----------|-----------|------|
| 1 | DynamoDB as default metadata store (not RDS) | RDS has no free tier on new accounts; DynamoDB is free-tier friendly (spec D1) | 2026-10-19 |
| 2 | Region default `ap-south-1` (Mumbai) | Team is in India; lower latency (spec D2) | 2026-10-19 |
| 3 | No NAT Gateway, ALB, Elastic IPs, RDS by default | Each costs money continuously (spec D3) | 2026-10-19 |
| 4 | Lambdas not placed in a VPC | They only talk to AWS public APIs; avoids NAT cost (spec D4) | 2026-10-19 |
| 5 | Training instances in public subnets, no inbound rules | SSM Session Manager for admin access; no SSH keys to leak (spec D5) | 2026-10-19 |
| 6 | SQS + Lambda orchestration (no Step Functions) | Fewer moving parts; lifecycle is linear (spec D6) | 2026-10-19 |
| 7 | Cognito for auth with JWT authorizer | Managed, free at this scale (spec D7) | 2026-10-19 |
| 8 | GitHub Actions OIDC (no stored access keys) | No static credentials in repo (spec D8) | 2026-10-19 |
| 9 | Instance types configurable via Terraform variables | Verify at build time which types the account allows (spec D9) | 2026-10-19 |
| 10 | Trainer instance role not scoped per job | Only the platform's own trainer image runs; user code is never executed (spec 11.4 limitation) | 2026-10-19 |
| 11 | Using `make` on Windows via Git Bash / WSL | The Makefile uses bash syntax; Windows users should run via Git Bash, WSL, or equivalent | 2026-10-19 |
| 12 | Relaxed numpy version to `<3` in trainer pyproject.toml | Local dev is on Python 3.13 which lacks numpy<2.1 wheels; Docker container pins 3.11 with exact versions; Dockerfile `pip install` line pins `numpy<2.1` | 2026-10-19 |
| 13 | ASCII log tags in predict_example template | Replaced unicode emoji with `[OK]` to support cp1252 standard Windows shell environments alongside Linux | 2026-10-19 |
