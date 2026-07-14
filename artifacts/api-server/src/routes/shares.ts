import { Router, type IRouter } from "express";
import { randomUUID, randomBytes } from "node:crypto";
import { eq, count } from "drizzle-orm";
import { db, shareLinksTable, submissionsTable } from "@workspace/db";
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
} from "@workspace/api-zod";
import { fetchFileContent, createPullRequestWithEdit } from "../lib/github";

const router: IRouter = Router();

function generateSlug(): string {
  return randomBytes(6).toString("base64url");
}

function isExpired(link: ShareLinkRow): boolean {
  return Boolean(link.expiresAt && link.expiresAt.getTime() < Date.now());
}

async function withSubmissionCount(link: ShareLinkRow) {
  const [row] = await db
    .select({ value: count() })
    .from(submissionsTable)
    .where(eq(submissionsTable.shareLinkId, link.id));
  return { ...link, submissionCount: row?.value ?? 0 };
}

router.get("/shares", async (_req, res): Promise<void> => {
  const links = await db
    .select()
    .from(shareLinksTable)
    .orderBy(shareLinksTable.createdAt);
  const withCounts = await Promise.all(links.map(withSubmissionCount));
  res.json(ListShareLinksResponse.parse(withCounts));
});

router.post("/shares", async (req, res): Promise<void> => {
  const parsed = CreateShareLinkBody.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({ error: parsed.error.message });
    return;
  }

  const [link] = await db
    .insert(shareLinksTable)
    .values({
      id: randomUUID(),
      slug: generateSlug(),
      repoOwner: parsed.data.repoOwner,
      repoName: parsed.data.repoName,
      filePath: parsed.data.filePath,
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

  res
    .status(201)
    .json(CreateShareLinkResponse.parse({ ...link, submissionCount: 0 }));
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

  let fileContent: string;
  try {
    fileContent = await fetchFileContent(
      link.repoOwner,
      link.repoName,
      link.filePath,
      link.baseBranch,
    );
  } catch (err) {
    req.log.error({ err }, "Failed to fetch file content from GitHub");
    res.status(404).json({ error: "Could not load file from the repository" });
    return;
  }

  const withCount = await withSubmissionCount(link);
  res.json(GetShareLinkResponse.parse({ ...withCount, fileContent }));
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

  const withCount = await withSubmissionCount(link);
  res.json(UpdateShareLinkResponse.parse(withCount));
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

  const branchName = `share-edit/${link.slug}-${Date.now()}`;
  const submitterLabel = parsed.data.submitterName?.trim() || "an anonymous collaborator";

  let prResult: { prUrl: string; prNumber: number };
  try {
    prResult = await createPullRequestWithEdit({
      owner: link.repoOwner,
      repo: link.repoName,
      baseBranch: link.baseBranch,
      filePath: link.filePath,
      newContent: parsed.data.content,
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
