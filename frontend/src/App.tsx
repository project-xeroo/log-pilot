import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import RoleGuard from "@/components/shared/RoleGuard";
import Layout from "@/components/shared/Layout";
import LoginPage from "@/pages/LoginPage";
import ReportsPage from "@/pages/ReportsPage";
import ReportDetailPage from "@/pages/ReportDetailPage";
import DeploymentsPage from "@/pages/DeploymentsPage";
import WeightsPage from "@/pages/WeightsPage";
import UsersPage from "@/pages/UsersPage";
import RiskBoardPage from "@/pages/RiskBoardPage";
import NotFoundPage from "@/pages/NotFoundPage";
import ForbiddenPage from "@/pages/ForbiddenPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/403" element={<ForbiddenPage />} />

        {/* Protected — any authenticated user */}
        <Route
          path="/"
          element={
            <RoleGuard>
              <Layout>
                <Navigate to="/risk-board" replace />
              </Layout>
            </RoleGuard>
          }
        />

        <Route
          path="/reports"
          element={
            <RoleGuard>
              <Layout>
                <ReportsPage />
              </Layout>
            </RoleGuard>
          }
        />

        <Route
          path="/reports/:id"
          element={
            <RoleGuard>
              <Layout>
                <ReportDetailPage />
              </Layout>
            </RoleGuard>
          }
        />

        <Route
          path="/deployments"
          element={
            <RoleGuard>
              <Layout>
                <DeploymentsPage />
              </Layout>
            </RoleGuard>
          }
        />

        <Route
          path="/weights"
          element={
            <RoleGuard>
              <Layout>
                <WeightsPage />
              </Layout>
            </RoleGuard>
          }
        />

        <Route
          path="/risk-board"
          element={
            <RoleGuard>
              <Layout>
                <RiskBoardPage />
              </Layout>
            </RoleGuard>
          }
        />

        {/* Admin-only */}
        <Route
          path="/users"
          element={
            <RoleGuard allowedRoles={["admin"]}>
              <Layout>
                <UsersPage />
              </Layout>
            </RoleGuard>
          }
        />

        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </BrowserRouter>
  );
}
