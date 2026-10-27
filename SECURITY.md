# Security

## Reporting a vulnerability

Please do not open a public issue for a security problem. Email the maintainers at Eko
(the address the repository owner uses for this project) with what you found, how to reproduce it,
and the version or commit. We will acknowledge it and agree a fix and disclosure timeline with you.

## Handling of data

This CRM holds personal data of CSPs and SBI officials and records of calls. Never commit real data,
credentials or call recordings. The `.gitignore` already excludes `.env` files, databases, media,
backups, the territory map and the data under `backend/app/scripts/data/`.

Retention rules for audio, transcripts, commitments and feedback are in
[`docs/data-retention.md`](docs/data-retention.md); deployment and configuration are in
[`docs/RUNBOOK.md`](docs/RUNBOOK.md).
