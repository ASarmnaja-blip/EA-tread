#!/usr/bin/env node
// GPT bridge for the EA-tread project.
//
// Serves a small chat web page and an HTTP API. Both a human (browser) and an
// agent (tools/gpt-bridge/ask.mjs, or plain curl) post into the same
// conversation, so Claude can talk to GPT directly and the browser follows
// along live over SSE.
//
// Start with:  OPENAI_API_KEY=sk-... node tools/gpt-bridge/server.mjs

import http from 'node:http';
import fs from 'node:fs';
import fsp from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(HERE, '..', '..');
const DATA_DIR = path.join(HERE, 'data');
const PUBLIC_DIR = path.join(HERE, 'public');

loadDotEnv(path.join(HERE, '.env'));

const PORT = Number(process.env.PORT || 8787);
const HOST = process.env.HOST || '127.0.0.1';
const MODEL = process.env.OPENAI_MODEL || 'gpt-4o';
const API_BASE = process.env.OPENAI_BASE_URL || 'https://api.openai.com/v1';
const MAX_HISTORY = Number(process.env.MAX_HISTORY || 40);
const MAX_FILE_BYTES = 200_000;

const SYSTEM_PROMPT = `You are a trading-systems engineer helping on the EA-tread project.

Project shape:
- MQL5/ — MetaTrader 5 Expert Advisors and includes (the live EA code)
- pine/ — TradingView Pine Script versions of the same ideas (Dobby strategy/indicator)
- research/ — Python backtests and parameter searches, several written as QuantConnect cells
- tools/ — data export and sizing helpers
- docs/ — backtest notes, research findings, account-scaling notes

Most questions will be about signal logic, entry/exit structure, risk and position
sizing, backtest methodology, or porting logic between MQL5, Pine and Python.

How to answer:
- Be concrete and quantitative. Name the parameter, the bar, the formula.
- When code is discussed, answer in the language of the file at hand and keep the
  surrounding style.
- Call out look-ahead bias, survivorship, overfitting to a single symbol or period,
  and broker-specific assumptions (spread, swap, fill model) whenever they apply.
- Say plainly when a claim needs a backtest to settle, instead of guessing.
- You may be talking to another AI agent rather than a human. Skip pleasantries and
  answer the technical question directly.`;

/** @type {Map<string, Set<http.ServerResponse>>} */
const listeners = new Map();

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`);
  try {
    if (req.method === 'GET' && (url.pathname === '/' || url.pathname === '/index.html')) {
      return serveStatic(res, 'index.html');
    }
    if (req.method === 'GET' && url.pathname === '/api/health') {
      return json(res, 200, { ok: true, model: MODEL, keyPresent: Boolean(process.env.OPENAI_API_KEY) });
    }
    if (req.method === 'GET' && url.pathname === '/api/sessions') {
      return json(res, 200, { sessions: await listSessions() });
    }
    if (req.method === 'GET' && url.pathname === '/api/history') {
      const session = sessionName(url.searchParams.get('session'));
      return json(res, 200, { session, messages: await readLog(session) });
    }
    if (req.method === 'GET' && url.pathname === '/api/stream') {
      return openStream(req, res, sessionName(url.searchParams.get('session')));
    }
    if (req.method === 'POST' && url.pathname === '/api/ask') {
      return await handleAsk(req, res);
    }
    if (req.method === 'POST' && url.pathname === '/api/note') {
      return await handleNote(req, res);
    }
    if (req.method === 'POST' && url.pathname === '/api/reset') {
      return await handleReset(req, res);
    }
    if (req.method === 'GET' && url.pathname.startsWith('/static/')) {
      return serveStatic(res, url.pathname.slice('/static/'.length));
    }
    json(res, 404, { error: 'not found' });
  } catch (err) {
    json(res, 500, { error: String(err && err.message ? err.message : err) });
  }
});

server.listen(PORT, HOST, () => {
  process.stdout.write(`gpt-bridge listening on http://${HOST}:${PORT}  (model: ${MODEL})\n`);
  if (!process.env.OPENAI_API_KEY) {
    process.stdout.write('warning: OPENAI_API_KEY is not set — /api/ask will fail until it is.\n');
  }
});

