import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
import { IS_DEMO } from "./api";
import Dashboard from "./pages/Dashboard";
import CenterPage from "./pages/CenterPage";
import ParticipantPage from "./pages/ParticipantPage";
import ExercisePage from "./pages/ExercisePage";

// На GitHub Pages сайт живёт в подпапке (/asses/) — базовый путь берём из сборки.
const basename = import.meta.env.BASE_URL.replace(/\/$/, "");

export default function App() {
  return (
    <BrowserRouter basename={basename}>
      <header className="topbar">
        <Link to="/" className="brand">
          <span className="dot" />
          Ассессмент-центр
        </Link>
        <span className="tag">HR-инструмент</span>
      </header>
      {IS_DEMO && (
        <div className="demo-banner">
          🔬 Демо-режим: витрина интерфейса — данные не сохраняются, обработка имитируется, скачивание отключено.
        </div>
      )}
      <main className="container">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/centers/:id" element={<CenterPage />} />
          <Route path="/participants/:id" element={<ParticipantPage />} />
          <Route path="/exercises/:id" element={<ExercisePage />} />
        </Routes>
      </main>
    </BrowserRouter>
  );
}
