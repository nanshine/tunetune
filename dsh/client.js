// TuneTune for DeepSeek Harness: the browser half.
//   - a left-sidebar entry whose main area lists every study and opens its panel full size
//   - a right-sidebar tab, offered on the guide page, showing the study of that conversation
// Both frame the Host's /tunetune/ui/ page; the research panel is the study's own pinned panel.
window.__ModuleLoader__.load({
  id: 'dsh-tunetune',
  factory: (require) => {
    var module = { exports: {} };
    var exports = module.exports;
    Object.defineProperty(exports, Symbol.toStringTag, { value: 'Module' });

    const React = require('react');
    const h = React.createElement;
    const ID = 'dsh-tunetune';
    const UI = '/tunetune/ui/';
    // Named for what the person does here, like the harness's other workspaces; TuneTune is the maker.
    const LABEL = { zh: '模型研究室', en: 'Model Lab' };
    const GUIDE = {
      zh: '在对话旁查看这个文件夹里的模型研究：方案、评测、实验和验收。',
      en: 'See this folder’s model research beside the conversation: proposal, evaluation, experiments and acceptance.',
    };

    // The TuneTune double-pulse symbol (design/brand/tunetune-symbol.svg), cropped square and drawn in currentColor.
    function TuneIcon(props) {
      const s = (props && props.size) || 18;
      return h('svg', { width: s, height: s, viewBox: '43 6 248 248', fill: 'currentColor', 'aria-hidden': true },
        h('circle', { cx: 70, cy: 184, r: 18 }),
        h('path', { d: 'M98 163C131 131 176 102 216 80L223 96C177 113 134 139 98 163Z' }),
        h('path', { d: 'M96 182C125 164 152 154 178 151L180 166C151 168 123 178 99 192Z' }),
        h('path', { d: 'M244.03 67.814L270.341 58.237A17 17 0 0 1 281.97 90.186L255.659 99.763A17 17 0 0 1 244.03 67.814Z' }),
        h('path', { d: 'M201.107 145.608L220.594 141.109A14 14 0 0 1 226.893 168.392L207.406 172.891A14 14 0 0 1 201.107 145.608Z' }));
    }

    function apply(ctx) {
      const frames = new Set();
      let scheme = null;
      let lang = /^en\b/i.test(navigator.language) ? 'en' : 'zh';
      const post = (frame) => {
        const target = frame.contentWindow;
        if (!target) return;
        if (scheme) target.postMessage({ type: 'tunetune:scheme', scheme }, location.origin);
        target.postMessage({ type: 'tunetune:locale', lang }, location.origin);
      };
      // Follow the harness's color scheme and language when those services exist.
      ctx.inject(['theme'], (c) => {
        const push = (snap) => { scheme = snap.active.colorScheme; frames.forEach(post); };
        push(c.theme.getTheme());
        c.on('theme/change', push);
      });
      ctx.inject(['locale'], (c) => {
        const push = (snap) => { lang = /^en\b/i.test(snap.active) ? 'en' : 'zh'; frames.forEach(post); };
        push(c.locale.getSnapshot());
        c.on('locale/change', push);
      });

      function Frame(props) {
        const ref = React.useRef(null);
        const query = props.sessionId ? `?session=${encodeURIComponent(props.sessionId)}&lang=${lang}` : `?lang=${lang}`;
        const [src] = React.useState(() => UI + query);
        React.useEffect(() => {
          const self = ref.current;
          if (self) frames.add(self);
          function onMessage(event) {
            const frame = ref.current;
            if (!frame || event.source !== frame.contentWindow || event.origin !== location.origin) return;
            const message = event.data;
            if (message && message.type === 'tunetune:open-session' && typeof message.sessionId === 'string') {
              try {
                ctx.uiWorkspace.openSession(message.sessionId);
              } catch (error) {
                console.error('[tunetune] could not open the conversation', error);
              }
            }
          }
          addEventListener('message', onMessage);
          return () => { removeEventListener('message', onMessage); frames.delete(self); };
        }, []);
        return h('iframe', {
          ref, src, title: LABEL[lang],
          onLoad: (event) => post(event.currentTarget),
          style: { width: '100%', height: '100%', border: 0, display: 'block' },
        });
      }

      function StudiesPanel() {
        return h(Frame, {});
      }

      // The tab body receives the conversation it belongs to.
      function StudyTab(props) {
        return h(Frame, { sessionId: props.sessionId });
      }

      ctx.slots.inject('sidebar.panellist', () =>
        ctx.slots.register({ name: 'sidebar.panellist', id: ID, order: 7, label: () => LABEL[lang] }, TuneIcon));
      ctx.slots.inject('main', () => ctx.slots.register({ name: 'main', key: ID }, StudiesPanel));

      // The right sidebar is optional in a composition; without it the main entry still works.
      ctx.inject(['sidebarRightTabs'], (c) => {
        const disposers = [];
        disposers.push(c.sidebarRightTabs.register({
          id: ID,
          kind: ID,
          title: () => LABEL[lang],
          keepMounted: true,
          guide: [{ id: ID, order: 30, title: () => LABEL[lang], description: () => GUIDE[lang], icon: TuneIcon }],
        }));
        disposers.push(c.slots.inject('sidebar.right.pane.tab', () =>
          c.slots.register({ name: 'sidebar.right.pane.tab', key: ID }, StudyTab)));
        return () => { for (const dispose of disposers) if (typeof dispose === 'function') dispose(); };
      });
    }

    exports.isPlugin = true;
    exports.inject = ['slots', 'uiWorkspace'];
    exports.apply = apply;
    return module.exports;
  },
});
