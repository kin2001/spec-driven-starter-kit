# Security policy

## Reporting a vulnerability

Use this repository's [private vulnerability reporting form](https://github.com/kin2001/spec-driven-starter-kit/security/advisories/new). Include affected revision, platform, a minimal reproduction using fake data, impact and any suggested mitigation. Do not put secrets, account tokens or private project data in a report.

Do not open a public issue containing exploit details or exposed credentials. If a credential has already been disclosed, revoke or rotate it with its provider; removing a file or adding an ignore rule does not revoke it.

## Scope and limits

Reports about path handling, archive validation, unintended overwrite, private-state propagation, approval/ownership bypass or misleading verification are especially useful. The latest public default branch is the maintained source; there is no security support SLA or promise for older snapshots.

The kit's instructions coordinate agents and its helpers perform local checks. They do not sandbox an unrestricted process, certify a product, configure production access or guarantee third-party session security. Verify host permissions, intended service identity, dependency scripts and the selected project's actual security controls.
