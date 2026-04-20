import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import "./index.css";
import ChatPage from "./pages/chat";

const router = createBrowserRouter([
  {
    path: "/",
    element: <ChatPage />,
  },
  {
    path: "/chat/:vertical",
    element: <ChatPage />,
  },
]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>
);
