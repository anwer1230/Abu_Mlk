import { Router, type IRouter } from "express";
import { randomUUID, randomBytes } from "node:crypto";
import { eq, count, asc } from "drizzle-orm";
import {
  db,
  shareLinksTable,
  shareLinkFilesTable,
  submissionsTable,
} from "@workspace/db";
import type { ShareLinkRow } from "@workspace/db";
import {
  ListShareLinksResponse,
  CreateShareLinkBody,
  CreateShareLinkResponse,
  GetShareLinkParams,
  GetShareLinkResponse,
  UpdateShareLinkParams,
  UpdateShareLinkBody,
  UpdateShareLinkResponse,
  DeleteShareLinkParams,
  ListSubmissionsParams,
  ListSubmissionsResponse,
  CreateSubmissionParams,
  CreateSubmissionBody,
  CreateSubmissionResponse,
  GetRepoTreeQueryParams,
  GetRepoTreeResponse,
} from "@workspace/api-zod";
import {
  fetchMultipleFileContents,
  fetchRepoTree,
  createPullRequestWithEdit,
} from "../lib/github";

const router: IRouter = Router();

function generateSlug(): string {
  return randomBytes(6).toString("base64url");
}

function isExpired(link: ShareLinkRow): boolean {
  return Boolean(link.expiresAt && link.expiresAt.getTime() < Date.now());
}

async function getFilePaths(shareLinkId: string): Promise<string[]> {
  const rows = await db
    .select()
    .from(shareLinkFilesTable)
    .where(eq(shareLinkFilesTable.shareLinkId, shareLinkId))
    .orderBy(asc(shareLinkFilesTable.position));
  return rows.map((row) => row.filePath);
}

async function withDetails(link: ShareLinkRow) {
  const [countRow] = await db
    .select({ value: count() })
    .from(submissionsTable)
    .where(eq(submissionsTable.shareLinkId, link.id));
  const filePaths = await getFilePaths(link.id);
  return {
    ...link,
    filePaths,
    submissionCount: countRow?.value ?? 0,
  };
}

router.get("/shares", async (_req, res): Promise<void> => {
  const links = await db
    .select()
    .from(shareLinksTable)
    .orderBy(shareLinksTable.createdAt);
  const withCounts = await Promise.all(links.map(withDetails));
  res.json(ListShareLinksResponse.parse(withCounts));
});

router.post("/shares", async (req, res): Promise<void> => {
  const parsed = CreateShareLinkBody.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({ error: parsed.error.message });
    return;
  }

  const linkId = randomUUID();

  const [link] = await db
    .insert(shareLinksTable)
    .values({
      id: linkId,
      slug: generateSlug(),
      repoOwner: parsed.data.repoOwner,
      repoName: parsed.data.repoName,
      baseBranch: parsed.data.baseBranch || "main",
      title: parsed.data.title,
      description: parsed.data.description,
      expiresAt: parsed.data.expiresAt
        ? new Date(parsed.data.expiresAt)
        : undefined,
    })
    .returning();

  if (!link) {
    res.status(400).json({ error: "Could not create share link" });
    return;
  }

  await db.insert(shareLinkFilesTable).values(
    parsed.data.filePaths.map((filePath, position) => ({
      id: randomUUID(),
      shareLinkId: linkId,
      filePath,
      position,
    })),
  );

  res.status(201).json(
    CreateShareLinkResponse.parse({
      ...link,
      filePaths: parsed.data.filePaths,
      submissionCount: 0,
    }),
  );
});

router.get("/shares/:slug", async (req, res): Promise<void> => {
  const params = GetShareLinkParams.safeParse(req.params);
  if (!params.success) {
    res.status(400).json({ error: params.error.message });
    return;
  }

  const [link] = await db
    .select()
    .from(shareLinksTable)
    .where(eq(shareLinksTable.slug, params.data.slug));

  if (!link || !link.isActive || isExpired(link)) {
    res
      .status(404)
      .json({ error: "Share link not found, inactive, or expired" });
    return;
  }

  const filePaths = await getFilePaths(link.id);

  let files: { filePath: string; content: string }[];
  try {
    files = await fetchMultipleFileContents(
      link.repoOwner,
      link.repoName,
      filePaths,
      link.baseBranch,
    );
  } catch (err) {
    req.log.error({ err }, "Failed to fetch file content from GitHub");
    res.status(404).json({ error: "Could not load files from the repository" });
    return;
  }

  const [countRow] = await db
    .select({ value: count() })
    .from(submissionsTable)
    .where(eq(submissionsTable.shareLinkId, link.id));

  res.json(
    GetShareLinkResponse.parse({
      ...link,
      filePaths,
      submissionCount: countRow?.value ?? 0,
      files,
    }),
  );
});

