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
    const LABEL = { zh: 'TuneTune', en: 'TuneTune' };
    const GUIDE = {
      zh: '在对话旁边查看这个目录的模型研究：方案、评估、实验和验收。',
      en: 'See this directory’s model research beside the conversation: proposal, evaluation, experiments and acceptance.',
    };

    // A dial with a small tuning mark.
    function TuneIcon(props) {
      const s = (props && props.size) || 18;
      return h('svg', { width: s, height: s, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.6, strokeLinecap: 'round' },
        h('circle', { cx: 12, cy: 12, r: 8 }),
        h('path', { d: 'M12 12l4-4' }),
        h('path', { d: 'M12 4v2M20 12h-2M12 20v-2M4 12h2' }));
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
