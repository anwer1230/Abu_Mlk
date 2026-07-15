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
 * Reads the current content of several files from a repository branch in
 * parallel — used when a share link bundles more than one file.
 */
export async function fetchMultipleFileContents(
  owner: string,
  repo: string,
  paths: string[],
  branch: string,
): Promise<{ filePath: string; content: string }[]> {
  return Promise.all(
    paths.map(async (filePath) => ({
      filePath,
      content: await fetchFileContent(owner, repo, filePath, branch),
    })),
  );
}

/**
 * Lists every file path in a repo branch, so a share link can be created by
 * picking a file instead of typing its path from memory. Falls back to the
 * repo's default branch when none is specified.
 */
export async function fetchRepoTree(
  owner: string,
  repo: string,
  branch?: string,
): Promise<{ defaultBranch: string; files: string[] }> {
  const octokit = getOctokit();

  const { data: repoInfo } = await octokit.repos.get({ owner, repo });
  const targetBranch = branch || repoInfo.default_branch;

  const { data: ref } = await octokit.git.getRef({
    owner,
    repo,
    ref: `heads/${targetBranch}`,
  });

  const { data: tree } = await octokit.git.getTree({
    owner,
    repo,
    tree_sha: ref.object.sha,
    recursive: "true",
  });

  const files = tree.tree
    .filter((entry) => entry.type === "blob" && typeof entry.path === "string")
    .map((entry) => entry.path as string)
    .sort();

  return { defaultBranch: repoInfo.default_branch, files };
}

/**
 * Opens a pull request with edits to one or more files — never pushes
 * directly to the base branch. This is the only write path a public share
 * link can trigger: every change lands as a single reviewable PR on a fresh
 * branch, as one commit even when it touches several files.
 */
export async function createPullRequestWithEdit(params: {
  owner: string;
  repo: string;
  baseBranch: string;
  files: { filePath: string; newContent: string }[];
  branchName: string;
  prTitle: string;
  prBody: string;
}): Promise<{ prUrl: string; prNumber: number }> {
  const { owner, repo, baseBranch, files, branchName, prTitle, prBody } =
    params;
  const octokit = getOctokit();

  const { data: baseRef } = await octokit.git.getRef({
    owner,
    repo,
    ref: `heads/${baseBranch}`,
  });
  const baseCommitSha = baseRef.object.sha;

  const { data: baseCommit } = await octokit.git.getCommit({
    owner,
    repo,
    commit_sha: baseCommitSha,
  });

  const blobs = await Promise.all(
    files.map(async (file) => {
      const { data: blob } = await octokit.git.createBlob({
        owner,
        repo,
        content: Buffer.from(file.newContent, "utf-8").toString("base64"),
        encoding: "base64",
      });
      return { filePath: file.filePath, sha: blob.sha };
    }),
  );

  const { data: newTree } = await octokit.git.createTree({
    owner,
    repo,
    base_tree: baseCommit.tree.sha,
    tree: blobs.map((blob) => ({
      path: blob.filePath,
      mode: "100644",
      type: "blob",
      sha: blob.sha,
    })),
  });

  const { data: newCommit } = await octokit.git.createCommit({
    owner,
    repo,
    message:
      files.length === 1
        ? `Update ${files[0]?.filePath} via shared edit link`
        : `Update ${files.length} files via shared edit link`,
    tree: newTree.sha,
    parents: [baseCommitSha],
  });

  await octokit.git.createRef({
    owner,
    repo,
    ref: `refs/heads/${branchName}`,
    sha: newCommit.sha,
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
