import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import {
  createBrowserRouter,
  Navigate,
  RouterProvider,
} from "react-router-dom";
import "./index.css";
import { AppContextProvider } from "@/contexts/AppContext";
import { CartContextProvider } from "@/contexts/CartContext";
import { ErrorBoundary } from "@/components/ui/ErrorBoundary";
import { AppShell } from "@/components/layout/AppShell";
import { isAuthenticated } from "@/lib/auth";
import LoginPage from "@/pages/login";
import HomePage from "@/pages/home";
import ShopPage from "@/pages/shop";
import CheckoutPage from "@/pages/checkout";
import ChatPage from "@/pages/chat";
import OrdersPage from "@/pages/orders";
import ConversationsPage from "@/pages/conversations";
import SettingsPage from "@/pages/settings";

function requireAuth() {
  if (!isAuthenticated()) {
    throw new Response("", { status: 302, headers: { Location: "/login" } });
  }
  return null;
}

const router = createBrowserRouter([
  // Public
  {
    path: "/login",
    element: <LoginPage />,
  },

  // Protected — all share the AppShell layout
  {
    path: "/",
    element: <AppShell />,
    loader: requireAuth,
    children: [
      { index: true, element: <Navigate to="/home" replace /> },
      { path: "home", element: <HomePage /> },
      { path: "shop", element: <ShopPage /> },
      { path: "checkout", element: <CheckoutPage /> },
      { path: "chat", element: <ChatPage /> },
      { path: "chat/:vertical", element: <ChatPage /> },
      { path: "orders", element: <OrdersPage /> },
      { path: "conversations", element: <ConversationsPage /> },
      { path: "settings", element: <SettingsPage /> },
    ],
  },

  // Fallback
  { path: "*", element: <Navigate to="/home" replace /> },
]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ErrorBoundary>
      <AppContextProvider>
        <CartContextProvider>
          <RouterProvider router={router} />
        </CartContextProvider>
      </AppContextProvider>
    </ErrorBoundary>
  </StrictMode>
);
