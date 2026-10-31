import { BrowserRouter, Navigate, Route, Routes } from "react-router";
import { AuthGate } from "./auth/AuthGate";
import AccountScreen from "./screens/Account";
import BuildScreen from "./screens/Build";
import Home from "./screens/Home";
import JobList from "./screens/JobList";
import OAuthCallback from "./screens/OAuthCallback";
import PlanScreen from "./screens/Plan";
import ReportScreen from "./screens/Report";
import RowInspector from "./screens/RowInspector";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/oauth/callback" element={<OAuthCallback />} />
        <Route path="*" element={<AuthGate><SignedInRoutes /></AuthGate>} />
      </Routes>
    </BrowserRouter>
  );
}

function SignedInRoutes() {
  return (
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/jobs" element={<JobList />} />
        <Route path="/jobs/:id" element={<Navigate to="plan" replace />} />
        <Route path="/jobs/:id/plan" element={<PlanScreen />} />
        <Route path="/jobs/:id/build" element={<BuildScreen />} />
        <Route path="/jobs/:id/rows/:rowId" element={<RowInspector />} />
        <Route path="/jobs/:id/report" element={<ReportScreen />} />
        <Route path="/account" element={<AccountScreen />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
  );
}