// ---------------------------------------------------------------- handlers

async function handleAsk(req, res) {
  const body = await readJsonBody(req);
  const message = String(body.message || '').trim();
  if (!message) return json(res, 400, { error: 'message is required' });
  if (!process.env.OPENAI_API_KEY) return json(res, 503, { error: 'OPENAI_API_KEY is not set on the server' });

  const session = sessionName(body.session);
  const from = body.from === 'user' ? 'user' : 'claude';
  const attachments = await readAttachments(body.files);

  let prompt = message;
  if (attachments.length) {
    const blocks = attachments
      .map((a) => `--- ${a.path} ---\n${a.text}`)
      .join('\n\n');
    prompt = `${message}\n\nFiles from the repository:\n\n${blocks}`;
  }

  await append(session, { role: 'user', from, text: message, files: attachments.map((a) => a.path) });

  const history = (await readLog(session))
    .filter((m) => m.role === 'user' || m.role === 'assistant')
    .slice(-MAX_HISTORY)
    .map((m) => ({ role: m.role, content: m.text }));
  // Replace the just-logged plain message with the attachment-expanded one.
  if (history.length) history[history.length - 1] = { role: 'user', content: prompt };

  let reply;
  try {
    reply = await callOpenAI([{ role: 'system', content: SYSTEM_PROMPT }, ...history], body.model);
  } catch (err) {
    const text = String(err && err.message ? err.message : err);
    await append(session, { role: 'error', from: 'gpt', text });
    return json(res, 502, { error: text });
  }

  const entry = await append(session, { role: 'assistant', from: 'gpt', text: reply.text, model: reply.model, usage: reply.usage });
  json(res, 200, { session, reply: reply.text, model: reply.model, usage: reply.usage, at: entry.at });
}

async function handleNote(req, res) {
  const body = await readJsonBody(req);
  const text = String(body.text || '').trim();
  if (!text) return json(res, 400, { error: 'text is required' });
  const session = sessionName(body.session);
  const entry = await append(session, { role: 'note', from: body.from === 'gpt' ? 'gpt' : body.from === 'user' ? 'user' : 'claude', text });
  json(res, 200, { session, at: entry.at });
}

async function handleReset(req, res) {
  const body = await readJsonBody(req);
  const session = sessionName(body.session);
  await fsp.rm(logPath(session), { force: true });
  broadcast(session, { type: 'reset' });
  json(res, 200, { session, cleared: true });
}

function openStream(req, res, session) {
  res.writeHead(200, {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache, no-transform',
    Connection: 'keep-alive',
  });
  res.write(': connected\n\n');
  const set = listeners.get(session) || new Set();
  set.add(res);
  listeners.set(session, set);
  const ping = setInterval(() => res.write(': ping\n\n'), 25_000);
  req.on('close', () => {
    clearInterval(ping);
    set.delete(res);
  });
}

// ---------------------------------------------------------------- OpenAI

async function callOpenAI(messages, modelOverride) {
  const model = modelOverride || MODEL;
  const res = await fetch(`${API_BASE}/chat/completions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${process.env.OPENAI_API_KEY}`,
    },
    body: JSON.stringify({ model, messages }),
  });
  const raw = await res.text();
  let data;
  try {
    data = JSON.parse(raw);
  } catch {
    throw new Error(`OpenAI returned non-JSON (HTTP ${res.status}): ${raw.slice(0, 400)}`);
  }
  if (!res.ok) {
    const detail = data?.error?.message || raw.slice(0, 400);
    throw new Error(`OpenAI HTTP ${res.status}: ${detail}`);
  }
  const text = data?.choices?.[0]?.message?.content;
  if (!text) throw new Error(`OpenAI response had no message content: ${raw.slice(0, 400)}`);
  return { text, model: data.model || model, usage: data.usage || null };
}

// ---------------------------------------------------------------- storage

