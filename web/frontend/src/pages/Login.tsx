import { useState } from "react";
import { api } from "../api";

export default function Login({ onSuccess }: { onSuccess: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!username.trim() || !password) return;
    setBusy(true);
    setError("");
    try {
      await api.login(username.trim(), password);
      onSuccess();
    } catch (err: any) {
      setError(err.message || "Не удалось войти");
      setPassword("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-screen">
      <div className="login-glow" />
      <form className="login-card" onSubmit={submit}>
        <div className="login-brand">
          <span className="dot" />
          Ассессмент-центр
        </div>
        <h1>Вход в систему</h1>
        <p className="muted">
          Оценка компетенций на ИИ. Доступ только для сотрудников HR.
        </p>

        <label className="login-field">
          <span>Логин</span>
          <input
            type="text"
            autoComplete="username"
            autoFocus
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="Ваш логин"
          />
        </label>

        <label className="login-field">
          <span>Пароль</span>
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••"
          />
        </label>

        {error && <div className="error">{error}</div>}

        <button type="submit" className="login-submit" disabled={busy || !username.trim() || !password}>
          {busy ? "Проверяем…" : "Войти"}
        </button>

        <p className="login-foot">Сессия сохраняется на две недели на этом устройстве.</p>
      </form>
    </div>
  );
}
