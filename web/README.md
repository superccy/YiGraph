# YiGraph paper repository: v2 Web interface

The interface is adapted from `YiGraph-dev` commit
`ee66a109e6b57b78356f4958a4f1c8e498990bb9`. The paper's `aag`, configuration,
experiment code, data, model settings and Python dependencies are retained.

## Build and run

Use Node >=20.9 for the frontend, and the paper's existing Python environment
for the backend. On node2, Node 22 is available in the `yigraph-web` environment.

```bash
cd /home/wangzh/projects/paper-code-web2.0/YiGraph/web/frontend/next-app
export PATH=/home/wangzh/miniconda3/envs/yigraph-web/bin:$PATH
npm ci
npm run typecheck
npm test
npm run build

# In the existing paper Python environment, from the repository root:
cd /home/wangzh/projects/paper-code-web2.0/YiGraph
python web/frontend/run.py
```

The original launcher chooses a free port starting at 5089. Open that port on
node2 or forward it through SSH. Flask serves the static `next-app/out` export;
no Next.js server is required in production. Build output and dependencies are
ignored by Git. Direct routes include `/`, `/datasets`, `/files`, `/models`, and
`/algorithms`. Existing page URLs redirect to their matching v2 pages.

For a separate Next development server, configure the backend explicitly:

```bash
NEXT_PUBLIC_BACKEND_URL=http://<node2-host>:<backend-port> npm run dev
```

Use an HTTPS URL when the frontend is served over HTTPS. Production builds
should leave `NEXT_PUBLIC_BACKEND_URL` unset to use the same origin.

## Compatibility

### Clarify intent before starting a new Web analysis

The v2 Web request handler now checks the analysis object, objective and decision
criteria with the existing configured LLM before calling the paper analysis
service. An incomplete request returns a clarification question and constructs
no new DAG. A reply is associated with its original request using a server-issued
`clarification_id` and `conversation_id`; its original dataset and mode are kept.
Partial answers trigger another question. Explicit computations such as node count
or PageRank do not require an unrelated decision threshold.

The checker validates its structured response and supporting excerpts. Decision
criteria must quote user input; malformed responses or LLM failures stop the request.
The original request and all clarification replies are passed to the existing
analysis service without generating a replacement business rule in the Web layer.
While waiting, the page keeps the input available and does not show a DAG or report.
Confirmation/modification requests cannot bypass a pending clarification. Replies
are sent only to the originating Socket.IO client, and the shared paper engine's
Web requests are serialized.

Pending clarification is in memory, bound to the Socket.IO client and conversation,
and expires after 30 minutes. Reconnecting, restarting the backend, or expiration
requires resubmitting the complete request. Other API/CLI entry points and the
paper's existing query rewriting, algorithm selection, DAG editing and execution
remain unchanged. This feature does not establish a system-wide guarantee that
the legacy query rewriter preserves every confirmed business definition.

Run the independent intent-gate tests without initializing the engine:

```bash
python -m unittest discover -s web/tests -v
```

See `demo/README.md` for a short reproduction scenario and the existing video.

- Chat uses the paper backend's existing Socket.IO `chat_request` and
  `chat_response` events. It does not introduce the development branch's
  HTTP chat service or alter the core engine.
- One analysis can run at a time in the frontend. A plan is confirmed or
  modified using its original dataset and model settings. A disconnected or
  superseded plan must be generated again. The paper backend still has shared
  engine state; use one active analysis client per backend instance.
- DAG rendering preserves all returned nodes and edges. Dragging updates only
  the saved visual coordinates. Per-node details absent from the paper protocol
  are marked as unavailable rather than synthesized.
- Dataset and file IDs come from refreshed backend records. Graph upload uses
  the existing single-edge or vertex/edge batch protocol, including schema and
  directedness settings. Parsing calls the existing implementation unchanged.
- Algorithms are read-only views of the paper's existing YAML knowledge base.
  Adding or overwriting algorithms is disabled. Metadata stays in its original
  language; missing fields are left empty.
- Page feedback is stored in `next-app/feedback.json`, separate from paper
  data and algorithm configuration.
- Only TXT/Markdown preview compatibility is added to the existing file route.
  Model selection, parsing parameters, prompts and core service behavior remain
  unchanged. The original model management API is retained.

## Return to v1

The original templates and static assets are retained. Set
`YIGRAPH_WEB_VERSION=1` when starting the original launcher to use v1 pages.
If no v2 export has been built, original pages are served automatically.