function sessionName(name) {
  const cleaned = String(name || 'main').trim().toLowerCase().replace(/[^a-z0-9._-]/g, '-');
  return cleaned.slice(0, 60) || 'main';
}

function logPath(session) {
  return path.join(DATA_DIR, `${session}.jsonl`);
}

async function append(session, entry) {
  const record = { at: new Date().toISOString(), ...entry };
  await fsp.mkdir(DATA_DIR, { recursive: true });
  await fsp.appendFile(logPath(session), `${JSON.stringify(record)}\n`, 'utf8');
  broadcast(session, { type: 'message', message: record });
  return record;
}

async function readLog(session) {
  let raw;
  try {
    raw = await fsp.readFile(logPath(session), 'utf8');
  } catch (err) {
    if (err.code === 'ENOENT') return [];
    throw err;
  }
  return raw
    .split('\n')
    .filter(Boolean)
    .map((line) => {
      try {
        return JSON.parse(line);
      } catch {
        return null;
      }
    })
    .filter(Boolean);
}

async function listSessions() {
  try {
    const names = await fsp.readdir(DATA_DIR);
    return names.filter((n) => n.endsWith('.jsonl')).map((n) => n.slice(0, -'.jsonl'.length)).sort();
  } catch {
    return [];
  }
}

function broadcast(session, payload) {
  const set = listeners.get(session);
  if (!set) return;
  const frame = `data: ${JSON.stringify(payload)}\n\n`;
  for (const res of set) res.write(frame);
}

/** Read repo files to attach, refusing anything outside the repository. */
async function readAttachments(files) {
  if (!Array.isArray(files) || !files.length) return [];
  const out = [];
  for (const rel of files.slice(0, 10)) {
    const abs = path.resolve(REPO_ROOT, String(rel));
    if (abs !== REPO_ROOT && !abs.startsWith(REPO_ROOT + path.sep)) {
      throw new Error(`refusing to read outside the repository: ${rel}`);
    }
    const stat = await fsp.stat(abs);
    if (!stat.isFile()) throw new Error(`not a file: ${rel}`);
    let text = await fsp.readFile(abs, 'utf8');
    if (text.length > MAX_FILE_BYTES) text = `${text.slice(0, MAX_FILE_BYTES)}\n... [truncated]`;
    out.push({ path: path.relative(REPO_ROOT, abs), text });
  }
  return out;
}

// ---------------------------------------------------------------- plumbing

function loadDotEnv(file) {
  let raw;
  try {
    raw = fs.readFileSync(file, 'utf8');
  } catch {
    return;
  }
  for (const line of raw.split('\n')) {
    const m = /^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/.exec(line);
    if (!m || line.trim().startsWith('#')) continue;
    let value = m[2].trim();
    if (/^".*"$/.test(value) || /^'.*'$/.test(value)) value = value.slice(1, -1);
    if (!(m[1] in process.env)) process.env[m[1]] = value;
  }
}

function readJsonBody(req) {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks = [];
    req.on('data', (c) => {
      size += c.length;
      if (size > 2_000_000) {
        reject(new Error('request body too large'));
        req.destroy();
        return;
      }
      chunks.push(c);
    });
    req.on('error', reject);
    req.on('end', () => {
      const text = Buffer.concat(chunks).toString('utf8');
      if (!text.trim()) return resolve({});
      try {
        resolve(JSON.parse(text));
      } catch {
        reject(new Error('body must be JSON'));
      }
    });
  });
}

const MIME = { '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.svg': 'image/svg+xml' };

async function serveStatic(res, rel) {
  const abs = path.resolve(PUBLIC_DIR, rel);
  if (!abs.startsWith(PUBLIC_DIR + path.sep)) return json(res, 403, { error: 'forbidden' });
  try {
    const buf = await fsp.readFile(abs);
    res.writeHead(200, { 'Content-Type': MIME[path.extname(abs)] || 'application/octet-stream' });
    res.end(buf);
  } catch {
    json(res, 404, { error: 'not found' });
  }
}

function json(res, status, payload) {
  const buf = Buffer.from(JSON.stringify(payload));
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Content-Length': buf.length });
  res.end(buf);
}
