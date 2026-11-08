// Carry what happens in a study's panel into the conversation that runs the study.
// Elsewhere the person answers in the panel and then tells the Agent; here the plugin does that:
//   - a panel answer steers the Agent, starting its next turn when it is idle
//   - a panel that cannot read the records is injected as context, so the Agent sees it at its next step
// Both name only files the Agent reads itself; the person's note stays in the response record.
import { randomUUID } from 'node:crypto';

const KINDS = { proposal: 'the proposal', plan: 'the experiment plan', evaluation_review: 'the draft references', acceptance: 'the acceptance outputs' };

function message(text) {
  const content = Object.freeze([Object.freeze({ type: 'text', text })]);
  return Object.freeze({ id: randomUUID(), role: 'user', content, source: Object.freeze({ kind: 'tunetune-panel' }) });
}

export function answerText(record) {
  const what = KINDS[record.kind] ?? record.kind;
  return `The person answered in the TuneTune panel: "${record.decision}" on ${what} (${record.target.path}, `
    + `sha256 ${record.target.sha256.slice(0, 12)}…). Read responses/${record.id}.json and continue from it; `
    + 'if that file has changed since, show the new version and ask again.';
}

export function syncErrorText(error) {
  return `The TuneTune panel cannot show the study's records and is showing older content: ${error} `
    + 'Run records.py validate, fix the records, and mention it to the person only if it changes what they see.';
}

export class Conversations {
  // `agents` resolves a session id to a live agent; `sessionsOf` lists a study's sessions, newest first.
  constructor({ agents, sessionsOf }) {
    this.agents = agents;
    this.sessionsOf = sessionsOf;
    this.viewers = new Map();
    this.errors = new Map();
  }

  // The conversation whose sidebar last opened this study's panel, else the newest live one.
  viewed(studyId, sessionId) {
    if (typeof sessionId === 'string' && this.sessionsOf(studyId).includes(sessionId)) this.viewers.set(studyId, sessionId);
  }

  agent(studyId, sessionId) {
    const lookup = this.agents();
    if (!lookup) return undefined;
    // The route validates an explicit session against its current working directory.
    // Do not fall back to another agent or a cached directory listing for that click.
    const candidates = sessionId !== undefined
      ? [sessionId]
      : [this.viewers.get(studyId), ...this.sessionsOf(studyId)].filter(Boolean);
    for (const id of candidates) {
      const agent = lookup.get(id);
      if (agent && typeof agent.steer === 'function' && typeof agent.inject === 'function') return agent;
    }
    return undefined;
  }

  answered(studyId, body, sessionId) {
    let record;
    try { record = JSON.parse(body); } catch { return false; }
    if (!record || typeof record.id !== 'string' || typeof record.kind !== 'string' || typeof record.decision !== 'string'
      || typeof record.target?.path !== 'string' || typeof record.target?.sha256 !== 'string') return false;
    const agent = this.agent(studyId, sessionId);
    if (!agent) return false;
    agent.steer(message(answerText(record)));
    return true;
  }

  // Report each new failure once, not on every poll; a recovery clears it.
  synced(studyId, header, sessionId) {
    const key = JSON.stringify([studyId, sessionId]);
    let error = null;
    if (typeof header === 'string') {
      try { error = JSON.parse(header); } catch { error = null; }
    }
    if (typeof error !== 'string' || !error) {
      this.errors.delete(key);
      return false;
    }
    if (this.errors.get(key) === error) return false;
    const agent = this.agent(studyId, sessionId);
    if (!agent) return false;
    this.errors.set(key, error);
    agent.inject(message(syncErrorText(error)));
    return true;
  }
}
