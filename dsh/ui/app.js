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
    emptyTitle: '还没有研究',
    emptyBody: '告诉 Agent 你想做什么模型，研究开始后会显示在这里。',
    listTitle: '模型研究室',
    listBody: '每个研究对应一个文件夹。在对话里说出想做的模型，研究就会出现在这里。',
    listEmpty: '还没有研究。新建一个对话，告诉 Agent 你想做什么模型。',
    stage: { starting: '刚开始', proposal: '方案待定', experiments: '评测与实验', delivered: '已交付' },
    open: '打开',
    conversation: '对话',
    back: '全部研究',
    oldTitle: '这个研究由旧版 TuneTune 创建',
    oldBody: '旧版面板不能显示在这里，可以在浏览器里打开它。',
    browser: '在浏览器中打开',
    starting: '正在启动…',
    manual: '打不开时，在终端运行：',
    failTitle: '研究面板没有启动',
    pythonBody: '需要 Python 3.10 或更新版本。安装后重新打开这个标签；也可以设置环境变量 TUNETUNE_PYTHON 指向 python3。',
    windowsBody: '在 Windows 上，TuneTune 需要在 WSL2 里运行。请在 WSL2 中运行 DeepSeek Harness 并打开研究目录，或者让 Agent 帮你配置 WSL2。',
    failBody: '下面是面板服务的输出：',
    retry: '重试',
    shadowed: (item) => `${item.location} 里有另一份 TuneTune 技能${item.version ? `（${item.version}）` : ''}，`
      + 'DeepSeek Harness 会优先用它而不是这个插件自带的版本，新研究因此可能显示不到这里。'
      + `删除其中的 ${item.skills.join('、')} 文件夹即可改用插件版本。`,
  },
  en: {
    loading: 'Reading the study…',
    emptyTitle: 'No study yet',
    emptyBody: 'Tell the Agent what model you want. The study appears here once it starts.',
    listTitle: 'Model Lab',
    listBody: 'Each study is a folder. Describe the model you want in a conversation and its study appears here.',
    listEmpty: 'No studies yet. Start a conversation and tell the Agent what model you want.',
    stage: { starting: 'Starting', proposal: 'Proposal', experiments: 'Evaluating and experimenting', delivered: 'Delivered' },
    open: 'Open',
    conversation: 'Conversation',
    back: 'All studies',
    oldTitle: 'This study was made with an earlier TuneTune',
    oldBody: 'Its panel cannot appear here, but it opens in your browser.',
    browser: 'Open in browser',
    starting: 'Starting…',
    manual: 'If it does not open, run this in a terminal:',
    failTitle: 'The research panel did not start',
    pythonBody: 'Python 3.10 or newer is required. Install it and reopen this tab, or set TUNETUNE_PYTHON to a python3 executable.',
    windowsBody: 'On Windows, TuneTune runs inside WSL2. Run DeepSeek Harness inside WSL2 and open the study there, or ask the Agent to set up WSL2.',
    failBody: 'Output from the panel service:',
    retry: 'Retry',
    shadowed: (item) => `${item.location} holds another copy of the TuneTune skills${item.version ? ` (${item.version})` : ''}. `
      + 'DeepSeek Harness uses it instead of the version in this plugin, so new studies may not appear here. '
      + `Remove its ${item.skills.join(', ')} folders to use the plugin’s version.`,
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

const SVG = 'http://www.w3.org/2000/svg';
// The TuneTune double-pulse symbol, drawn in the current text color.
function brandMark() {
  const svg = document.createElementNS(SVG, 'svg');
  svg.setAttribute('viewBox', '48 52 240 156');
  svg.setAttribute('class', 'mark');
  svg.setAttribute('aria-hidden', 'true');
  const shapes = [
    ['circle', { cx: 70, cy: 184, r: 18 }],
    ['path', { d: 'M98 163C131 131 176 102 216 80L223 96C177 113 134 139 98 163Z' }],
    ['path', { d: 'M96 182C125 164 152 154 178 151L180 166C151 168 123 178 99 192Z' }],
    ['path', { d: 'M244.03 67.814L270.341 58.237A17 17 0 0 1 281.97 90.186L255.659 99.763A17 17 0 0 1 244.03 67.814Z' }],
    ['path', { d: 'M201.107 145.608L220.594 141.109A14 14 0 0 1 226.893 168.392L207.406 172.891A14 14 0 0 1 201.107 145.608Z' }],
  ];
  for (const [tag, attrs] of shapes) {
    const node = document.createElementNS(SVG, tag);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
    node.setAttribute('fill', 'currentColor');
    svg.append(node);
  }
  return svg;
}

// Older same-name skills elsewhere win over the plugin's, which explains a missing panel better than any error.
function shadowNotes(shadowed) {
  return (Array.isArray(shadowed) ? shadowed : []).map((item) => el('p', { class: 'warning' }, t('shadowed', item)));
}

const title = (study) => study.name || study.folder;

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
// The latest report of older skill copies, also shown beside an older study it likely produced.
let shadowed = [];
function schedule(next) {
  clearTimeout(timer);
  timer = setTimeout(next, POLL_MS);
}

// Probe the study's panel before framing it, so a missing Python reads as a sentence, not JSON.
async function openStudy(study, header) {
  clearTimeout(timer);
  current = { study, header };
  if (!study.embeddable) {
    const open = el('button', { class: 'primary', onclick: () => openInBrowser(study, open) }, t('browser'));
    show(header, notice(t('oldTitle'), t('oldBody'), el('div', { class: 'actions' }, open),
      el('details', {}, el('summary', {}, t('manual')), el('pre', {}, study.command)), ...shadowNotes(shadowed)));
    return;
  }
  const base = `../p/${study.id}/${sessionId ? `s/${encodeURIComponent(sessionId)}/` : ''}`;
  const probe = await json(`${base}api/state`).catch(() => ({ ok: false, status: 0, value: {} }));
  if (current?.study !== study) return;
  if (!probe.ok) {
    const retry = el('button', { class: 'primary', onclick: () => openStudy(study, header) }, t('retry'));
    const known = { 'python-missing': 'pythonBody', 'windows-host': 'windowsBody' }[probe.value.code];
    const detail = known ? null : el('pre', {}, probe.value.detail || probe.value.error || `HTTP ${probe.status}`);
    show(header, notice(t('failTitle'), t(known || 'failBody'), detail, retry));
    return;
  }
  // The panel's conversation receives the person's answers given there.
  show(header, el('iframe', { class: 'frame', src: base, title: title(study) }));
}

// The plugin starts the study's own service; the browser opens it on its loopback address.
async function openInBrowser(study, button) {
  const tab = window.open('', '_blank');
  button.disabled = true;
  button.textContent = t('starting');
  const answer = await fetch(`../api/studies/${study.id}/browser`, { method: 'POST', credentials: 'same-origin' })
    .then(async (response) => ({ ok: response.ok, value: await response.json().catch(() => ({})) }))
    .catch(() => ({ ok: false, value: {} }));
  button.disabled = false;
  button.textContent = t('browser');
  if (answer.ok && typeof answer.value.url === 'string') {
    if (tab) tab.location.href = answer.value.url;
    else window.open(answer.value.url, '_blank', 'noopener');
    return;
  }
  if (tab) tab.close();
  const known = { 'python-missing': 'pythonBody', 'windows-host': 'windowsBody' }[answer.value.code];
  const detail = known ? null : el('pre', {}, answer.value.detail || answer.value.error || '');
  show(current?.header, notice(t('failTitle'), t(known || 'failBody'), detail));
}

async function sessionView() {
  current = null;
  const answer = await json(`../api/sessions/${encodeURIComponent(sessionId)}`).catch(() => null);
  shadowed = answer?.value?.shadowed ?? [];
  if (answer?.ok && answer.value.study) return openStudy(answer.value.study, null);
  // The study appears once the Agent initializes it in this conversation's directory.
  show(notice(t('emptyTitle'), t('emptyBody'), ...shadowNotes(shadowed)));
  schedule(sessionView);
}

let shownList = null;
async function listView() {
  current = null;
  const answer = await json('../api/studies').catch(() => null);
  if (current) return;
  shadowed = answer?.value?.shadowed ?? [];
  const studies = answer?.ok ? answer.value.studies : [];
  // Polling rebuilds the page only when something changed, so a click never lands on a replaced button.
  const key = JSON.stringify([studies, shadowed, lang]);
  if (key === shownList && app.querySelector('.list')) return schedule(listView);
  shownList = key;
  const cards = studies.map((study) => el('div', { class: 'card' },
    el('div', { class: 'head' },
      el('span', { class: 'name' }, title(study)),
      study.stage ? el('span', { class: `stage ${study.stage}` }, t('stage')[study.stage]) : null),
    study.summary ? el('div', { class: 'summary' }, study.summary) : null,
    el('div', { class: 'path' }, study.path),
    el('div', { class: 'actions' },
      el('button', { class: 'primary', onclick: () => openStudy(study, studyBar(study)) }, t('open')),
      study.sessions.length ? el('button', { onclick: () => tell({ type: 'tunetune:open-session', sessionId: study.sessions[0] }) }, t('conversation')) : null)));
  show(el('div', { class: 'list' },
    el('h1', {}, brandMark(), t('listTitle')),
    el('p', {}, t('listBody')),
    ...shadowNotes(shadowed),
    cards.length ? el('div', { class: 'cards' }, cards) : el('p', { class: 'empty' }, t('listEmpty'))));
  schedule(listView);
}

function studyBar(study) {
  return el('div', { class: 'bar' },
    el('button', { onclick: () => listView() }, `← ${t('back')}`),
    el('span', { class: 'title' }, title(study)),
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
