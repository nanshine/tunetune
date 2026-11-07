// Frame page for TuneTune inside DeepSeek Harness.
//   ?session=<id>  right sidebar tab: the study in that session's working directory
//   (no session)   main area: every study the loaded sessions point at
// The research panel itself is each study's own pinned panel, framed below this page.
const params = new URLSearchParams(location.search);
const sessionId = params.get('session');
const app = document.getElementById('app');
const POLL_MS = 3000;

const TEXT = {
  zh: {
    loading: '正在读取研究…',
    emptyTitle: '这个对话还没有 TuneTune 研究',
    emptyBody: '在对话里说出你想做的模型，例如「用 TuneTune 帮我做一个给客户留言分类的模型」。Agent 会在当前目录初始化研究，面板随后出现在这里。',
    listTitle: 'TuneTune 研究',
    listBody: '这里列出已打开的对话所在目录中的研究。研究在对话里开始、推进；面板显示研究并记录你的回应。',
    listEmpty: '还没有找到研究。在一个对话里让 Agent 用 TuneTune 开始研究即可。',
    open: '打开面板',
    conversation: '回到对话',
    back: '全部研究',
    unnamed: '未命名研究',
    sessions: (n) => `${n} 个对话`,
    oldTitle: '这个研究用的是较早的面板',
    oldBody: '它的工具固定在初始化时的版本，那一版面板不能嵌入 DeepSeek Harness。在终端运行下面的命令，用浏览器打开它：',
    failTitle: '研究面板没有启动',
    pythonBody: '需要 Python 3.10 或更新版本。安装后重新打开这个标签；也可以设置环境变量 TUNETUNE_PYTHON 指向 python3。',
    windowsBody: '在 Windows 上，TuneTune 需要在 WSL2 里运行。请在 WSL2 中运行 DeepSeek Harness 并打开研究目录，或者让 Agent 帮你配置 WSL2。',
    failBody: '下面是面板服务的输出：',
    retry: '重试',
  },
  en: {
    loading: 'Reading the study…',
    emptyTitle: 'No TuneTune study in this conversation yet',
    emptyBody: 'Tell the Agent what model you want, for example “Use TuneTune to build a model that sorts my customer messages.” It initializes the study in the current directory and the panel appears here.',
    listTitle: 'TuneTune studies',
    listBody: 'Studies in the directories of open conversations. Research starts and moves forward in the conversation; the panel shows it and records your responses.',
    listEmpty: 'No study found yet. Ask the Agent in a conversation to start one with TuneTune.',
    open: 'Open panel',
    conversation: 'Go to conversation',
    back: 'All studies',
    unnamed: 'Untitled study',
    sessions: (n) => `${n} conversation${n === 1 ? '' : 's'}`,
    oldTitle: 'This study uses an earlier panel',
    oldBody: 'Its tools stay at the version that initialized it, and that panel cannot be embedded in DeepSeek Harness. Run this in a terminal to open it in a browser:',
    failTitle: 'The research panel did not start',
    pythonBody: 'Python 3.10 or newer is required. Install it and reopen this tab, or set TUNETUNE_PYTHON to a python3 executable.',
    windowsBody: 'On Windows, TuneTune runs inside WSL2. Run DeepSeek Harness inside WSL2 and open the study there, or ask the Agent to set up WSL2.',
    failBody: 'Output from the panel service:',
    retry: 'Retry',
  },
};
let lang = /^en\b/i.test(params.get('lang') || navigator.language) ? 'en' : 'zh';
const t = (key, ...args) => {
  const value = TEXT[lang][key];
  return typeof value === 'function' ? value(...args) : value;
};

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === 'onclick') node.addEventListener('click', value);
    else if (value !== undefined && value !== null) node.setAttribute(key, value);
  }
  for (const child of children.flat()) if (child !== null && child !== undefined) node.append(child);
  return node;
}

function show(...nodes) {
  // replaceChildren would print an absent header as the text "null".
  app.replaceChildren(...nodes.filter((node) => node !== null && node !== undefined));
}

function notice(title, body, ...extra) {
  return el('div', { class: 'notice' }, el('h1', {}, title), el('p', {}, body), ...extra);
}

