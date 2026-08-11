# Security policy

## Supported versions

Security fixes are applied to the latest release and the current `main` branch.
Older tags may not receive backports.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting form under the repository's
**Security** tab. Do not disclose a vulnerability, credential, private path,
proof of concept, or affected user's data in a public issue or discussion.

If private vulnerability reporting is temporarily unavailable, open a public
issue containing only a request for a private maintainer contact. Do not include
technical details until a private channel has been established.

Include, when available:

- the affected Skill, script, version, or commit;
- the operating system and relevant runtime versions;
- minimal reproduction steps using synthetic or non-sensitive data;
- the expected impact and any known mitigations;
- whether credentials, uploads, generated media, or third-party services are
  involved.

The maintainers will make a best effort to acknowledge a complete report within
seven days, assess severity and scope, and coordinate a fix and disclosure
timeline with the reporter.

## Sensitive-data incidents

If a credential or cookie is committed or exposed, revoke or rotate it
immediately. Removing it from the latest commit is not sufficient because Git
history and existing clones may retain it. Report the incident privately so the
repository history and affected integrations can be assessed.

Never include real Bilibili cookies, API keys, SSH keys, private TTS
configuration, unpublished papers, or unauthorized reference voices in a
security report or test fixture.

## Scope

In scope:

- repository scripts and Skill instructions;
- unsafe path handling or unintended file modification;
- credential exposure or command-injection paths;
- bypasses of explicit upload and withdrawal authorization gates;
- bundled asset integrity and local dependency-bootstrap logic.

Third-party model, library, service, Codex, GitHub, and Bilibili vulnerabilities
should normally be reported to their respective maintainers. Please also notify
this project privately when a third-party issue requires a dependency,
documentation, or mitigation change here.
