import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { MotionConfig } from "framer-motion";
import "./index.css";
import App from "./App.tsx";
import { DashboardListPage } from "./pages/DashboardListPage.tsx";
import { CreateDashboardPage } from "./pages/CreateDashboardPage.tsx";
import { BoardRoute } from "./pages/BoardRoute.tsx";
import { OrganizationPage } from "./pages/OrganizationPage.tsx";
import { InvitePage } from "./pages/InvitePage.tsx";
import { JoinPage } from "./pages/JoinPage.tsx";
import { MemberPage } from "./pages/MemberPage.tsx";
import { AdminPage } from "./pages/AdminPage.tsx";
import { AuthGate } from "./components/AuthGate.tsx";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {/* Honour the OS "reduce motion" setting in every framer-motion animation. */}
    <MotionConfig reducedMotion="user">
      <BrowserRouter>
        <AuthGate>
          <Routes>
            <Route element={<App />}>
              <Route index element={<DashboardListPage />} />
              <Route path="new" element={<CreateDashboardPage />} />
              <Route path="dashboards/:id" element={<BoardRoute />} />
              <Route path="organization" element={<OrganizationPage />} />
              <Route path="invite/:token" element={<InvitePage />} />
              <Route path="o/:slug" element={<JoinPage />} />
              <Route path="members/:userId" element={<MemberPage />} />
              <Route path="admin" element={<AdminPage />} />
            </Route>
          </Routes>
        </AuthGate>
      </BrowserRouter>
    </MotionConfig>
  </StrictMode>
);
