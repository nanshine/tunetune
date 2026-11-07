// Run each study's own pinned panel service and forward browser requests to it.
// The study keeps the tools that initialized it, so newer plugin versions never change
// how an existing study is read, validated or written.
import { spawn } from 'node:child_process';
import { request } from 'node:http';
import { join } from 'node:path';

const START_TIMEOUT_MS = 20_000;
const STOP_GRACE_MS = 5_000;
const LOG_TAIL = 4_000;
// Only what the panel needs travels upstream; DeepSeek Harness cookies and credentials stay here.
const FORWARD_REQUEST = ['accept', 'content-type', 'content-length'];
const FORWARD_RESPONSE = ['content-type', 'content-length', 'cache-control', 'x-content-type-options', 'referrer-policy'];

export class PanelServices {
  constructor({ findPython, idleMs = 15 * 60_000, spawnProcess = spawn, log = () => {}, platform = process.platform }) {
    this.findPython = findPython;
    this.platform = platform;
    this.idleMs = idleMs;
    this.spawnProcess = spawnProcess;
    this.log = log;
    this.running = new Map();
  }

  // Resolve the loopback port of a study's panel service, starting it on first use.
  // A service opened in a separate browser tab sees no requests here, so it must not idle out.
  async port(study, { keep = false } = {}) {
    let entry = this.running.get(study.id);
    if (!entry) {
      entry = { pending: this.start(study), child: null, timer: null, keep: false };
      this.running.set(study.id, entry);
      entry.pending.catch(() => {
        if (this.running.get(study.id) === entry) this.running.delete(study.id);
      });
    }
    if (keep) entry.keep = true;
    const port = await entry.pending;
    this.touch(study.id);
    return port;
  }

  touch(id) {
    const entry = this.running.get(id);
    if (!entry) return;
    clearTimeout(entry.timer);
    if (entry.keep) return;
    entry.timer = setTimeout(() => this.stop(id), this.idleMs);
    entry.timer.unref?.();
  }

  async start(study) {
    // The pinned tools refuse native Windows; studies there live inside WSL2 instead.
    if (this.platform === 'win32') throw Object.assign(new Error('TuneTune needs WSL2 on Windows'), { code: 'windows-host' });
    const python = await this.findPython();
    if (!python) throw Object.assign(new Error('Python 3.10 or newer was not found'), { code: 'python-missing' });
    const entry = this.running.get(study.id);
    // Stopped while Python was being located: start nothing that nobody will stop.
    if (!entry || entry.child) throw Object.assign(new Error('The research panel was stopped'), { code: 'panel-failed' });
    const script = join(study.directory, '.workspace', 'app', 'workspace.py');
    // -B keeps bytecode caches out of the study; workspace.py binds 127.0.0.1 only.
    const child = this.spawnProcess(python, ['-B', script, '--project', study.directory, '--port', '0'], {
      cwd: study.directory,
      stdio: ['ignore', 'pipe', 'pipe'],
      env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' },
    });
    entry.child = child;
    let stdout = '';
    let stderr = '';
    child.stderr.on('data', (chunk) => { stderr = (stderr + chunk).slice(-LOG_TAIL); });
    return new Promise((resolve, reject) => {
      const fail = (message) => {
        clearTimeout(timer);
        child.kill('SIGTERM');
        reject(Object.assign(new Error(message), { code: 'panel-failed', detail: stderr.trim() }));
      };
      const timer = setTimeout(() => fail('The research panel did not start in time'), START_TIMEOUT_MS);
      child.stdout.on('data', (chunk) => {
        stdout += chunk;
        const match = stdout.match(/^http:\/\/127\.0\.0\.1:(\d+)\r?\n/);
        if (match) {
          clearTimeout(timer);
          child.stdout.removeAllListeners('data');
          child.stdout.resume();
          resolve(Number(match[1]));
        } else if (stdout.length > 1024) {
          fail('The research panel printed an unexpected address');
        }
      });
      child.on('error', (error) => fail(error.message));
      child.on('exit', (code, signal) => {
        clearTimeout(timer);
        const current = this.running.get(study.id);
        if (current?.child === child) {
          clearTimeout(current.timer);
          this.running.delete(study.id);
        }
        this.log(`panel for ${study.path} exited (${signal ?? code})`);
        reject(Object.assign(new Error('The research panel stopped'), { code: 'panel-failed', detail: stderr.trim() }));
      });
    });
  }

  // SIGTERM lets workspace.py unload resident models before it exits.
  stop(id) {
    const entry = this.running.get(id);
    if (!entry) return Promise.resolve();
    this.running.delete(id);
    clearTimeout(entry.timer);
    const child = entry.child;
    if (!child || child.exitCode !== null || child.signalCode !== null) return Promise.resolve();
    return new Promise((resolve) => {
      const force = setTimeout(() => child.kill('SIGKILL'), STOP_GRACE_MS);
      force.unref?.();
      child.once('exit', () => { clearTimeout(force); resolve(); });
      child.kill('SIGTERM');
    });
  }

  stopAll() {
    return Promise.all([...this.running.keys()].map((id) => this.stop(id)));
  }
}

// The panel forbids framing by default; inside DeepSeek Harness it is framed by the same origin.
export function embeddedPolicy(value) {
  if (typeof value !== 'string') return undefined;
  return value.replace(/frame-ancestors\s+'none'/, "frame-ancestors 'self'");
}

// Forward one request to the panel service on 127.0.0.1:port, rewriting only Host and Origin,
// which workspace.py checks against its own loopback address.
export function forward(req, res, port, path) {
  return new Promise((resolve) => {
    const headers = { host: `127.0.0.1:${port}` };
    for (const name of FORWARD_REQUEST) if (req.headers[name] !== undefined) headers[name] = req.headers[name];
    if (req.method === 'POST') headers.origin = `http://127.0.0.1:${port}`;
    const upstream = request({ host: '127.0.0.1', port, method: req.method, path, headers }, (answer) => {
      const out = {};
      for (const name of FORWARD_RESPONSE) if (answer.headers[name] !== undefined) out[name] = answer.headers[name];
      const policy = embeddedPolicy(answer.headers['content-security-policy']);
      if (policy) out['content-security-policy'] = policy;
      res.writeHead(answer.statusCode ?? 502, out);
      answer.pipe(res);
      answer.on('end', resolve);
      answer.on('error', resolve);
    });
    upstream.on('error', () => {
      if (!res.headersSent) {
        res.writeHead(502, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' });
        res.end(JSON.stringify({ error: 'The research panel is not reachable' }));
      } else {
        res.destroy();
      }
      resolve();
    });
    req.pipe(upstream);
  });
}
