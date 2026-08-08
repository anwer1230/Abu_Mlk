import { randomUUID } from "node:crypto";
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { Router, type IRouter, type Request, type Response } from "express";
import { logger } from "../lib/logger";

type WorkerResponse = {
  id: string;
  ok: boolean;
  result?: unknown;
  error?: string;
};

type Pending = {
  resolve: (value: unknown) => void;
  reject: (error: Error) => void;
  timer: NodeJS.Timeout;
};

let worker: ChildProcessWithoutNullStreams | null = null;
let stdoutBuffer = "";
const pending = new Map<string, Pending>();

function rejectPending(error: Error) {
  for (const [id, request] of pending) {
    clearTimeout(request.timer);
    request.reject(error);
    pending.delete(id);
  }
}

function ensureWorker() {
  if (worker && !worker.killed) return worker;
  const workerCandidates = [
    path.resolve(process.cwd(), "telegram_backend", "worker.py"),
    path.resolve(process.cwd(), "..", "..", "telegram_backend", "worker.py"),
  ];
  const workerPath = workerCandidates.find((candidate) => existsSync(candidate));
  if (!workerPath) {
    throw new Error("Telegram worker.py was not found in the project");
  }
  worker = spawn(process.env.TELEGRAM_PYTHON ?? "python3", ["-u", workerPath], {
    cwd: path.dirname(path.dirname(workerPath)),
    env: process.env,
    stdio: ["pipe", "pipe", "pipe"],
  });
  worker.stdout.setEncoding("utf8");
  worker.stdout.on("data", (chunk: string) => {
    stdoutBuffer += chunk;
    const lines = stdoutBuffer.split("\n");
    stdoutBuffer = lines.pop() ?? "";
    for (const line of lines) {
      if (!line.trim()) continue;
      try {
        const message = JSON.parse(line) as WorkerResponse;
        const request = pending.get(message.id);
        if (!request) continue;
        clearTimeout(request.timer);
        pending.delete(message.id);
        if (message.ok) request.resolve(message.result);
        else request.reject(new Error(message.error ?? "Telegram worker error"));
      } catch (error) {
        logger.warn({ error }, "Ignored malformed Telegram worker output");
      }
    }
  });
  worker.stderr.setEncoding("utf8");
  worker.stderr.on("data", (chunk: string) => {
    logger.warn({ output: chunk.trim() }, "Telegram worker reported an error");
  });
  worker.on("exit", (code, signal) => {
    rejectPending(new Error(`Telegram worker stopped (${code ?? signal ?? "unknown"})`));
    worker = null;
  });
  return worker;
}

function callWorker(method: string, params: Record<string, unknown> = {}) {
  const current = ensureWorker();
  const id = randomUUID();
  return new Promise<unknown>((resolve, reject) => {
    const timer = setTimeout(() => {
      pending.delete(id);
      reject(new Error("Telegram worker timed out"));
    }, 30_000);
    pending.set(id, { resolve, reject, timer });
    current.stdin.write(`${JSON.stringify({ id, method, params })}\n`);
  });
}

function requireString(req: Request, key: string) {
  const value = req.body?.[key];
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${key} is required`);
  }
  return value.trim();
}

function sendResult(res: Response, promise: Promise<unknown>) {
  promise.then((result) => res.json(result)).catch((error: unknown) => {
    const message = error instanceof Error ? error.message : "Telegram request failed";
    res.status(503).json({ error: message });
  });
}

const router: IRouter = Router();

router.get("/telegram/state", (_req, res) => sendResult(res, callWorker("state")));
router.post("/telegram/auth/start", (req, res) => {
  try {
    sendResult(res, callWorker("auth.start", { phone_number: requireString(req, "phone_number") }));
  } catch (error) {
    res.status(400).json({ error: error instanceof Error ? error.message : "Invalid request" });
  }
});
router.post("/telegram/auth/code", (req, res) => {
  try {
    sendResult(res, callWorker("auth.code", { code: requireString(req, "code") }));
  } catch (error) {
    res.status(400).json({ error: error instanceof Error ? error.message : "Invalid request" });
  }
});
router.post("/telegram/auth/password", (req, res) => {
  try {
    sendResult(res, callWorker("auth.password", { password: requireString(req, "password") }));
  } catch (error) {
    res.status(400).json({ error: error instanceof Error ? error.message : "Invalid request" });
  }
});
router.get("/telegram/chats", (req, res) => {
  const limit = Number(req.query.limit ?? 100);
  sendResult(res, callWorker("chats", { limit: Number.isFinite(limit) ? limit : 100 }));
});
router.get("/telegram/chat/:chatId", (req, res) => {
  sendResult(res, callWorker("chat", { chat_id: req.params.chatId }));
});
router.get("/telegram/chat/:chatId/history", (req, res) => {
  const limit = Number(req.query.limit ?? 50);
  sendResult(res, callWorker("history", { chat_id: req.params.chatId, limit }));
});
router.post("/telegram/messages", (req, res) => {
  try {
    sendResult(res, callWorker("send.text", {
      chat_id: Number(requireString(req, "chat_id")),
      text: requireString(req, "text"),
    }));
  } catch (error) {
    res.status(400).json({ error: error instanceof Error ? error.message : "Invalid request" });
  }
});

export default router;