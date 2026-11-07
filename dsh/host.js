// TuneTune for DeepSeek Harness: the Host half.
//   - registers the four TuneTune skills with ctx.skills
//   - /tunetune/ui/                 the frame page shown in the main area and the right sidebar
//   - /tunetune/api/studies         studies found in the working directories of loaded sessions
//   - /tunetune/api/sessions/<id>   the study in one session's working directory, if any
//   - /tunetune/p/<study>/…         the study's own pinned panel service, started on demand
//   - POST /tunetune/api/studies/<study>/browser  the same service for a separate browser tab,
//                                   the only way to show panels from tools that predate the plugin
// Every route sits behind DeepSeek Harness's connection checks: the panel shows private research
// and can load local models, so it must never answer requests the harness itself would refuse.
import { createReadStream, realpathSync, statSync } from 'node:fs';
import { extname, join, normalize, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { forward, PanelServices } from './panels.js';
import { createSkillProvider, shadowingSkills } from './skills.js';
import { findPython, inspectStudy } from './studies.js';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const SKILLS_ROOT = join(ROOT, 'plugins', 'tunetune', 'skills');
const UI_ROOT = join(ROOT, 'dsh', 'ui');
const BASE = '/tunetune';
const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml' };
const UI_POLICY = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
  + "frame-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'self'; form-action 'none'";

export const name = 'tunetune';
export const inject = ['webServer', 'connection', 'sessions', 'skills'];

function sendJson(res, status, body) {
  res.writeHead(status, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store', 'x-content-type-options': 'nosniff' });
  res.end(JSON.stringify(body));
}

function serveUi(req, res, relative) {
  if (relative.split('/').some((part) => !part || part.startsWith('.'))) return sendJson(res, 404, { error: 'Not found' });
  let file;
  try {
    const base = realpathSync(UI_ROOT);
    file = realpathSync(normalize(join(base, relative)));
    if (!file.startsWith(base + sep) || !statSync(file).isFile() || !MIME[extname(file)]) return sendJson(res, 404, { error: 'Not found' });
  } catch {
    return sendJson(res, 404, { error: 'Not found' });
  }
  res.writeHead(200, { 'content-type': MIME[extname(file)], 'cache-control': 'no-cache', 'x-content-type-options': 'nosniff', 'content-security-policy': UI_POLICY });
  if (req.method === 'HEAD') return res.end();
  createReadStream(file).pipe(res);
}

// A browser POST must come from the page the harness served: no Origin, no write.
function sameOrigin(req) {
  const origin = req.headers.origin;
  if (typeof origin !== 'string') return false;
  try {
    return new URL(origin).host === req.headers.host;
  } catch {
    return false;
  }
}

function sessionDirectory(ctx, session) {
  try {
    // Optional service: compositions without it still record the session's original directory.
    const directory = ctx.get?.('workingDirectory')?.get(session);
    if (typeof directory === 'string') return directory;
  } catch { /* fall back to the directory the session was created in */ }
  return session?.header?.cwd;
}

function publicStudy(study) {
  if (!study) return null;
  const { directory, ...shown } = study;
  return shown;
}

export function createRouter(ctx, { panels, findStudy = inspectStudy, shadowed = () => shadowingSkills(SKILLS_ROOT) } = {}) {
  // Studies stay reachable for the life of the process once a session has shown them.
  const known = new Map();
  const remember = (study) => {
    if (study) known.set(study.id, study.directory);
    return study;
  };
  const studyOfSession = (id) => {
    const session = ctx.sessions.get(id);
    return session ? remember(findStudy(sessionDirectory(ctx, session))) : null;
  };
  const studies = () => {
    const found = new Map();
    // Newest first, so "go to conversation" lands on the latest one.
    const created = (session) => String(session?.header?.createdAt ?? '');
    for (const session of [...ctx.sessions.list()].sort((a, b) => created(b).localeCompare(created(a)))) {
      const study = remember(findStudy(sessionDirectory(ctx, session)));
      if (!study) continue;
      const entry = found.get(study.id) ?? { ...publicStudy(study), sessions: [] };
      entry.sessions.push(String(session.id));
      found.set(study.id, entry);
    }
    for (const [id, directory] of known) {
      if (found.has(id)) continue;
      const study = findStudy(directory);
      if (study?.id === id) found.set(id, { ...publicStudy(study), sessions: [] });
      else known.delete(id);
    }
    return [...found.values()];
  };

  return async function handle(req, res) {
    const rejection = ctx.connection.requestRejection(req);
    if (rejection) return sendJson(res, rejection, { error: 'Not authorized' });
    let url;
    try {
      url = new URL(req.url || '/', 'http://localhost');
    } catch {
      return sendJson(res, 400, { error: 'Invalid request' });
    }
    const rest = url.pathname.slice(BASE.length) || '/';
    const reading = req.method === 'GET' || req.method === 'HEAD';
    if (!reading && !(req.method === 'POST' && sameOrigin(req))) return sendJson(res, 403, { error: 'Same origin required' });

    let match;
    if ((match = rest.match(/^\/p\/([0-9a-f]{16})(\/.*)?$/))) {
      if (!match[2]) {
        res.writeHead(308, { location: `${BASE}/p/${match[1]}/${url.search}` });
        return res.end();
      }
      const directory = known.get(match[1]);
      const study = directory ? findStudy(directory) : null;
      if (!study || study.id !== match[1]) return sendJson(res, 404, { error: 'Study not found' });
      if (!study.embeddable) return sendJson(res, 409, { error: 'This study uses an earlier panel', command: study.command });
      let port;
      try {
        port = await panels.port(study);
      } catch (error) {
        return sendJson(res, 503, { error: error.message, code: error.code, detail: error.detail });
      }
      return forward(req, res, port, `${match[2]}${url.search}`);
    }
    if ((match = rest.match(/^\/api\/studies\/([0-9a-f]{16})\/browser$/)) && req.method === 'POST') {
      const directory = known.get(match[1]);
      const study = directory ? findStudy(directory) : null;
      if (!study || study.id !== match[1]) return sendJson(res, 404, { error: 'Study not found' });
      try {
        // workspace.py binds 127.0.0.1 and checks Host and Origin itself, as when run from a terminal.
        return sendJson(res, 200, { url: `http://127.0.0.1:${await panels.port(study, { keep: true })}/` });
      } catch (error) {
        return sendJson(res, 503, { error: error.message, code: error.code, detail: error.detail });
      }
    }
    if (!reading) return sendJson(res, 404, { error: 'Not found' });
    if (rest === '/' || rest === '/ui') {
      res.writeHead(308, { location: `${BASE}/ui/${url.search}` });
      return res.end();
    }
    if (rest === '/api/studies') return sendJson(res, 200, { studies: studies(), shadowed: shadowed() });
    if ((match = rest.match(/^\/api\/sessions\/([^/]+)$/))) {
      let id;
      try { id = decodeURIComponent(match[1]); } catch { return sendJson(res, 400, { error: 'Invalid session' }); }
      const study = studyOfSession(id);
      return sendJson(res, 200, { session: id, study: publicStudy(study), shadowed: shadowed() });
    }
    if ((match = rest.match(/^\/ui\/(.*)$/))) return serveUi(req, res, match[1] || 'index.html');
    return sendJson(res, 404, { error: 'Not found' });
  };
}

export function apply(ctx) {
  ctx.effect(() => ctx.skills.registerProvider(() => createSkillProvider(SKILLS_ROOT)));
  const panels = new PanelServices({ findPython: () => findPython(), log: (line) => ctx.logger?.('tunetune').info?.(line) });
  const handler = createRouter(ctx, { panels });
  ctx.effect(() => {
    const dispose = ctx.webServer.register({ kind: 'prefix', path: BASE, handler });
    // Panel services can hold loaded models; they end with the plugin, not with the harness.
    return () => {
      dispose();
      void panels.stopAll();
    };
  });
}
