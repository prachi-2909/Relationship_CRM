import { Route, Routes } from "react-router-dom";

import { AppShell } from "./components/AppShell";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { AuditLogPage } from "./pages/AuditLogPage";
import { DashboardPage } from "./pages/DashboardPage";
import { ImportPage } from "./pages/ImportPage";
import { InteractionsPage } from "./pages/InteractionsPage";
import { LoginPage } from "./pages/LoginPage";
import { MomentsPage } from "./pages/MomentsPage";
import { OfficialProfilePage } from "./pages/OfficialProfilePage";
import { OfficialsPage } from "./pages/OfficialsPage";
import { OrganisationPage } from "./pages/OrganisationPage";
import { RelationshipDetailPage } from "./pages/RelationshipDetailPage";
import { RelationshipsPage } from "./pages/RelationshipsPage";
import { TasksPage } from "./pages/TasksPage";
import { UsersPage } from "./pages/UsersPage";

// PlaceholderPage retired — every screen is now implemented.

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<AppShell />}>
          <Route index element={<DashboardPage />} />
          <Route path="organisation" element={<OrganisationPage />} />
          <Route path="officials" element={<OfficialsPage />} />
          <Route path="officials/:id" element={<OfficialProfilePage />} />
          <Route path="relationships" element={<RelationshipsPage />} />
          <Route path="relationships/:id" element={<RelationshipDetailPage />} />
          <Route path="interactions" element={<InteractionsPage />} />
          <Route path="follow-ups" element={<TasksPage />} />
          <Route path="import" element={<ImportPage />} />
          <Route path="moments" element={<MomentsPage />} />
          <Route path="users" element={<UsersPage />} />
          <Route path="audit" element={<AuditLogPage />} />
          <Route
            path="*"
            element={
              <div className="text-sm text-muted-foreground">Page not found.</div>
            }
          />
        </Route>
      </Route>
    </Routes>
  );
}
