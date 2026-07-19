import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import type { ExerciseTemplate } from "../types";

export function StatusBadge({ t }: { t: ExerciseTemplate }) {
  if (t.is_usable) return <span className="badge ok">✓ Готово</span>;
  if (t.status === "ready" && !t.has_notebook)
    return <span className="badge warn">Нужен блокнот</span>;
  if (t.understood) return <span className="badge warn">Ждёт активации</span>;
  return <span className="badge draft">Черновик</span>;
}

export default function ExerciseLibrary() {
  const [items, setItems] = useState<ExerciseTemplate[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () =>
    api
      .listTemplates()
      .then(setItems)
      .catch((e: any) => setError(e.message));

  useEffect(() => {
    load();
  }, []);

  const create = async () => {
    if (!name.trim()) return;
    setBusy(true);
    setError("");
    try {
      await api.createTemplate(name.trim());
      setName("");
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const ready = items.filter((t) => t.is_usable).length;

  return (
    <>
      <div className="page-head">
        <h1>Упражнения</h1>
        <p className="muted">
          Каталог упражнений: заводятся один раз, здесь. К упражнению прикладываются материалы и
          пустой блокнот наблюдателя, ИИ разбирает их и подтверждает понимание — только после этого
          упражнение можно выбрать при оценке участника.
        </p>
      </div>

      <div className="card">
        <h2>Новое упражнение</h2>
        <div className="row">
          <input
            type="text"
            placeholder="Название упражнения"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && create()}
          />
          <button onClick={create} disabled={busy}>
            Создать
          </button>
        </div>
        <p className="muted" style={{ marginTop: 10 }}>
          Дальше на странице упражнения: приложить материалы и блокнот → «Проверить понимание» → активировать.
        </p>
        {error && <div className="error">{error}</div>}
      </div>

      <div className="card">
        <h2>
          Каталог {items.length > 0 && <span className="pill">{ready} из {items.length} готовы</span>}
        </h2>
        {items.length === 0 && <p className="muted">Каталог пуст. Создайте первое упражнение.</p>}
        <ul className="list">
          {items.map((t) => (
            <li key={t.id}>
              <div className="li-main">
                <Link to={`/exercises/${t.id}`}>{t.name}</Link>
                <div className="li-sub muted">
                  материалов: {t.material_count} ·{" "}
                  {t.has_notebook
                    ? `блокнот: ${t.notebook_indicator_count ?? "?"} индикаторов`
                    : "блокнот не приложен"}
                </div>
              </div>
              <StatusBadge t={t} />
            </li>
          ))}
        </ul>
      </div>
    </>
  );
}
