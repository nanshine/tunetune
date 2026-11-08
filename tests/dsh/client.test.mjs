// DeepSeek Harness browser half: the right-sidebar tab opens by itself, with a stand-in harness context.
import assert from 'node:assert/strict';
import { afterEach, beforeEach, describe, mock, test } from 'node:test';

const CLIENT = new URL('../../dsh/client.js', import.meta.url);
let loads = 0;

async function loadPlugin() {
  let definition;
  globalThis.window = { __ModuleLoader__: { load: (value) => { definition = value; } } };
  await import(`${CLIENT.href}?load=${loads++}`);
  const react = { createElement: () => null, useRef: () => ({}), useState: (value) => [value()], useEffect: () => {} };
  return definition.factory((name) => { assert.equal(name, 'react'); return react; });
}

function observable(value) {
  const listeners = new Set();
  return {
    getSnapshot: () => value,
    subscribe: (listener) => { listeners.add(listener); return () => listeners.delete(listener); },
    set(next) { value = next; for (const listener of [...listeners]) listener(); },
    get listeners() { return listeners.size; },
  };
}

// Services the plugin asks for; each `inject` runs at once and keeps its disposer.
function harness(sidebar) {
  const disposers = [];
  const services = { sidebarRight: sidebar, sidebarRightTabs: { register: () => () => {} } };
  const slots = { inject: (_name, fn) => fn(), register: () => () => {} };
  const ctx = {
    slots,
    uiWorkspace: { openSession: () => {} },
    inject(names, fn) {
      if (!names.every((name) => name in services)) return;
      const dispose = fn({ ...services, slots, on: () => {} });
      if (typeof dispose === 'function') disposers.push(dispose);
    },
  };
  return { ctx, dispose: () => { for (const dispose of disposers.splice(0)) dispose(); } };
}

async function settle() {
  for (let i = 0; i < 5; i += 1) await new Promise((resolve) => setImmediate(resolve));
}

describe('automatic right-sidebar opening', () => {
  let studies;
  let requests;
  let sidebar;
  let plugin;
  let running;

  beforeEach(async () => {
    mock.timers.enable({ apis: ['setInterval'] });
    const memory = new Map();
    globalThis.location = { origin: 'http://harness.test' };
    globalThis.sessionStorage = {
      getItem: (key) => (memory.has(key) ? memory.get(key) : null),
      setItem: (key, value) => { memory.set(key, String(value)); },
    };
    studies = new Map();
    requests = [];
    globalThis.fetch = async (path) => {
      requests.push(path);
      const id = decodeURIComponent(path.split('/').pop());
      return { ok: true, json: async () => ({ session: id, study: studies.get(id) ?? null }) };
    };
    sidebar = { mounted: observable(undefined), opened: [], openTab(kind) { this.opened.push(kind); } };
    plugin = await loadPlugin();
    running = harness(sidebar);
    plugin.apply(running.ctx);
  });

  afterEach(() => {
    running.dispose();
    mock.timers.reset();
    delete globalThis.window;
    delete globalThis.location;
    delete globalThis.sessionStorage;
    delete globalThis.fetch;
  });

  const study = (fields = {}) => ({ id: 'a1b2c3d4e5f60718', embeddable: true, attention: null, ...fields });

  test('a conversation holding a study opens its tab once, and closing it is respected', async () => {
    studies.set('s1', study());
    sidebar.mounted.set('s1');
    await settle();
    assert.deepEqual(sidebar.opened, ['dsh-tunetune']);
    assert.equal(requests[0], '/tunetune/api/sessions/s1');
    mock.timers.tick(4000);
    await settle();
    assert.deepEqual(sidebar.opened, ['dsh-tunetune']);
  });

  test('a study initialized during the conversation opens on a later poll', async () => {
    sidebar.mounted.set('s1');
    await settle();
    assert.deepEqual(sidebar.opened, []);
    studies.set('s1', study());
    mock.timers.tick(4000);
    await settle();
    assert.deepEqual(sidebar.opened, ['dsh-tunetune']);
  });

  test('each new attention request opens it again; the same or cleared request does not', async () => {
    studies.set('s1', study({ attention: '3' }));
    sidebar.mounted.set('s1');
    await settle();
    assert.equal(sidebar.opened.length, 1);
    mock.timers.tick(4000);
    await settle();
    assert.equal(sidebar.opened.length, 1);
    studies.set('s1', study({ attention: null }));
    mock.timers.tick(4000);
    await settle();
    assert.equal(sidebar.opened.length, 1);
    studies.set('s1', study({ attention: '5' }));
    mock.timers.tick(4000);
    await settle();
    assert.equal(sidebar.opened.length, 2);
  });

  test('earlier panels, plain folders and conversations no longer on screen are left alone', async () => {
    studies.set('old', study({ embeddable: false }));
    sidebar.mounted.set('old');
    await settle();
    sidebar.mounted.set('plain');
    await settle();
    assert.deepEqual(sidebar.opened, []);
    studies.set('s2', study());
    let release;
    const gate = new Promise((resolve) => { release = resolve; });
    const respond = globalThis.fetch;
    globalThis.fetch = async (path) => { await gate; return respond(path); };
    sidebar.mounted.set('s2');
    sidebar.mounted.set(undefined);
    release();
    await settle();
    assert.deepEqual(sidebar.opened, []);
  });

  test('a reload remembers what was opened, and unloading stops watching', async () => {
    studies.set('s1', study({ attention: '2' }));
    sidebar.mounted.set('s1');
    await settle();
    running.dispose();
    assert.equal(sidebar.mounted.listeners, 0);
    running = harness(sidebar);
    plugin.apply(running.ctx);
    await settle();
    assert.equal(sidebar.opened.length, 1);
    const before = requests.length;
    running.dispose();
    mock.timers.tick(8000);
    await settle();
    assert.equal(requests.length, before);
  });
});
