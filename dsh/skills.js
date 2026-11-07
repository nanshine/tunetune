// Offer the four TuneTune skills to DeepSeek Harness from the same folders every channel ships.
// ~/.agents/skills is shared by every agent, so a copy there was usually installed for another one and
// must not replace this plugin's. Rank 450 sits between ~/.dsh/skills (400) and ~/.agents/skills (500):
// copies placed for DeepSeek Harness itself, in ~/.dsh/skills or a project's skill folders, still win.
import { existsSync, readFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { shownPath } from './studies.js';

export const SKILLS = ['research-workspace', 'tunetune-init', 'build-evaluation', 'run-experiments'];
export const RANK = 450;
const INVOCATION = { modelInvocable: true, userInvocable: true };

export function readSkill(root, name) {
  const dir = join(root, name);
  const file = join(dir, 'SKILL.md');
  if (!existsSync(file)) return null;
  const text = readFileSync(file, 'utf8');
  const head = text.match(/^---\n([\s\S]*?)\n---\n?/);
  if (!head) return null;
  const field = (key) => head[1].match(new RegExp(`^${key}:\\s*(.+)$`, 'm'))?.[1].trim().replace(/^(["'])(.*)\1$/, '$2');
  if (field('name') !== name || !field('description')) return null;
  return { name, description: field('description'), dir, file, body: text.slice(head[0].length) };
}

export function createSkillProvider(root) {
  const candidate = (skill) => ({
    name: skill.name,
    description: skill.description,
    path: skill.file,
    invocation: INVOCATION,
    source: 'bundled',
    provider: 'tunetune',
    rank: RANK,
    locator: skill.name,
    // Relative references such as ../research-workspace/references/records.md resolve from here.
    resourceBase: { kind: 'directory', path: skill.dir },
  });
  return {
    name: 'tunetune',
    async list() {
      return SKILLS.map((name) => readSkill(root, name)).filter(Boolean).map(candidate);
    },
    async get(found) {
      const skill = SKILLS.includes(found.locator) ? readSkill(root, found.locator) : null;
      if (!skill) return undefined;
      const { rank, locator, ...summary } = candidate(skill);
      return { ...summary, content: skill.body };
    },
  };
}

function manifestVersion(dir) {
  try {
    const value = JSON.parse(readFileSync(join(dir, 'manifest.json'), 'utf8'));
    return typeof value?.version === 'string' ? value.version : null;
  } catch {
    return null;
  }
}

function sameFile(left, right) {
  try {
    return readFileSync(left).equals(readFileSync(right));
  } catch {
    return false;
  }
}

// Same-name copies in ~/.dsh/skills still win over the plugin's, so an older install silently
// sends new studies to older tools whose panel cannot appear here. Report each such directory.
export function shadowingSkills(root, directories = [join(homedir(), '.dsh', 'skills')]) {
  const bundled = manifestVersion(join(root, 'research-workspace'));
  const found = [];
  for (const directory of directories) {
    const names = SKILLS.filter((name) => existsSync(join(directory, name, 'SKILL.md')));
    if (!names.length) continue;
    const version = names.includes('research-workspace') ? manifestVersion(join(directory, 'research-workspace')) : null;
    const differs = (version && version !== bundled)
      || names.some((name) => !sameFile(join(directory, name, 'SKILL.md'), join(root, name, 'SKILL.md')));
    if (differs) found.push({ location: shownPath(directory), skills: names, version, bundled });
  }
  return found;
}