async function json(path) {
  const response = await fetch(path, { cache: 'no-store', credentials: 'same-origin' });
  const value = await response.json().catch(() => ({}));
  return { ok: response.ok, status: response.status, value };
}

function tell(message) {
  if (parent !== window) parent.postMessage(message, location.origin);
}

let timer = null;
let current = null;
function schedule(next) {
  clearTimeout(timer);
  timer = setTimeout(next, POLL_MS);
}

// Probe the study's panel before framing it, so a missing Python reads as a sentence, not JSON.
async function openStudy(study, header) {
  clearTimeout(timer);
  current = { study, header };
  if (!study.embeddable) {
    show(header, notice(t('oldTitle'), t('oldBody'), el('pre', {}, study.command)));
    return;
  }
  const base = `../p/${study.id}/`;
  const probe = await json(`${base}api/state`).catch(() => ({ ok: false, status: 0, value: {} }));
  if (current?.study !== study) return;
  if (!probe.ok) {
    const retry = el('button', { class: 'primary', onclick: () => openStudy(study, header) }, t('retry'));
    const known = { 'python-missing': 'pythonBody', 'windows-host': 'windowsBody' }[probe.value.code];
    const detail = known ? null : el('pre', {}, probe.value.detail || probe.value.error || `HTTP ${probe.status}`);
    show(header, notice(t('failTitle'), t(known || 'failBody'), detail, retry));
    return;
  }
  show(header, el('iframe', { class: 'frame', src: base, title: study.name || t('unnamed') }));
}

async function sessionView() {
  current = null;
  const answer = await json(`../api/sessions/${encodeURIComponent(sessionId)}`).catch(() => null);
  if (answer?.ok && answer.value.study) return openStudy(answer.value.study, null);
  // The study appears once the Agent initializes it in this conversation's directory.
  show(notice(t('emptyTitle'), t('emptyBody')));
  schedule(sessionView);
}

async function listView() {
  current = null;
  const answer = await json('../api/studies').catch(() => null);
  const studies = answer?.ok ? answer.value.studies : [];
  const cards = studies.map((study) => el('div', { class: 'card' },
    el('div', { class: 'name' }, study.name || t('unnamed')),
    el('div', { class: 'path' }, study.path),
    el('div', { class: 'path' }, t('sessions', study.sessions.length)),
    el('div', { class: 'actions' },
      el('button', { class: 'primary', onclick: () => openStudy(study, studyBar(study)) }, t('open')),
      study.sessions.length ? el('button', { onclick: () => tell({ type: 'tunetune:open-session', sessionId: study.sessions[0] }) }, t('conversation')) : null)));
  show(el('div', { class: 'list' },
    el('h1', {}, t('listTitle')),
    el('p', {}, t('listBody')),
    cards.length ? el('div', { class: 'cards' }, cards) : el('p', {}, t('listEmpty'))));
  schedule(listView);
}

function studyBar(study) {
  return el('div', { class: 'bar' },
    el('button', { onclick: () => listView() }, `← ${t('back')}`),
    el('span', { class: 'title' }, study.name || t('unnamed')),
    study.sessions.length ? el('button', { onclick: () => tell({ type: 'tunetune:open-session', sessionId: study.sessions[0] }) }, t('conversation')) : null);
}

function render() {
  show(el('div', { class: 'notice' }, el('p', {}, t('loading'))));
  return sessionId ? sessionView() : listView();
}

// The plugin's browser half forwards the harness's color scheme and language.
addEventListener('message', (event) => {
  if (event.source !== parent || event.origin !== location.origin) return;
  const message = event.data;
  if (message?.type === 'tunetune:scheme' && (message.scheme === 'light' || message.scheme === 'dark')) {
    document.documentElement.dataset.scheme = message.scheme;
  }
  if (message?.type === 'tunetune:locale' && typeof message.lang === 'string') {
    const next = /^en\b/i.test(message.lang) ? 'en' : 'zh';
    document.documentElement.lang = next === 'en' ? 'en' : 'zh-CN';
    // A framed panel is the study's own and keeps its language; only this page's text changes.
    if (next !== lang && !current) {
      lang = next;
      render();
    } else {
      lang = next;
    }
  }
});

render();
