import { useRef, useState, type ReactNode } from "react";

const fmtSize = (bytes: number) => {
  if (bytes < 1024) return `${bytes} Б`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} КБ`;
  return `${(bytes / 1024 / 1024).toFixed(1)} МБ`;
};

/**
 * Styled drop zone in place of the native file input.
 *
 * Accepts a drop or a click. `multiple` passes every chosen file to `onFiles`;
 * otherwise just the first. The zone stays keyboard-reachable (it is a real button)
 * and shows the picked file's name + size so the choice is visible before upload.
 */
export function FileDrop({
  accept,
  multiple = false,
  disabled = false,
  icon,
  title,
  hint,
  onFiles,
}: {
  accept: string;
  multiple?: boolean;
  disabled?: boolean;
  icon?: ReactNode;
  title: string;
  hint: string;
  onFiles: (files: File[]) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [picked, setPicked] = useState<File[]>([]);

  const take = (list: FileList | null) => {
    const files = Array.from(list ?? []);
    if (!files.length) return;
    setPicked(files);
    onFiles(multiple ? files : files.slice(0, 1));
  };

  return (
    <div
      className={`filedrop ${over ? "over" : ""} ${disabled ? "off" : ""}`}
      role="button"
      tabIndex={disabled ? -1 : 0}
      onClick={() => !disabled && inputRef.current?.click()}
      onKeyDown={(e) => {
        if (!disabled && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          inputRef.current?.click();
        }
      }}
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        if (!disabled) take(e.dataTransfer.files);
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        multiple={multiple}
        disabled={disabled}
        hidden
        onChange={(e) => {
          take(e.target.files);
          e.target.value = ""; // тот же файл можно выбрать повторно
        }}
      />
      <span className="fd-icon" aria-hidden="true">
        {icon ?? (
          <svg viewBox="0 0 24 24" fill="none" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 15.5V4M8 8l4-4 4 4" />
            <path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
          </svg>
        )}
      </span>
      <div className="fd-text">
        <b>{title}</b>
        <span>{hint}</span>
      </div>
      {picked.length > 0 && (
        <div className="fd-picked">
          {picked.map((f, i) => (
            <span key={i}>
              📄 {f.name} · {fmtSize(f.size)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
