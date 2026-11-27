# Security Policy

## Supported versions

| Version | Security fixes |
| --- | --- |
| 2.0 pre-releases (`2.0.0b*`) | Yes |
| 1.11.x | Yes |
| 1.10 and older | No |

Fixes ship in a new release on PyPI. If you run an unsupported version, upgrade to a supported
one first.

## Report a vulnerability

Please do not report a security vulnerability in a public GitHub issue, discussion or pull
request.

Email **me@vrsen.ai** with the subject line `Security: agency-swarm`. Include:

- the affected version of `agency-swarm` and of `openai-agents`;
- what an attacker can do, and what they need first (for example, network access to a
  FastAPI endpoint or control over a tool's input);
- steps or a small script that reproduce the problem;
- any fix or workaround you know of.

## What happens next

- We confirm we received your report within 5 business days.
- We tell you whether we accept the report, and our plan, within 14 days.
- We aim to release a fix within 90 days of your report. Serious issues come first.
- We keep you updated until the fix ships.

We follow coordinated disclosure. Please keep the details private until a fixed release is out,
or until 90 days have passed, whichever comes first. The release notes of the fix describe the
issue and credit you, unless you ask us not to.
