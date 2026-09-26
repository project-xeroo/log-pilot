import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Role, User } from "@/types";

interface AuthState {
  token: string | null;
  user: User | null;
  role: Role | null;
  setAuth: (token: string, user: User) => void;
  logout: () => void;
  isAuthenticated: () => boolean;
  hasRole: (...roles: Role[]) => boolean;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      user: null,
      role: null,
      setAuth: (token, user) => set({ token, user, role: user.role }),
      logout: () => set({ token: null, user: null, role: null }),
      isAuthenticated: () => !!get().token,
      hasRole: (...roles) => {
        const r = get().role;
        return r !== null && roles.includes(r);
      },
    }),
    { name: "logpilot-auth" }
  )
);
