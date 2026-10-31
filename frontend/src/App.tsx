import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router";

const AuthGate = lazy(async () => ({ default: (await import("./auth/AuthGate")).AuthGate }));
const AccountScreen = lazy(() => import("./screens/Account"));
const BuildScreen = lazy(() => import("./screens/Build"));
const Home = lazy(() => import("./screens/Home"));
const JobList = lazy(() => import("./screens/JobList"));
const OAuthCallback = lazy(() => import("./screens/OAuthCallback"));
const PlanScreen = lazy(() => import("./screens/Plan"));
const ReportScreen = lazy(() => import("./screens/Report"));
const RowInspector = lazy(() => import("./screens/RowInspector"));

function LoadingRoute() {
  return <div className="h-full bg-void" aria-label="Loading" />;
}

export default function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<LoadingRoute />}>
        <Routes>
          <Route path="/oauth/callback" element={<OAuthCallback />} />
          <Route path="*" element={<AuthGate><SignedInRoutes /></AuthGate>} />
        </Routes>
      </Suspense>
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
