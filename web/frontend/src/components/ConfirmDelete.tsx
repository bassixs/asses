import { useState } from "react";

/**
 * Two-step delete. The first click only arms the action, the second performs it —
 * so nothing is destroyed by a stray click, without resorting to a browser dialog.
 *
 * Safe to place inside a clickable card: every click is stopped from bubbling into
 * the surrounding link.
 */
export function ConfirmDelete({
  onConfirm,
  what,
  busy,
}: {
  onConfirm: () => void | Promise<void>;
  /** What exactly disappears, e.g. "центр со всеми участниками и результатами". */
  what: string;
  busy?: boolean;
}) {
  const [armed, setArmed] = useState(false);

  const stop = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  if (!armed) {
    return (
      <button
        className="danger-link"
        title="Удалить"
        disabled={busy}
        onClick={(e) => {
          stop(e);
          setArmed(true);
        }}
      >
        Удалить
      </button>
    );
  }

  return (
    <span className="confirm-del" onClick={stop}>
      <span className="confirm-text">Удалить {what}?</span>
      <button
        className="danger"
        disabled={busy}
        onClick={(e) => {
          stop(e);
          setArmed(false);
          void onConfirm();
        }}
      >
        Да, удалить
      </button>
      <button
        className="ghost"
        disabled={busy}
        onClick={(e) => {
          stop(e);
          setArmed(false);
        }}
      >
        Отмена
      </button>
    </span>
  );
}
