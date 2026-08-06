import { Switch, Route, Redirect } from "wouter";

// ── Pages publiques
import LoginPage         from "@/pages/LoginPage";
import ApplicationForm   from "@/pages/ApplicationForm";
import SetupPasswordPage from "@/pages/SetupPasswordPage";
import TestPage          from "@/pages/TestPage";
import CandidateBooking  from "./pages/CandidateBooking";
import ForgotPasswordPage from "./pages/Forgotpasswordpage";
import ResetPasswordPage from "./pages/Resetpasswordpage";
// ── Pages manager
import ManagerDashboard from "./pages/ManagerDashboard";
import MissionRegistry  from "./pages/MissionRegistry";
import JobDetail        from "./pages/JobDetail";
import AllCandidates    from "./pages/all-candidates";
import CandidateList    from "./pages/candidate-list";
import CandidateDetail  from "./pages/candidate-detail";
import ManagerScheduler from "./pages/ManagerScheduler";
import ManagerAccount   from "./pages/ManagerAccount";

// ── Pages RH
import RHDashboard from "./pages/RHDashboard";
import RHAccount from "./pages/RHAccount";
import RHManagers from "./pages/RHManagers";
import CreateJob from "./pages/CreateJob";
import Jobspage from "./pages/Jobspage";
import JobDetailRH from "./pages/JobDetailRH";
import RHJobs from "./pages/RHJobs";
import RHRanking   from "./pages/RHRanking";
import RHCandidateReport  from "./pages/RHCandidateReport";


// ─── Helpers ─────────────────────────────────────────────────────────────────

interface JWTPayload {
  role?: string;
  exp?: number;
}

/** Décode le token ET vérifie l'expiration — supprime le token si invalide/expiré */
function decodePayload(): JWTPayload | null {
  try {
    const token = localStorage.getItem("access_token");
    if (!token) return null;
    const payload = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    // Token expiré → on le supprime immédiatement
    if (payload.exp && Date.now() / 1000 > payload.exp) {
      localStorage.removeItem("access_token");
      return null;
    }
    return payload;
  } catch {
    localStorage.removeItem("access_token");
    return null;
  }
}

// ─── Auth guards ──────────────────────────────────────────────────────────────

/** Vérifie juste qu'un token valide (non expiré) existe */
function RequireAuth({ children }: { children: React.ReactNode }) {
  if (!decodePayload()) return <Redirect to="/" />;
  return <>{children}</>;
}

/** Vérifie que le rôle correspond — sinon redirige vers la bonne page */
function RequireRole({ role, children }: { role: "RH" | "MANAGER"; children: React.ReactNode }) {
  const payload = decodePayload();
  if (!payload) return <Redirect to="/" />;

  const userRole = payload.role;
  if (userRole !== role) {
    if (userRole === "RH")      return <Redirect to="/rh/dashboard" />;
    if (userRole === "MANAGER") return <Redirect to="/dashboard" />;
    return <Redirect to="/" />;
  }

  return <>{children}</>;
}

// ─── App ──────────────────────────────────────────────────────────────────────

function App() {
  return (
    <Switch>

      {/* ── Pages publiques */}
      <Route path="/"               component={LoginPage}         />
      <Route path="/apply"          component={ApplicationForm}   />
      <Route path="/setup-password" component={SetupPasswordPage} />
      <Route path="/test"           component={TestPage}          />
      <Route path="/booking"        component={CandidateBooking}  />
      <Route path="/forgot-password" component={ForgotPasswordPage} />
      <Route path="/reset-password" component={ResetPasswordPage} />

      {/* ── Dashboard Manager */}
      <Route path="/dashboard">
        <RequireRole role="MANAGER"><ManagerDashboard /></RequireRole>
      </Route>

      {/* ── Jobs Manager */}
      <Route path="/mission-registry">
        <RequireRole role="MANAGER"><MissionRegistry /></RequireRole>
      </Route>

      <Route path="/job/:id">
        {() => <RequireRole role="MANAGER"><JobDetail /></RequireRole>}
      </Route>

      {/* ── Candidates Manager */}
      <Route path="/candidates">
        <RequireRole role="MANAGER"><AllCandidates /></RequireRole>
      </Route>

      <Route path="/candidates/:jobId">
        {() => <RequireRole role="MANAGER"><CandidateList /></RequireRole>}
      </Route>

      <Route path="/candidates/:jobId/:candidateId">
        {() => <RequireRole role="MANAGER"><CandidateDetail /></RequireRole>}
      </Route>

      {/* ── Interviews Manager */}
      <Route path="/interviews">
        <RequireRole role="MANAGER"><ManagerScheduler /></RequireRole>
      </Route>

      {/* ── Account Manager */}
      <Route path="/account">
        <RequireRole role="MANAGER"><ManagerAccount /></RequireRole>
      </Route>

      {/* ── RH Space */}
      <Route path="/rh/dashboard">
        <RequireRole role="RH"><RHDashboard /></RequireRole>
      </Route>
      <Route path="/rh/account">
        <RequireRole role="RH"><RHAccount /></RequireRole>
      </Route>
      <Route path="/rh/Managers">
        <RequireRole role="RH"><RHManagers /></RequireRole>
      </Route>
      <Route path="/rh/jobs/create">
        <RequireRole role="RH"><CreateJob /></RequireRole>
      </Route>
      <Route path="/rh/jobs/:id">
        {() => <RequireRole role="RH"><JobDetailRH /></RequireRole>}
      </Route>
      <Route path="/rh/jobs">
        <RequireRole role="RH"><Jobspage /></RequireRole>
      </Route>
      <Route path="/rh/ranking">
        <RequireRole role="RH"><RHJobs /></RequireRole>
      </Route>
      <Route path="/rh/ranking/:job_id">
        {() => <RequireRole role="RH"><RHRanking /></RequireRole>}
      </Route>
      <Route path="/rh/candidate/:job_id/:application_id">
        {() => <RequireRole role="RH"><RHCandidateReport /></RequireRole>}
      </Route>

      {/* ── Fallback */}
      <Route><Redirect to="/" /></Route>

    </Switch>
  );
}

export default App;