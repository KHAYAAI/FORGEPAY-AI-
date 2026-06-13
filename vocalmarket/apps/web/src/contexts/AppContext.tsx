import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { getUser } from "@/lib/auth";
import type { AuthUser, Vertical } from "@/types";

interface ToastMessage {
  id: string;
  text: string;
  type: "success" | "error" | "info";
}

interface AppContextValue {
  user: AuthUser | null;
  vertical: Vertical;
  setVertical: (v: Vertical) => void;
  refreshUser: () => void;
  toast: (msg: string, type?: "success" | "error" | "info") => void;
  toasts: ToastMessage[];
  dismissToast: (id: string) => void;
}

const AppContext = createContext<AppContextValue | null>(null);

export function AppContextProvider({ children }: { children: ReactNode }) {
  const [user, setUserState] = useState<AuthUser | null>(getUser);
  const [vertical, setVerticalState] = useState<Vertical>("grocery");
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  useEffect(() => {
    const saved = localStorage.getItem("vocalmarket_vertical") as Vertical | null;
    if (saved && ["grocery", "b2b_procurement", "healthcare"].includes(saved)) {
      setVerticalState(saved);
    }
  }, []);

  const refreshUser = useCallback(() => {
    setUserState(getUser());
  }, []);

  const setVertical = useCallback((v: Vertical) => {
    setVerticalState(v);
    localStorage.setItem("vocalmarket_vertical", v);
  }, []);

  const toast = useCallback(
    (text: string, type: "success" | "error" | "info" = "info") => {
      const id = crypto.randomUUID();
      setToasts((prev) => [...prev, { id, text, type }]);
      setTimeout(
        () => setToasts((prev) => prev.filter((t) => t.id !== id)),
        4000,
      );
    },
    [],
  );

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return (
    <AppContext.Provider
      value={{
        user,
        vertical,
        setVertical,
        refreshUser,
        toast,
        toasts,
        dismissToast,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used within AppContextProvider");
  return ctx;
}
