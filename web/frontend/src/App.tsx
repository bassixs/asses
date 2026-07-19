import { BrowserRouter, Link, NavLink, Route, Routes } from "react-router-dom";
import { IS_DEMO } from "./api";
import Home from "./pages/Home";
import Workspace from "./pages/Workspace";
import Analytics from "./pages/Analytics";
import Faq from "./pages/Faq";
import CenterPage from "./pages/CenterPage";
import ParticipantPage from "./pages/ParticipantPage";
import ExercisePage from "./pages/ExercisePage";
import ExerciseLibrary from "./pages/ExerciseLibrary";
import TemplatePage from "./pages/TemplatePage";

// На GitHub Pages сайт живёт в подпапке (/asses/) — базовый путь берём из сборки.
const basename = import.meta.env.BASE_URL.replace(/\/$/, "");

const NAV = [
  { to: "/", label: "Обзор", end: true },
  { to: "/exercises", label: "Упражнения", end: false },
  { to: "/workspace", label: "Центры", end: false },
  { to: "/analytics", label: "Аналитика", end: false },
  { to: "/faq", label: "FAQ", end: false },
];

export default function App() {
  return (
    <BrowserRouter basename={basename}>
      <header className="topbar">
        <Link to="/" className="brand">
          <span className="dot" />
          Ассессмент-центр
        </Link>
        <nav className="mainnav">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => (isActive ? "active" : "")}>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <span className="tag">HR-инструмент</span>
      </header>
      {IS_DEMO && (
        <div className="demo-banner">
          🔬 Демо-режим: витрина интерфейса — данные не сохраняются, обработка имитируется, скачивание отключено.
        </div>
      )}
      <main className="container">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/exercises" element={<ExerciseLibrary />} />
          <Route path="/exercises/:id" element={<TemplatePage />} />
          <Route path="/workspace" element={<Workspace />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/faq" element={<Faq />} />
          <Route path="/centers/:id" element={<CenterPage />} />
          <Route path="/participants/:id" element={<ParticipantPage />} />
          <Route path="/assessments/:id" element={<ExercisePage />} />
        </Routes>
      </main>
      <footer className="footer">
        Ассессмент-центр · оценка компетенций на ИИ · участники по коду, без ФИО
      </footer>
    </BrowserRouter>
  );
}
