import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import CenterPage from "./pages/CenterPage";
import ParticipantPage from "./pages/ParticipantPage";
import ExercisePage from "./pages/ExercisePage";

export default function App() {
  return (
    <BrowserRouter>
      <header className="topbar">
        <Link to="/" className="brand">
          🏢 Ассессмент-центр
        </Link>
      </header>
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
