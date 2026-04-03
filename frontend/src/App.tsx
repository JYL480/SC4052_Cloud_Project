import { Routes, Route, Navigate } from "react-router-dom";
// import { ProtectedRoute } from "./components/protected-route";

import Chat from "./pages/chat";
import Avatar from "./pages/avatar";

import "./App.css";

function App() {
  return (
    <main className="MainContent">
      <Routes>
        <Route path="/chat" element={<Chat />} />
        <Route path="/avatar" element={<Avatar />} />
        <Route path="/" element={<Navigate to="/chat" replace />} />
      </Routes>
    </main>
  );
}

export default App;
