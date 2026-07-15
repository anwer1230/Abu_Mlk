---
name: Repo Share multi-file links
description: Data model decision for sharing several repo files under one or more share links.
---

Share links always support N files (N=1 is just the common case), backed by a normalized
`share_link_files` join table (shareLinkId, filePath, position) rather than a single `filePath`
column or a separate "multi" mode/table.

**Why:** avoids maintaining two parallel models (single-file vs multi-file). "One link for 5 files"
is one `share_links` row with 5 join rows; "5 separate links" is the frontend looping the create
call 5 times with 1 file each — no special backend branch needed for that case.

**How to apply:** PR creation for a link must batch all its files into a single commit (Git Data API:
blobs → tree → commit → ref) rather than one commit per file, so a multi-file link still produces
one reviewable PR. The public editor UI shows tabs when a link has >1 file.
