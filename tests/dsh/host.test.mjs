// DeepSeek Harness host half, exercised with a stand-in context and a real initialized study.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, realpathSync, rmSync, symlinkSync, writeFileSync, mkdirSync } from 'node:fs';
import { createServer, request } from 'node:http';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { after, before, describe, test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { apply, createRouter, inject } from '../../dsh/host.js';
import { embeddedPolicy, forward, PanelServices } from '../../dsh/panels.js';
import { createSkillProvider, SKILLS } from '../../dsh/skills.js';
import { findPython, inspectStudy, studyId } from '../../dsh/studies.js';

const ROOT = fileURLToPath(new URL('../..', import.meta.url));
const SKILLS_ROOT = join(ROOT, 'plugins/tunetune/skills');
const INIT = join(SKILLS_ROOT, 'research-workspace/scripts/init.py');

function initStudy(base, name) {
  const directory = join(base, name);
  mkdirSync(directory);
  execFileSync('python3', ['-B', INIT, '--project', directory, '--name', name], { stdio: 'ignore' });
  return realpathSync(directory);
}

function listen(handler) {
  return new Promise((resolve) => {
    const server = createServer(handler);
    server.listen(0, '127.0.0.1', () => resolve(server));
  });
}

function call(port, method, path, { headers = {}, body } = {}) {
  return new Promise((resolve, reject) => {
    const req = request({ host: '127.0.0.1', port, method, path, headers: { host: `127.0.0.1:${port}`, ...headers } }, (res) => {
      const chunks = [];
      res.on('data', (chunk) => chunks.push(chunk));
      res.on('end', () => resolve({ status: res.statusCode, headers: res.headers, text: Buffer.concat(chunks).toString('utf8') }));
    });
    req.on('error', reject);
    req.end(body);
  });
}

describe('skills', () => {
  test('the four shipped skills are offered with their own directories', async () => {
    const provider = createSkillProvider(SKILLS_ROOT);
    const listed = await provider.list();
    assert.deepEqual(listed.map((skill) => skill.name).sort(), [...SKILLS].sort());
    for (const skill of listed) {
      assert.equal(skill.source, 'bundled');
      assert.equal(skill.rank, 600);
      assert.equal(skill.resourceBase.path, join(SKILLS_ROOT, skill.name));
      assert.ok(skill.description.length > 20);
    }
    const loaded = await provider.get(listed.find((skill) => skill.name === 'research-workspace'));
    assert.ok(!loaded.content.startsWith('---'));
    assert.equal(loaded.content, readFileSync(join(SKILLS_ROOT, 'research-workspace/SKILL.md'), 'utf8').replace(/^---\n[\s\S]*?\n---\n?/, ''));
    assert.equal(await provider.get({ ...listed[0], locator: '../outside' }), undefined);
  });
});

describe('studies and routes', () => {
  let base;
  let study;
  let plain;
  let panels;
  let server;
  let port;
  let rejection;
  const sessions = new Map();

  before(async () => {
    base = realpathSync(mkdtempSync(join(tmpdir(), 'tunetune-dsh-')));
    study = initStudy(base, 'study');
    plain = join(base, 'plain');
    mkdirSync(plain);
    sessions.set('s-study', { id: 's-study', header: { cwd: study } });
    sessions.set('s-plain', { id: 's-plain', header: { cwd: plain } });
    rejection = undefined;
    const ctx = {
      connection: { requestRejection: () => rejection },
      sessions: { get: (id) => sessions.get(id), list: () => [...sessions.values()] },
      get: () => undefined,
    };
    panels = new PanelServices({ findPython: () => findPython(), idleMs: 60_000 });
    server = await listen(createRouter(ctx, { panels }));
    port = server.address().port;
  });

  after(async () => {
    await panels.stopAll();
    await new Promise((resolve) => server.close(resolve));
    rmSync(base, { recursive: true, force: true });
  });

  test('a study is recognized only from its pinned tools', () => {
    const found = inspectStudy(study);
    assert.equal(found.id, studyId(study));
    assert.equal(found.name, 'study');
    assert.equal(found.embeddable, true);
    assert.equal(inspectStudy(plain), null);
    assert.equal(inspectStudy('relative/path'), null);
    const link = join(base, 'link');
    symlinkSync(study, link);
    assert.equal(inspectStudy(link), null);
  });

  test('sessions report their study without exposing its absolute path', async () => {
    const answer = await call(port, 'GET', '/tunetune/api/sessions/s-study');
    assert.equal(answer.status, 200);
    const value = JSON.parse(answer.text);
    assert.equal(value.study.id, studyId(study));
    assert.equal(value.study.directory, undefined);
    const none = JSON.parse((await call(port, 'GET', '/tunetune/api/sessions/s-plain')).text);
    assert.equal(none.study, null);
    const list = JSON.parse((await call(port, 'GET', '/tunetune/api/studies')).text);
    assert.deepEqual(list.studies.map((item) => [item.id, item.sessions]), [[studyId(study), ['s-study']]]);
  });

  test('the pinned panel is served framed by the same origin', async () => {
    const id = studyId(study);
    const page = await call(port, 'GET', `/tunetune/p/${id}/`);
    assert.equal(page.status, 200);
    assert.match(page.text, /tunetune-panel/);
    assert.match(page.headers['content-security-policy'], /frame-ancestors 'self'/);
    const state = await call(port, 'GET', `/tunetune/p/${id}/api/state`);
    assert.equal(state.status, 200);
    const snapshot = JSON.parse(state.text);
    assert.equal(JSON.parse(JSON.stringify(snapshot.files['project.json'].content)).name, 'study');
  });

  test('writes need the page’s own origin and then reach the pinned service', async () => {
    const id = studyId(study);
    const sha = JSON.parse((await call(port, 'GET', `/tunetune/p/${id}/api/state`)).text).files['project.json'].sha256;
    const body = JSON.stringify({ name: '新名字', expected_sha256: sha });
    const json = { 'content-type': 'application/json', 'content-length': Buffer.byteLength(body) };
    const missing = await call(port, 'POST', `/tunetune/p/${id}/api/project/name`, { headers: json, body });
    assert.equal(missing.status, 403);
    const foreign = await call(port, 'POST', `/tunetune/p/${id}/api/project/name`, { headers: { ...json, origin: 'http://evil.example' }, body });
    assert.equal(foreign.status, 403);
    const saved = await call(port, 'POST', `/tunetune/p/${id}/api/project/name`, { headers: { ...json, origin: `http://127.0.0.1:${port}` }, body });
    assert.equal(saved.status, 200, saved.text);
    assert.equal(JSON.parse(readFileSync(join(study, 'project.json'), 'utf8')).name, '新名字');
  });

  test('requests the harness refuses are refused here too', async () => {
    rejection = 401;
    try {
      for (const path of ['/tunetune/api/studies', `/tunetune/p/${studyId(study)}/api/state`, '/tunetune/ui/']) {
        assert.equal((await call(port, 'GET', path)).status, 401, path);
      }
    } finally {
      rejection = undefined;
    }
  });

  test('unknown studies, traversal and earlier panels are not served', async () => {
    assert.equal((await call(port, 'GET', `/tunetune/p/${'0'.repeat(16)}/api/state`)).status, 404);
    assert.equal((await call(port, 'GET', '/tunetune/ui/../host.js')).status, 404);
    assert.equal((await call(port, 'GET', '/tunetune/ui/%2e%2e/host.js')).status, 404);
    const ui = await call(port, 'GET', '/tunetune/ui/');
    assert.equal(ui.status, 200);
    assert.match(ui.headers['content-security-policy'], /frame-ancestors 'self'/);

    const older = initStudy(base, 'older');
    const index = join(older, '.workspace/app/assets/index.html');
    writeFileSync(index, readFileSync(index, 'utf8').replace(/<meta name="tunetune-panel"[^>]*>/, ''));
    sessions.set('s-older', { id: 's-older', header: { cwd: older } });
    await call(port, 'GET', '/tunetune/api/sessions/s-older');
    const refused = await call(port, 'GET', `/tunetune/p/${studyId(older)}/`);
    assert.equal(refused.status, 409);
    assert.match(JSON.parse(refused.text).command, /workspace\.py/);
  });

  test('studies list their newest conversation first', async () => {
    sessions.set('s-old', { id: 's-old', header: { cwd: study, createdAt: '2026-01-01T00:00:00.000Z' } });
    sessions.set('s-new', { id: 's-new', header: { cwd: study, createdAt: '2026-11-01T00:00:00.000Z' } });
    try {
      const list = JSON.parse((await call(port, 'GET', '/tunetune/api/studies')).text);
      assert.deepEqual(list.studies.find((item) => item.id === studyId(study)).sessions.slice(0, 2), ['s-new', 's-old']);
    } finally {
      sessions.delete('s-old');
      sessions.delete('s-new');
    }
  });

  test('a study stays reachable after its session unloads', async () => {
    sessions.delete('s-study');
    try {
      const list = JSON.parse((await call(port, 'GET', '/tunetune/api/studies')).text);
      assert.ok(list.studies.some((item) => item.id === studyId(study) && item.sessions.length === 0));
    } finally {
      sessions.set('s-study', { id: 's-study', header: { cwd: study } });
    }
  });
});

describe('forwarding', () => {
  test('only panel headers travel upstream and Host and Origin name the loopback service', async () => {
    let seen;
    const upstream = await listen((req, res) => {
      seen = req.headers;
      res.writeHead(200, { 'content-type': 'text/plain', 'set-cookie': 'leak=1', 'content-security-policy': "default-src 'self'; frame-ancestors 'none'" });
      res.end('ok');
    });
    const upstreamPort = upstream.address().port;
    const front = await listen((req, res) => forward(req, res, upstreamPort, '/api/try'));
    try {
      const body = '{}';
      const answer = await call(front.address().port, 'POST', '/x', {
        headers: { 'content-type': 'application/json', 'content-length': '2', cookie: 'dsh=secret', authorization: 'Bearer secret', origin: 'http://harness' },
        body,
      });
      assert.equal(answer.text, 'ok');
      assert.equal(seen.cookie, undefined);
      assert.equal(seen.authorization, undefined);
      assert.equal(seen.host, `127.0.0.1:${upstreamPort}`);
      assert.equal(seen.origin, `http://127.0.0.1:${upstreamPort}`);
      assert.equal(answer.headers['set-cookie'], undefined);
      assert.equal(answer.headers['content-security-policy'], "default-src 'self'; frame-ancestors 'self'");
    } finally {
      await new Promise((resolve) => front.close(resolve));
      await new Promise((resolve) => upstream.close(resolve));
    }
    assert.equal(embeddedPolicy(undefined), undefined);
  });
});

describe('panel processes', () => {
  test('a missing Python is reported and nothing is started', async () => {
    let spawned = false;
    const panels = new PanelServices({ findPython: async () => null, spawnProcess: () => { spawned = true; } });
    await assert.rejects(panels.port({ id: 'a'.repeat(16), directory: '/nowhere', path: '/nowhere' }), { code: 'python-missing' });
    assert.equal(spawned, false);
    assert.equal(panels.running.size, 0);
  });

  test('idle services stop and stopping ends the process', async () => {
    const base = realpathSync(mkdtempSync(join(tmpdir(), 'tunetune-dsh-idle-')));
    try {
      const study = inspectStudy(initStudy(base, 'idle'));
      const panels = new PanelServices({ findPython: () => findPython(), idleMs: 200 });
      const first = await panels.port(study);
      assert.equal(await panels.port(study), first);
      const child = panels.running.get(study.id).child;
      await new Promise((resolve) => child.once('exit', resolve));
      assert.equal(panels.running.size, 0);
      const again = await panels.port(study);
      assert.ok(again > 0);
      await panels.stopAll();
      assert.equal(panels.running.size, 0);
    } finally {
      rmSync(base, { recursive: true, force: true });
    }
  });
});

describe('plugin wiring', () => {
  test('apply registers the skill provider and one prefix route that ends with the plugin', async () => {
    assert.deepEqual(inject, ['webServer', 'connection', 'sessions', 'skills']);
    const effects = [];
    const routes = [];
    let provider;
    const ctx = {
      effect: (fn) => effects.push(fn()),
      skills: { registerProvider: (factory) => { provider = factory(); return () => {}; } },
      webServer: { register: (route) => { routes.push(route); return () => routes.splice(routes.indexOf(route), 1); } },
      connection: { requestRejection: () => undefined },
      sessions: { get: () => undefined, list: () => [] },
      get: () => undefined,
    };
    apply(ctx);
    assert.equal(provider.name, 'tunetune');
    assert.deepEqual(routes.map((route) => [route.kind, route.path]), [['prefix', '/tunetune']]);
    for (const dispose of effects) if (typeof dispose === 'function') dispose();
    assert.equal(routes.length, 0);
  });
});
