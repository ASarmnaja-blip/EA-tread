#!/usr/bin/env node
// Ask GPT a question through a running gpt-bridge server and print the reply.
//
//   node tools/gpt-bridge/ask.mjs "why does the 3-leg exit lag on gold?"
//   node tools/gpt-bridge/ask.mjs -f MQL5/Experts/Dobby.mq5 "review the risk sizing"
//   node tools/gpt-bridge/ask.mjs --session exits --history
//
// Anything posted here also shows up live in the browser, so a human can read
// the exchange without being in the middle of it.

const args = process.argv.slice(2);
const opts = { files: [], session: 'main', base: process.env.GPT_BRIDGE_URL || 'http://127.0.0.1:8787' };
const words = [];

for (let i = 0; i < args.length; i++) {
  const a = args[i];
  if (a === '-f' || a === '--file') opts.files.push(args[++i]);
  else if (a === '-s' || a === '--session') opts.session = args[++i];
  else if (a === '-m' || a === '--model') opts.model = args[++i];
  else if (a === '--url') opts.base = args[++i];
  else if (a === '--history') opts.history = true;
  else if (a === '--note') opts.note = true;
  else if (a === '--reset') opts.reset = true;
  else if (a === '-h' || a === '--help') opts.help = true;
  else words.push(a);
}

const message = words.join(' ').trim();

if (opts.help || (!message && !opts.history && !opts.reset)) {
  process.stdout.write(`usage: ask.mjs [options] <message>

  -f, --file <path>     attach a repo file to the question (repeatable)
  -s, --session <name>  conversation to use (default: main)
  -m, --model <id>      override the server's model for this question
      --note            record the message in the log without asking GPT
      --history         print the conversation and exit
      --reset           clear the conversation
      --url <base>      bridge server URL (default: http://127.0.0.1:8787)
`);
  process.exit(opts.help ? 0 : 1);
}

try {
  if (opts.reset) {
    await post('/api/reset', { session: opts.session });
    process.stdout.write(`cleared session "${opts.session}"\n`);
    if (!message && !opts.history) process.exit(0);
  }
  if (opts.history) {
    const { messages } = await get(`/api/history?session=${encodeURIComponent(opts.session)}`);
    for (const m of messages) {
      process.stdout.write(`\n[${m.at}] ${(m.from || m.role).toUpperCase()}\n${m.text}\n`);
    }
    process.exit(0);
  }
  if (opts.note) {
    await post('/api/note', { session: opts.session, text: message });
    process.exit(0);
  }
  const body = { message, session: opts.session, files: opts.files, from: 'claude' };
  if (opts.model) body.model = opts.model;
  const out = await post('/api/ask', body);
  process.stdout.write(`${out.reply}\n`);
  if (out.usage) {
    process.stderr.write(`\n[${out.model} · ${out.usage.prompt_tokens}+${out.usage.completion_tokens} tokens]\n`);
  }
} catch (err) {
  process.stderr.write(`ask.mjs: ${err.message}\n`);
  process.exit(1);
}

async function post(route, body) {
  return request(route, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
}

async function get(route) {
  return request(route, {});
}

async function request(route, init) {
  let res;
  try {
    res = await fetch(opts.base + route, init);
  } catch (err) {
    throw new Error(`cannot reach the bridge at ${opts.base} — is the server running? (${err.message})`);
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}