router.patch("/shares/:slug", async (req, res): Promise<void> => {
  const params = UpdateShareLinkParams.safeParse(req.params);
  if (!params.success) {
    res.status(400).json({ error: params.error.message });
    return;
  }
  const parsed = UpdateShareLinkBody.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({ error: parsed.error.message });
    return;
  }

  const { expiresAt, ...rest } = parsed.data;
  const updateValues: Partial<ShareLinkRow> = { ...rest };
  if ("expiresAt" in parsed.data) {
    updateValues.expiresAt = expiresAt ? new Date(expiresAt) : null;
  }

  const [link] = await db
    .update(shareLinksTable)
    .set(updateValues)
    .where(eq(shareLinksTable.slug, params.data.slug))
    .returning();

  if (!link) {
    res.status(404).json({ error: "Share link not found" });
    return;
  }

  const withDetail = await withDetails(link);
  res.json(UpdateShareLinkResponse.parse(withDetail));
});

router.delete("/shares/:slug", async (req, res): Promise<void> => {
  const params = DeleteShareLinkParams.safeParse(req.params);
  if (!params.success) {
    res.status(400).json({ error: params.error.message });
    return;
  }

  const [link] = await db
    .delete(shareLinksTable)
    .where(eq(shareLinksTable.slug, params.data.slug))
    .returning();

  if (!link) {
    res.status(404).json({ error: "Share link not found" });
    return;
  }

  res.sendStatus(204);
});

router.get("/repos/tree", async (req, res): Promise<void> => {
  if (!req.query.owner || !req.query.repo) {
    res.status(400).json({ error: "owner and repo query parameters are required" });
    return;
  }

  const params = GetRepoTreeQueryParams.safeParse(req.query);
  if (!params.success) {
    res.status(400).json({ error: params.error.message });
    return;
  }

  try {
    const tree = await fetchRepoTree(
      params.data.owner,
      params.data.repo,
      params.data.branch,
    );
    res.json(GetRepoTreeResponse.parse(tree));
  } catch (err) {
    req.log.error({ err }, "Failed to read repository tree from GitHub");
    res.status(400).json({
      error:
        "Could not read this repository. Check the owner, repo name, and branch, and make sure the connected GitHub account can access it.",
    });
  }
});

router.get("/shares/:slug/submissions", async (req, res): Promise<void> => {
  const params = ListSubmissionsParams.safeParse(req.params);
  if (!params.success) {
    res.status(400).json({ error: params.error.message });
    return;
  }

  const [link] = await db
    .select()
    .from(shareLinksTable)
    .where(eq(shareLinksTable.slug, params.data.slug));
  if (!link) {
    res.status(404).json({ error: "Share link not found" });
    return;
  }

  const submissions = await db
    .select()
    .from(submissionsTable)
    .where(eq(submissionsTable.shareLinkId, link.id))
    .orderBy(submissionsTable.createdAt);

  res.json(ListSubmissionsResponse.parse(submissions));
});

router.post("/shares/:slug/submissions", async (req, res): Promise<void> => {
  const params = CreateSubmissionParams.safeParse(req.params);
  if (!params.success) {
    res.status(400).json({ error: params.error.message });
    return;
  }
  const parsed = CreateSubmissionBody.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({ error: parsed.error.message });
    return;
  }

  const [link] = await db
    .select()
    .from(shareLinksTable)
    .where(eq(shareLinksTable.slug, params.data.slug));

  if (!link || !link.isActive || isExpired(link)) {
    res
      .status(404)
      .json({ error: "Share link not found, inactive, or expired" });
    return;
  }

  const linkFilePaths = await getFilePaths(link.id);
  const submittedPaths = new Set(parsed.data.files.map((f) => f.filePath));
  const missingPaths = linkFilePaths.filter((p) => !submittedPaths.has(p));
  if (missingPaths.length > 0) {
    res.status(400).json({
      error: `Missing content for: ${missingPaths.join(", ")}`,
    });
    return;
  }

  const branchName = `share-edit/${link.slug}-${Date.now()}`;
  const submitterLabel = parsed.data.submitterName?.trim() || "an anonymous collaborator";

  let prResult: { prUrl: string; prNumber: number };
  try {
    prResult = await createPullRequestWithEdit({
      owner: link.repoOwner,
      repo: link.repoName,
      baseBranch: link.baseBranch,
      files: parsed.data.files.map((f) => ({
        filePath: f.filePath,
        newContent: f.content,
      })),
      branchName,
      prTitle: `Edit via share link: ${link.title}`,
      prBody: [
        `Submitted through the share link **${link.title}**.`,
        `Submitter: ${submitterLabel}`,
        parsed.data.note ? `Note: ${parsed.data.note}` : undefined,
        "",
        "Review the diff carefully before merging — this pull request was opened by a public share link, not a repository collaborator.",
      ]
        .filter((line): line is string => Boolean(line))
        .join("\n\n"),
    });
  } catch (err) {
    req.log.error({ err }, "Failed to create pull request from submission");
    res
      .status(400)
      .json({ error: "Could not create a pull request for this edit" });
    return;
  }

  const [submission] = await db
    .insert(submissionsTable)
    .values({
      id: randomUUID(),
      shareLinkId: link.id,
      prUrl: prResult.prUrl,
      prNumber: prResult.prNumber,
      branchName,
      submitterName: parsed.data.submitterName,
      note: parsed.data.note,
    })
    .returning();

  if (!submission) {
    res.status(400).json({ error: "Could not record the submission" });
    return;
  }

  res.status(201).json(CreateSubmissionResponse.parse(submission));
});

export default router;
