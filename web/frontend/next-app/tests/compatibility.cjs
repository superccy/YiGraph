const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const ts = require('typescript')
const root = path.resolve(__dirname, '..')

// Load adapters without mounting React or contacting a real analysis service.
function adapters() {
  const cache = new Map()
  const handlers = new Map()
  const outgoing = []
  const socket = { connected: true, on: (name, callback) => handlers.set(name, callback), emit: (...args) => outgoing.push(args) }
  function load(filename) {
    filename = path.resolve(filename)
    if (cache.has(filename)) return cache.get(filename).exports
    const module = { exports: {} }
    cache.set(filename, module)
    const result = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    })
    const localRequire = (name) => {
      if (name === 'socket.io-client') return { io: () => socket }
      if (name.startsWith('@/')) return load(path.join(root, name.slice(2)) + '.ts')
      if (name.startsWith('.')) return load(path.resolve(path.dirname(filename), name) + '.ts')
      return require(name)
    }
    new Function('require', 'module', 'exports', result.outputText)(localRequire, module, module.exports)
    return module.exports
  }
  return { load: (name) => load(path.join(root, name)), handlers, outgoing, socket }
}

test('paper DAG retains first task, independent nodes, IDs and all returned dependencies', () => {
  const { load } = adapters()
  const adapter = load('core/chat-adapter.ts')
  const nodes = [{ id: 3, label: '用户问题中的关键节点', tasktype: 'Graph Algorithm (pagerank)' }, { id: 9, label: 'Second task', tasktype: 'Numeric Analysis' }]
  const independent = adapter.convertOldDagToPlan({ nodes, edges: [] }, '', [])
  assert.equal(independent.nodes.length, 2)
  assert.equal(independent.nodes[0].label, nodes[0].label)
  assert.deepEqual(independent.edges, [])
  const connected = adapter.convertOldDagToPlan({ nodes, edges: [{ from: 9, to: 3 }] }, '', [])
  assert.deepEqual(connected.edges, [{ id: 'e-0', source: 'n-2', target: 'n-1' }])
})

test('paper code events and error envelopes remain visible', () => {
  const adapter = adapters().load('core/chat-adapter.ts')
  const state = adapter.createAdapterState()
  const event = adapter.processChatEvent({ type: 'result', contentType: 'code', content: { language: 'python', code: 'print(42)' } }, state)
  assert.equal(event.text, '```python\nprint(42)\n```')
  assert.equal(adapter.processChatEvent({ error: 'Analysis failed' }, state).message, 'Analysis failed')
  assert.equal(state.finished, true)
})

test('clarification stays separate from reports and survives the end of the message stream', () => {
  const adapter = adapters().load('core/chat-adapter.ts')
  const state = adapter.createAdapterState()
  const clarification = { clarification_id: 'opaque-id', question: 'Which anomaly criterion?', missing_fields: ['criteria'] }
  assert.deepEqual(adapter.processChatEvent({ type: 'result', contentType: 'clarification', content: clarification }, state), { kind: 'clarification', clarification })
  adapter.processChatEvent({ type: 'stream_end' }, state)
  assert.equal(state.clarification.clarification_id, 'opaque-id')
  assert.equal(state.dag, null)
  assert.deepEqual(state.resultParagraphs, [])
  assert.equal(adapter.processChatEvent({ type: 'result', contentType: 'intent_ready' }, state).kind, 'intent_ready')
  assert.equal(state.clarification, null)
  assert.equal(adapter.processChatEvent({ error: 'Expired', restart_required: true }, state).restartRequired, true)
})

