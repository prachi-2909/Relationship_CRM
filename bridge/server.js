// Claude bridge: a tiny OpenAI-compatible HTTP endpoint in front of the Claude CLI.
//
// The CRM backend talks to "an OpenAI-compatible /chat/completions endpoint" (LLM_BASE_URL). This service is
// that endpoint, and answers every request by running `claude -p` (the Claude CLI's non-interactive mode) with
// ONE fixed model. It runs inside the compose project, is reachable only over the internal compose network
// (no host port), and rejects any request without the shared bearer token.
//
// Nothing here logs prompts or replies: only the time, outcome, duration and sizes of each call.
"use strict";

const http = require("http");
const crypto = require("crypto");
const { spawn } = require("child_process");

const PORT = parseInt(process.env.PORT || "8080", 10);
const TOKEN = process.env.BRIDGE_TOKEN || "";
const MODEL = process.env.CLAUDE_MODEL || "claude-sonnet-5-5";
const TIMEOUT_MS = parseInt(process.env.CLAUDE_TIMEOUT_MS || "180000", 10);
const MAX_CONCURRENT = Math.max(1, parseInt(process.env.MAX_CONCURRENT || "2", 10));
const MAX_BODY_BYTES = 2 * 1024 * 1024;
const CLAUDE_BIN = process.env.CLAUDE_BIN || "claude";
// Test hook: extra leading arguments (e.g. a fake CLI script when CLAUDE_BIN is node).
const BIN_PREARGS = (process.env.CLAUDE_BIN_PREARGS || "").split(" ").filter(Boolean);
// Escape hatch if a CLI version needs or rejects a flag; space-separated, appended to the call.
const EXTRA_ARGS = (process.env.CLAUDE_EXTRA_ARGS || "").split(" ").filter(Boolean);
const WORKDIR = process.env.CLAUDE_WORKDIR || process.cwd();

function log(msg) {
  console.log(`${new Date().toISOString()} ${msg}`);
}

function tokenOk(header) {
  const given = Buffer.from((header || "").replace(/^Bearer\s+/i, ""));
  const want = Buffer.from(TOKEN);
  return given.length === want.length && crypto.timingSafeEqual(given, want);
}

function send(res, status, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(status, { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(body) });
  res.end(body);
}

// OpenAI-style messages -> (system prompt, one text turn for the CLI).
function toPrompt(messages) {
  const system = [];
  const turns = [];
  for (const m of messages) {
    const text = typeof m.content === "string" ? m.content : JSON.stringify(m.content);
    if (m.role === "system") system.push(text);
    else turns.push({ role: m.role === "assistant" ? "assistant" : "user", text });
  }
  let prompt;
  if (turns.length === 1) {
    prompt = turns[0].text;
  } else {
    // A running conversation: replay it so the model can resolve follow-ups, ending on the user's last turn.
    prompt =
      "Conversation so far:\n" +
      turns.map((t) => `${t.role === "user" ? "User" : "Assistant"}: ${t.text}`).join("\n\n") +
      "\n\nReply to the last User message only.";
  }
  return { system: system.join("\n\n"), prompt };
}

// A small FIFO limiter so a burst of calls cannot start dozens of CLI processes at once.
let running = 0;
const waiting = [];
function acquire() {
  return new Promise((resolve) => {
    if (running < MAX_CONCURRENT) {
      running += 1;
      resolve();
    } else {
      waiting.push(resolve);
    }
  });
}
function release() {
  const next = waiting.shift();
  if (next) next();
  else running -= 1;
}

function runClaude(system, prompt) {
  return new Promise((resolve, reject) => {
    const args = [...BIN_PREARGS, "-p", "--model", MODEL, "--output-format", "text", "--max-turns", "1"];
    if (system) args.push("--system-prompt", system);
    args.push(...EXTRA_ARGS);
    const child = spawn(CLAUDE_BIN, args, { cwd: WORKDIR, stdio: ["pipe", "pipe", "pipe"] });
    let out = "";
    let err = "";
    const timer = setTimeout(() => {
      child.kill("SIGKILL");
      reject(new Error(`claude timed out after ${TIMEOUT_MS} ms`));
    }, TIMEOUT_MS);
    child.stdout.on("data", (d) => (out += d));
    child.stderr.on("data", (d) => (err += d));
    child.on("error", (e) => {
      clearTimeout(timer);
      reject(e);
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      if (code === 0) resolve(out.trim());
      else reject(new Error(`claude exited ${code}: ${err.trim().slice(0, 400)}`));
    });
    child.stdin.on("error", () => {}); // the child may exit before reading everything
    child.stdin.end(prompt);
  });
}

function handleChat(req, res) {
  if (!tokenOk(req.headers.authorization)) return send(res, 401, { error: { message: "bad token" } });
  let size = 0;
  const chunks = [];
  req.on("data", (c) => {
    size += c.length;
    if (size > MAX_BODY_BYTES) {
      send(res, 413, { error: { message: "request too large" } });
      req.destroy();
    } else chunks.push(c);
  });
  req.on("end", async () => {
    let body;
    try {
      body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
      if (!Array.isArray(body.messages) || body.messages.length === 0) throw new Error("no messages");
    } catch (e) {
      return send(res, 400, { error: { message: "invalid request" } });
    }
    const { system, prompt } = toPrompt(body.messages);
    const started = Date.now();
    await acquire();
    try {
      const reply = await runClaude(system, prompt);
      log(`ok ${Date.now() - started}ms in=${prompt.length}c out=${reply.length}c`);
      send(res, 200, {
        object: "chat.completion",
        model: MODEL,
        choices: [{ index: 0, finish_reason: "stop", message: { role: "assistant", content: reply } }],
      });
    } catch (e) {
      log(`error ${Date.now() - started}ms ${e.message}`);
      send(res, 502, { error: { message: "claude call failed" } });
    } finally {
      release();
    }
  });
}

const server = http.createServer((req, res) => {
  if (req.method === "GET" && req.url === "/health") return send(res, 200, { status: "ok", model: MODEL });
  if (req.method === "POST" && req.url === "/v1/chat/completions") return handleChat(req, res);
  send(res, 404, { error: { message: "not found" } });
});

if (process.argv.includes("--selftest")) {
  // Run inside the container once after logging in: proves the CLI, the login and the model all work.
  runClaude("", "Reply with exactly the word: OK")
    .then((r) => {
      console.log(`selftest model=${MODEL} reply=${JSON.stringify(r)}`);
      process.exit(0);
    })
    .catch((e) => {
      console.error(`selftest FAILED: ${e.message}`);
      process.exit(1);
    });
} else {
  if (!TOKEN) {
    console.error("BRIDGE_TOKEN is not set; refusing to start without a shared token.");
    process.exit(1);
  }
  server.listen(PORT, "0.0.0.0", () => log(`claude bridge listening on :${PORT}, model ${MODEL}`));
}
