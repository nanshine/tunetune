import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import { GripVertical, Maximize2, Minimize2, X } from 'lucide-react';

export type WindowPlacement = { dock: 'left' | 'right'; maximized: boolean; position: { x: number; y: number } | null; z: number; cascade: number };

// A movable research window. It docks by default so its place is predictable, can be dragged anywhere,
// and can fill the screen for wide work such as acceptance or reference review.
export function FloatingWindow({ id, title, icon, actions, placement, onClose, onToggleMaximized, onFocus, onMove, children }: {
  id: string; title: string; icon: ReactNode; actions?: ReactNode; placement: WindowPlacement;
  onClose: () => void; onToggleMaximized: () => void; onFocus: () => void; onMove: (position: { x: number; y: number }) => void; children: ReactNode;
}) {
  const frame = useRef<HTMLElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const drag = useRef<{ dx: number; dy: number } | null>(null);
  useEffect(() => { heading.current?.focus({ preventScroll: true }); }, []);
  const style = placement.maximized ? { zIndex: placement.z } : placement.position
    ? { zIndex: placement.z, left: placement.position.x, top: placement.position.y, right: 'auto' }
    : { zIndex: placement.z, ['--cascade' as string]: `${placement.cascade * 28}px` };
  return <section ref={frame} className={`window dock-${placement.dock} ${placement.maximized ? 'maximized' : ''} ${placement.position ? 'moved' : ''}`} style={style}
    role="dialog" aria-modal="false" aria-labelledby={`${id}-title`} onPointerDownCapture={onFocus}
    onKeyDown={event => { if (event.key === 'Escape') { event.stopPropagation(); onClose(); } }}>
    <header className="window-bar" onDoubleClick={onToggleMaximized}
      onPointerDown={event => {
        if (placement.maximized || (event.target as HTMLElement).closest('button, select, input, a')) return;
        const rect = frame.current!.getBoundingClientRect();
        drag.current = { dx: event.clientX - rect.left, dy: event.clientY - rect.top };
        event.currentTarget.setPointerCapture(event.pointerId);
      }}
      onPointerMove={event => {
        if (!drag.current) return;
        const x = Math.min(Math.max(event.clientX - drag.current.dx, 8 - (frame.current?.offsetWidth ?? 0) + 120), window.innerWidth - 120);
        const y = Math.min(Math.max(event.clientY - drag.current.dy, 8), window.innerHeight - 48);
        onMove({ x, y });
      }}
      onPointerUp={event => { drag.current = null; event.currentTarget.releasePointerCapture?.(event.pointerId); }}>
      <span className="window-grip" aria-hidden="true"><GripVertical size={14} /></span>
      <span className="window-icon" aria-hidden="true">{icon}</span>
      <h2 ref={heading} id={`${id}-title`} tabIndex={-1}>{title}</h2>
      <div className="window-actions">{actions}
        <button className="icon-button" aria-label={placement.maximized ? `还原${title}` : `放大${title}`} onClick={onToggleMaximized}>{placement.maximized ? <Minimize2 size={14} /> : <Maximize2 size={14} />}</button>
        <button className="icon-button" aria-label={`关闭${title}`} onClick={onClose}><X size={15} /></button>
      </div>
    </header>
    <div className="window-body">{children}</div>
  </section>;
}
