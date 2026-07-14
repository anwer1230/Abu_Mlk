import { Octokit } from "@octokit/rest";

function getOctokit(): Octokit {
  const token = process.env.GITHUB_TOKEN;
  if (!token) {
    throw new Error("GITHUB_TOKEN is not configured.");
  }
  return new Octokit({ auth: token });
}

/**
 * Reads the current content of a file from a repository branch. Always
 * fetched fresh — never cached — so viewers see the live version.
 */
export async function fetchFileContent(
  owner: string,
  repo: string,
  path: string,
  branch: string,
): Promise<string> {
  const octokit = getOctokit();
  const { data } = await octokit.repos.getContent({
    owner,
    repo,
    path,
    ref: branch,
  });

  if (Array.isArray(data) || data.type !== "file" || !("content" in data)) {
    throw new Error("Path does not point to a readable file");
  }

  return Buffer.from(data.content, "base64").toString("utf-8");
}

/**
 * Opens a pull request with an edited file — never pushes directly to the
 * base branch. This is the only write path a public share link can trigger:
 * every change lands as a reviewable PR on a fresh branch.
 */
export async function createPullRequestWithEdit(params: {
  owner: string;
  repo: string;
  baseBranch: string;
  filePath: string;
  newContent: string;
  branchName: string;
  prTitle: string;
  prBody: string;
}): Promise<{ prUrl: string; prNumber: number }> {
  const {
    owner,
    repo,
    baseBranch,
    filePath,
    newContent,
    branchName,
    prTitle,
    prBody,
  } = params;
  const octokit = getOctokit();

  const { data: baseRef } = await octokit.git.getRef({
    owner,
    repo,
    ref: `heads/${baseBranch}`,
  });

  await octokit.git.createRef({
    owner,
    repo,
    ref: `refs/heads/${branchName}`,
    sha: baseRef.object.sha,
  });

  let existingSha: string | undefined;
  try {
    const { data: existing } = await octokit.repos.getContent({
      owner,
      repo,
      path: filePath,
      ref: branchName,
    });
    if (!Array.isArray(existing) && existing.type === "file") {
      existingSha = existing.sha;
    }
  } catch {
    // File doesn't exist yet on this branch — creating a new file is fine.
  }

  await octokit.repos.createOrUpdateFileContents({
    owner,
    repo,
    path: filePath,
    message: `Update ${filePath} via shared edit link`,
    content: Buffer.from(newContent, "utf-8").toString("base64"),
    branch: branchName,
    sha: existingSha,
  });

  const { data: pr } = await octokit.pulls.create({
    owner,
    repo,
    title: prTitle,
    body: prBody,
    head: branchName,
    base: baseBranch,
  });

  return { prUrl: pr.html_url, prNumber: pr.number };
}
