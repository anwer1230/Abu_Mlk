---
name: GitHub push credentials
description: Safe fallback for pushing to GitHub when the managed source-control connection is unavailable.
---

When the managed GitHub source-control integration has no credentials, a repository push can use the `GITHUB_TOKEN` Replit Secret through a temporary `GIT_ASKPASS` helper. Do not put the token in a remote URL, Git config, command output, or project files.

**Why:** The managed Git push operation may report missing source-control credentials even when a GitHub token is available as a project secret.

**How to apply:** Request or confirm `GITHUB_TOKEN` through the secrets flow, use it only in the process environment for the push, remove the temporary helper afterward, and verify the remote commit hash without printing the token.