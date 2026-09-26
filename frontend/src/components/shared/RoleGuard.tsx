import { Navigate } from "react-router-dom";
import { useAuthStore } from "@/store/auth";
import type { Role } from "@/types";

interface Props {
  children: React.ReactNode;
  /** If provided, only these roles may access the route. */
  allowedRoles?: Role[];
}

/**
 * Route-level guard.  Unauthenticated users → /login.
 * Authenticated but wrong role → /403.
 */
export default function RoleGuard({ children, allowedRoles }: Props) {
  const { isAuthenticated, hasRole } = useAuthStore();

  if (!isAuthenticated()) return <Navigate to="/login" replace />;

  if (allowedRoles && !hasRole(...allowedRoles)) {
    return <Navigate to="/403" replace />;
  }

  return <>{children}</>;
}
