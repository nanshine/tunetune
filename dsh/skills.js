// Offer the four TuneTune skills to DeepSeek Harness from the same folders every channel ships.
// Same-name skills a person installed in ~/.dsh/skills or ~/.agents/skills rank ahead of these.
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

export const SKILLS = ['research-workspace', 'tunetune-init', 'build-evaluation', 'run-experiments'];
const RANK = 600;
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
