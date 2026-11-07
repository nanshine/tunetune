// Locate TuneTune studies and the Python that runs their pinned panel service.
// Kept free of DeepSeek Harness imports so it can be tested with plain Node.
import { execFile } from 'node:child_process';
import { createHash } from 'node:crypto';
import { lstatSync, readFileSync, realpathSync } from 'node:fs';
import { homedir } from 'node:os';
import { basename, join, sep } from 'node:path';

const MANIFEST_LIMIT = 1024 * 1024;
const SUMMARY_LIMIT = 160;
const PANEL_MARKER = /<meta\s+name="tunetune-panel"\s+content="relative-api"\s*\/?>/;

// The id names a directory without exposing its path in URLs or logs.
export function studyId(directory) {
  return createHash('sha256').update(directory).digest('hex').slice(0, 16);
}

export function shownPath(directory) {
  const home = homedir();
  return directory === home || directory.startsWith(home + sep) ? `~${directory.slice(home.length)}` : directory;
}

function shellWord(word) {
  return /^[A-Za-z0-9_./~=-]+$/.test(word) ? word : `'${word.replaceAll("'", "'\\''")}'`;
}

function regularFile(path) {
  try {
    const entry = lstatSync(path);
    return entry.isFile() ? entry : null;
  } catch {
    return null;
  }
}

function readJson(path) {
  const entry = regularFile(path);
  if (!entry || entry.size > MANIFEST_LIMIT) return null;
  try {
    const value = JSON.parse(readFileSync(path, 'utf8'));
    return value && typeof value === 'object' && !Array.isArray(value) ? value : null;
  } catch {
    return null;
  }
}

// Where the study stands, read from the same core records the panel shows.
function stageOf(project, summary) {
  if (Array.isArray(project?.deliveries) && project.deliveries.length) return 'delivered';
  if (typeof project?.current_evaluation === 'string' && project.current_evaluation) return 'experiments';
  return summary ? 'proposal' : 'starting';
}

// A study is a directory initialized by init.py: its pinned tools carry their own panel.
// Returns null for anything else, including symlinked project roots, which workspace.py refuses.
export function inspectStudy(directory) {
  if (typeof directory !== 'string' || !directory.startsWith('/')) return null;
  let real;
  try {
    if (lstatSync(directory).isSymbolicLink()) return null;
    real = realpathSync(directory);
  } catch {
    return null;
  }
  const manifest = readJson(join(real, '.workspace', 'manifest.json'));
  if (!manifest || !regularFile(join(real, '.workspace', 'app', 'workspace.py'))) return null;
  const project = readJson(join(real, 'project.json'));
  let embeddable = false;
  const index = join(real, '.workspace', 'app', 'assets', 'index.html');
  if (regularFile(index)) {
    try { embeddable = PANEL_MARKER.test(readFileSync(index, 'utf8')); } catch { embeddable = false; }
  }
  const proposal = readJson(join(real, 'proposal.json'));
  const summary = typeof proposal?.summary === 'string' ? proposal.summary.trim() : '';
  return {
    id: studyId(real),
    directory: real,
    path: shownPath(real),
    folder: basename(real),
    name: typeof project?.name === 'string' && project.name.trim() ? project.name.trim() : null,
    summary: summary.length > SUMMARY_LIMIT ? `${summary.slice(0, SUMMARY_LIMIT - 1)}…` : summary || null,
    stage: stageOf(project, summary),
    version: typeof manifest.version === 'string' ? manifest.version : null,
    // Panels from earlier tools request /api at the site root and cannot run under a prefix.
    embeddable,
    command: ['python3', join(real, '.workspace', 'app', 'workspace.py'), '--project', real, '--port', '0', '--open'].map(shellWord).join(' '),
  };
}

function pythonVersion(executable) {
  return new Promise((resolve) => {
    execFile(executable, ['-c', 'import sys; print("%d.%d" % sys.version_info[:2])'], { timeout: 5000 }, (error, stdout) => {
      if (error) return resolve(null);
      const match = String(stdout).trim().match(/^(\d+)\.(\d+)$/);
      resolve(match ? [Number(match[1]), Number(match[2])] : null);
    });
  });
}

// Desktop apps often start with a minimal PATH, so common install locations are tried too.
export const PYTHON_CANDIDATES = ['python3', '/opt/homebrew/bin/python3', '/usr/local/bin/python3', '/usr/bin/python3'];

export async function findPython(candidates = PYTHON_CANDIDATES, override = process.env.TUNETUNE_PYTHON) {
  for (const executable of override ? [override] : candidates) {
    const version = await pythonVersion(executable);
    if (version && (version[0] > 3 || (version[0] === 3 && version[1] >= 10))) return executable;
  }
  return null;
}
