import { useEffect, useState } from "react";
import { api } from "../api";
import { ConfirmDelete } from "../components/ConfirmDelete";
import type { WebUser } from "../types";

/** Panel shown once after a password is generated — it is never retrievable again. */
function PasswordReveal({ user, password, onClose }: { user: string; password: string; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard?.writeText(password).then(
      () => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      },
      () => {},
    );
  };
  return (
    <div className="pw-reveal">
      <div className="pw-head">
        <b>Пароль для «{user}»</b>
        <span className="muted">Показывается один раз — сохраните его сейчас.</span>
      </div>
      <div className="pw-value">
        <code>{password}</code>
        <button className="ghost small" onClick={copy}>
          {copied ? "Скопировано" : "Скопировать"}
        </button>
      </div>
      <button className="ghost small" onClick={onClose}>
        Готово, сохранил
      </button>
    </div>
  );
}

export default function UsersPage() {
  const [users, setUsers] = useState<WebUser[]>([]);
  const [name, setName] = useState("");
  const [asAdmin, setAsAdmin] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [reveal, setReveal] = useState<{ user: string; password: string } | null>(null);

  const load = () => api.listUsers().then(setUsers).catch((e: any) => setError(e.message));

  useEffect(() => {
    load();
  }, []);

  const wrap = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try {
      await fn();
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const add = () =>
    wrap(async () => {
      if (!name.trim()) return;
      const u = await api.createUser(name.trim(), asAdmin);
      setName("");
      setAsAdmin(false);
      if (u.password) setReveal({ user: u.username, password: u.password });
    });

  const resetPw = (u: WebUser) =>
    wrap(async () => {
      const r = await api.resetUserPassword(u.id);
      if (r.password) setReveal({ user: u.username, password: r.password });
    });

  const changeMine = () =>
    wrap(async () => {
      const r = await api.changeOwnPassword();
      setReveal({ user: "вашего аккаунта", password: r.password });
    });

  return (
    <>
      <div className="page-head">
        <h1>Пользователи</h1>
        <p className="muted">
          Специалисты работают в одном общем пространстве — видят одни центры, каталог и аналитику.
          Аккаунт нужен для входа и учёта. Пароль задаётся системой и показывается один раз при
          создании или сбросе.
        </p>
      </div>

      {reveal && (
        <div className="card">
          <PasswordReveal user={reveal.user} password={reveal.password} onClose={() => setReveal(null)} />
        </div>
      )}

      <div className="card">
        <h2>Новый специалист</h2>
        <div className="row">
          <input
            type="text"
            placeholder="Логин (латиница или кириллица)"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && add()}
          />
          <label className="chk">
            <input type="checkbox" checked={asAdmin} onChange={(e) => setAsAdmin(e.target.checked)} />
            <span>админ</span>
          </label>
          <button onClick={add} disabled={busy || !name.trim()}>
            Добавить
          </button>
        </div>
        <p className="muted" style={{ marginTop: 8 }}>
          Админ может управлять пользователями. Обычный специалист — нет.
        </p>
        {error && <div className="error">{error}</div>}
      </div>

      <div className="card">
        <h2>Список ({users.length})</h2>
        <div className="user-rows">
          {users.map((u) => (
            <div className={`user-row ${u.is_active ? "" : "off"}`} key={u.id}>
              <div className="ur-main">
                <span className="ur-name">
                  {u.username}
                  {u.is_self && <span className="ur-you">это вы</span>}
                </span>
                <span className="ur-sub muted">
                  {u.is_admin ? "администратор" : "специалист"}
                  {!u.is_active && " · отключён"}
                  {u.last_login
                    ? ` · вход ${new Date(u.last_login).toLocaleDateString("ru-RU")}`
                    : " · ещё не входил"}
                </span>
              </div>
              <div className="ur-actions">
                {u.is_self ? (
                  <button className="ghost small" disabled={busy} onClick={changeMine}>
                    Сменить свой пароль
                  </button>
                ) : (
                  <>
                    <button className="ghost small" disabled={busy} onClick={() => resetPw(u)}>
                      Сбросить пароль
                    </button>
                    <button
                      className="ghost small"
                      disabled={busy}
                      onClick={() => wrap(() => api.patchUser(u.id, { is_active: !u.is_active }))}
                    >
                      {u.is_active ? "Отключить" : "Включить"}
                    </button>
                    <ConfirmDelete
                      busy={busy}
                      what={`аккаунт «${u.username}»`}
                      onConfirm={() => wrap(() => api.deleteUser(u.id))}
                    />
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
