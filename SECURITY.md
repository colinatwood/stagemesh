# Security policy

## Supported versions

StageMesh is pre-1.0 software. Security fixes are applied to the latest `main`
branch and, when one exists, the newest published prerelease. Older prereleases
are not supported. No current version is qualified for unattended,
show-critical, or safety-critical operation.

## Reporting a vulnerability

Do not disclose suspected vulnerabilities, credentials, exploit details, private
logs, or device identifiers in a public issue or discussion.

Use GitHub's private vulnerability-reporting flow for this repository:
<https://github.com/colinatwood/stagemesh/security/advisories/new>. If that flow
is unavailable, contact the repository owner through the GitHub profile without
including sensitive details, and request a private reporting channel.

Include the affected commit or version, operating system, impact, reproduction
conditions, and a minimal proof of concept when safe. Remove tokens, usernames,
hostnames, hardware serial numbers, and personal data from evidence.

The project will acknowledge a usable private report, investigate it, coordinate
a fix and disclosure when appropriate, and credit reporters who request credit.
Response times are best effort because this is an open-source pre-1.0 project.

## Security scope

Useful reports include authentication or authorization bypasses, unsafe output
arming, IPC or network-boundary defects, malicious project/session handling,
path traversal, code execution, secret exposure, and updater or artifact-integrity
problems. Physical-hardware qualification, signing certificates, production IdP
deployment, and legal review are separate release boundaries.
