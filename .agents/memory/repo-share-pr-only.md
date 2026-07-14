---
name: Repo Share Editor safety design
description: Why the shareable-repo-file-editor feature opens PRs instead of pushing directly, and where the GitHub token boundary lives.
---

When building a feature that lets an untrusted party (public link, or an AI agent) edit a file in a
user's GitHub repo, never let the write path push directly to a branch using a token exposed to the
client. Always route edits through: fetch content → create a new branch off base → commit the edit →
open a pull request. The PR is the safety boundary — a human reviews before merge.

**Why:** the user originally asked for a public share link that pushed directly using an embedded/public
token; that design was rejected as a serious security risk (anyone with the link could silently rewrite
repo history, and the token would be exposed in client-reachable code).

**How to apply:** keep the real GitHub token (e.g. `GITHUB_TOKEN`) read only in server-side code, never
sent to the frontend. If a user pastes a raw token/secret directly into chat, treat it as compromised —
tell them to revoke it immediately and collect a fresh one through the proper secrets flow.
