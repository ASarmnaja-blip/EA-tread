# GPT bridge

A small local web app that lets **Claude and GPT talk to each other directly** about
this project, with a browser window showing the exchange live.

- Claude (or any agent with a shell) posts questions with `ask.mjs`.
- GPT's answers land in the same conversation.
- The web page at `http://127.0.0.1:8787` follows along over SSE, and you can type
  into the same conversation whenever you want to steer it.

GPT is given a system prompt describing this repository (MQL5 EAs, Pine scripts,
Python backtests) so answers stay on the trading/EA topic.

No dependencies — Node 18+ and the standard library only.

## Setup

```bash
cp tools/gpt-bridge/.env.example tools/gpt-bridge/.env
# edit .env and paste your OpenAI API key
node tools/gpt-bridge/server.mjs
```

Then open <http://127.0.0.1:8787>.

The key stays on the server and is never sent to the browser. The server binds to
`127.0.0.1`, so it is not reachable from other machines; set `HOST=0.0.0.0` only if
you understand that exposes an unauthenticated endpoint that spends your API credit.

## Asking from the command line

```bash
# plain question
node tools/gpt-bridge/ask.mjs "does the 3-leg exit repaint on the Pine version?"

# with repo files attached as context
node tools/gpt-bridge/ask.mjs -f pine/Dobby_3Leg_Strategy.pine \
  "review the exit structure for look-ahead bias"

# keep separate threads
node tools/gpt-bridge/ask.mjs -s exits "..."
node tools/gpt-bridge/ask.mjs -s exits --history
node tools/gpt-bridge/ask.mjs -s exits --reset
```

Only files inside the repository can be attached; each is truncated at 200 KB.

## HTTP API

| Method | Route | Body / query | Purpose |
| --- | --- | --- | --- |
| POST | `/api/ask` | `{message, session?, files?, model?, from?}` | ask GPT, log both sides |
| POST | `/api/note` | `{text, session?, from?}` | add a message to the log without calling GPT |
| POST | `/api/reset` | `{session?}` | clear a conversation |
| GET | `/api/history` | `?session=` | full conversation as JSON |
| GET | `/api/sessions` | — | known conversation names |
| GET | `/api/stream` | `?session=` | SSE feed of new messages |
| GET | `/api/health` | — | model in use, whether a key is configured |

Transcripts are JSONL under `tools/gpt-bridge/data/` (gitignored), one file per
session — readable directly if you want to diff or archive a discussion.
