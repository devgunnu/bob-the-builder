import { lazy, Suspense, useEffect, useState, type ReactNode } from "react";
import type { PublicConfig } from "../api/types";
import { Bob } from "../components/Bob";
import { loadAuthConfig } from "./session";

// Amplify UI is only downloaded when the server asks for Cognito sign-in.
const CognitoGate = lazy(() => import("./CognitoGate"));

/** Reads /api/config/public, then shows the Cognito sign-in when needed (D27). */
export function AuthGate({ children }: { children: ReactNode }) {
  const [cfg, setCfg] = useState<PublicConfig | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadAuthConfig().then(setCfg).catch((e) => setError(String(e.message ?? e)));
  }, []);

  if (error)
    return (
      <div className="grid h-full place-items-center bg-void px-4 text-center text-white">
        <div>
          <Bob pose="idle" size={110} float={false} still />
          <p className="mt-3 font-display text-xl font-bold">Bob can't reach the API</p>
          <p className="mt-1 text-[13px] text-dim">{error}</p>
          <button onClick={() => window.location.reload()} className="mt-4 rounded-xl bg-bob-blue px-4 py-2 text-[13.5px]">Try again</button>
        </div>
      </div>
    );
  if (!cfg) return <div className="h-full bg-void" />;
  if (cfg.auth !== "cognito") return <>{children}</>;
  return (
    <Suspense fallback={<div className="h-full bg-void" />}>
      <CognitoGate>{children}</CognitoGate>
    </Suspense>
  );
}

