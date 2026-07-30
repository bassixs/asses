import { useEffect, useRef, useState } from "react";

export type SelectOption = { value: string; label: string };

/**
 * Dropdown styled in the site's theme. The native <select> renders its option list via
 * the OS (blue highlight, wrong fonts) and can't be themed — this replaces it with a
 * custom list. Closes on outside click or Escape; keyboard-navigable.
 */
export function Select({
  value,
  options,
  placeholder = "— выберите —",
  emptyText = "нет вариантов",
  disabled = false,
  onChange,
}: {
  value: string;
  options: SelectOption[];
  placeholder?: string;
  emptyText?: string;
  disabled?: boolean;
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const ref = useRef<HTMLDivElement>(null);
  const selected = options.find((o) => o.value === value);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  const pick = (v: string) => {
    onChange(v);
    setOpen(false);
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (disabled) return;
    if (e.key === "Escape") return setOpen(false);
    if (!open && (e.key === "Enter" || e.key === " " || e.key === "ArrowDown")) {
      e.preventDefault();
      setOpen(true);
      return;
    }
    if (!open) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => Math.min(options.length - 1, i + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(0, i - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (options[active]) pick(options[active].value);
    }
  };

  return (
    <div className={`sel ${open ? "open" : ""} ${disabled ? "off" : ""}`} ref={ref}>
      <button
        type="button"
        className="sel-trigger"
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => !disabled && setOpen((o) => !o)}
        onKeyDown={onKey}
      >
        <span className={selected ? "" : "sel-ph"}>{selected ? selected.label : placeholder}</span>
        <span className="sel-chev" aria-hidden="true" />
      </button>

      {open && (
        <ul className="sel-menu" role="listbox">
          {options.length === 0 && <li className="sel-empty">{emptyText}</li>}
          {options.map((o, i) => (
            <li
              key={o.value}
              role="option"
              aria-selected={o.value === value}
              className={`sel-opt ${o.value === value ? "on" : ""} ${i === active ? "hi" : ""}`}
              onMouseEnter={() => setActive(i)}
              onClick={() => pick(o.value)}
            >
              <span>{o.label}</span>
              {o.value === value && <span className="sel-check" aria-hidden="true">✓</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