test('Socket.IO keeps the paper payload, blocks overlap/stale plans, never replays after disconnect', () => {
  const { load, handlers, outgoing, socket } = adapters()
  const chat = load('core/api/chat.ts')
  const events = []
  const payload = { model: 'paper-model', dataset: 'paper-data', mode: 'interact', message: 'Question', dag_id: 'current-plan' }
  chat.sendChatRequest(payload, (event) => events.push(event))
  assert.deepEqual(outgoing, [['chat_request', payload]])
  chat.sendChatRequest(payload, (event) => events.push(event))
  assert.equal(outgoing.length, 1)
  assert.match(events.at(-1).error, /already running/)
  handlers.get('chat_response')({ type: 'stream_end' })
  chat.sendChatRequest({ ...payload, dag_confirm: 'yes', dag_id: 'stale' }, (event) => events.push(event))
  assert.equal(outgoing.length, 1)
  chat.sendChatRequest({ ...payload, dag_confirm: 'yes' }, (event) => events.push(event))
  assert.equal(outgoing.length, 2)
  socket.connected = false
  handlers.get('disconnect')()
  assert.match(events.at(-1).error, /interrupted/)
  socket.connected = true
  assert.equal(chat.isChatBusy(), false)
  assert.equal(chat.isCurrentDag('current-plan'), false)
  assert.equal(outgoing.length, 2)
})

test('create dataset reads the backend record rather than making a timestamp ID', async () => {
  const previousFetch = global.fetch
  try {
    const requests = []
    global.fetch = async (url, options) => {
      requests.push([url, options])
      return { json: async () => options?.method === 'POST'
        ? { success: true, data: { db_name: 'new-data' } }
        : { success: true, data: [{ id: 17, name: 'new-data', file_type: 'graph', file_count: 0, created_at: '2026-10-10' }] } }
    }
    const api = adapters().load('core/api/datasets.ts')
    assert.equal((await api.createDataset({ name: 'new-data', fileType: 'graph-data' })).id, '17')
    assert.equal(requests.length, 2)
  } finally { global.fetch = previousFetch }
})

test('graph upload uses the existing vertex/edge batch schema and rejects incomplete inputs', async () => {
  const previousFetch = global.fetch
  try {
    const requests = []
    global.fetch = async (url, options) => {
      requests.push([url, options])
      return { json: async () => ({ success: true }) }
    }
    const api = adapters().load('core/api/files.ts')
    const vertex = new File(['id,name\n1,A'], 'vertices.csv')
    const edge = new File(['source,target\n1,2'], 'edges.csv')
    const config = { graphName: 'graph', vertexFileName: vertex.name, edgeFileName: edge.name, vertexIdField: 'id', vertexLabelField: 'name', edgeSourceField: 'source', edgeTargetField: 'target', directed: false }
    await api.uploadFiles('17', [vertex, edge], 'graph', config)
    const body = requests[0][1].body
    assert.equal(body.get('kb_id'), '17')
    assert.equal(body.get('is_batch_upload'), 'true')
    assert.deepEqual(body.getAll('files').map((file) => file.name), ['vertices.csv', 'edges.csv'])
    const schema = JSON.parse(body.get('graph_info'))
    assert.equal(schema.vertexSchema.idField, 'id')
    assert.equal(schema.vertexSchema.fileName, 'vertices.csv')
    assert.equal(schema.edgeSchema.fileName, 'edges.csv')
    assert.equal(schema.graphProperties.isDirected, false)
    await assert.rejects(api.uploadFiles('17', [vertex, edge], 'graph', {}))
    assert.equal(requests.length, 1)
  } finally { global.fetch = previousFetch }
})

test('file previews preserve PDF/HTML content and parsing failures stay failures', async () => {
  const previousFetch = global.fetch
  try {
    const api = adapters().load('core/api/files.ts')
    global.fetch = async () => ({ json: async () => ({ success: true, content_type: 'html', content: '<p>Document</p>' }) })
    assert.deepEqual(await api.previewFile('17', 'document.docx'), { type: 'html', content: '<p>Document</p>' })
    global.fetch = async () => ({ json: async () => ({ success: true, file_status: { 'broken.txt': ['failed', 0.2] } }) })
    assert.equal((await api.getParseStatus('17'))['broken.txt'].status, 'error')
  } finally { global.fetch = previousFetch }
})

test('health probing checks the actual response instead of treating every HTTP response as online', async () => {
  const previousFetch = global.fetch
  try {
    const api = adapters().load('core/api/base.ts')
    global.fetch = async () => ({ ok: true, json: async () => ({ status: 'unhealthy' }) })
    assert.equal(await api.probeBackend(), null)
    global.fetch = async () => ({ ok: true, json: async () => ({ status: 'healthy' }) })
    assert.equal(await api.probeBackend(), '')
  } finally { global.fetch = previousFetch }
})
