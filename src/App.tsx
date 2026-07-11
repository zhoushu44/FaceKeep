import { BrowserRouter as Router, Navigate, Routes, Route } from "react-router-dom";
import Home from "@/pages/Home";
import Admin from "@/pages/Admin";
import Login from "@/pages/Login";
import UserCenter from "@/pages/UserCenter";
import AdminLogin from "@/pages/AdminLogin";
import { ADMIN_SESSION_KEY } from "@/lib/api";

function AdminRoute() {
  return localStorage.getItem(ADMIN_SESSION_KEY) ? <Admin /> : <Navigate to="/admin/login" replace />;
}

export default function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/admin" element={<AdminRoute />} />
        <Route path="/admin/login" element={<AdminLogin />} />
        <Route path="/login" element={<Login />} />
        <Route path="/user" element={<UserCenter />} />
      </Routes>
    </Router>
  );
}
