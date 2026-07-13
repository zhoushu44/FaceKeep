import { BrowserRouter as Router, Navigate, Routes, Route } from "react-router-dom";
import Home from "@/pages/Home";
import Admin from "@/pages/Admin";
import AdminBackup from "@/pages/AdminBackup";
import AdminImageApiSettings from "@/pages/AdminImageApiSettings";
import Login from "@/pages/Login";
import UserCenter from "@/pages/UserCenter";
import AdminLogin from "@/pages/AdminLogin";
import AdminRegister from "@/pages/AdminRegister";
import ApiDocs from "@/pages/ApiDocs";
import { ADMIN_SESSION_KEY } from "@/lib/api";

type AdminPage = "admin" | "backup" | "imageApiSettings";

function AdminRoute({ page = "admin" }: { page?: AdminPage }) {
  if (!localStorage.getItem(ADMIN_SESSION_KEY)) return <Navigate to="/admin/login" replace />;
  if (page === "backup") return <AdminBackup />;
  if (page === "imageApiSettings") return <AdminImageApiSettings />;
  return <Admin />;
}

export default function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/api-docs" element={<ApiDocs />} />
        <Route path="/admin" element={<AdminRoute />} />
        <Route path="/admin/backups" element={<AdminRoute page="backup" />} />
        <Route path="/admin/image-api-settings" element={<AdminRoute page="imageApiSettings" />} />
        <Route path="/admin/login" element={<AdminLogin />} />
        <Route path="/admin/register" element={<AdminRegister />} />
        <Route path="/login" element={<Login />} />
        <Route path="/user" element={<UserCenter />} />
      </Routes>
    </Router>
  );
}
