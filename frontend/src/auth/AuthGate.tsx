import { useEffect, useState, type ReactNode } from "react";
import { Authenticator, ThemeProvider, type Theme } from "@aws-amplify/ui-react";
import type { PublicConfig } from "../api/types";
import { Bob } from "../components/Bob";
import { loadAuthConfig } from "./session";

// Calm dark theme for the Amplify sign-in form, in Bob's colours.
const theme: Theme = {
  name: "bob",
  tokens: {
    colors: {
      background: { primary: { value: "#0a0e1a" }, secondary: { value: "#0f1424" } },
      font: { primary: { value: "#ffffff" }, secondary: { value: "#8a93ab" }, interactive: { value: "#4d8bff" } },
      border: { primary: { value: "rgba(255,255,255,0.12)" } },
      brand: { primary: { 10: { value: "#1f5bff" }, 80: { value: "#1f5bff" }, 90: { value: "#4d8bff" }, 100: { value: "#4d8bff" } } },
    },
    radii: { small: { value: "10px" }, medium: { value: "12px" }, large: { value: "16px" } },
  },
};

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
  if (!cfg) return <div className="h-full bg-cream" />;
  if (cfg.auth !== "cognito") return <>{children}</>;
  return <CognitoGate>{children}</CognitoGate>;
}

/** Loads Amplify's stylesheet only when sign-in is used, inside a CSS layer so it can't override the app. */
function CognitoGate({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    import("@aws-amplify/ui-react/styles.layer.css").then(() => setReady(true));
  }, []);
  if (!ready) return <div className="h-full bg-void" />;

  return (
    <ThemeProvider theme={theme} colorMode="dark">
      <Authenticator.Provider>
        <Gate>{children}</Gate>
      </Authenticator.Provider>
    </ThemeProvider>
  );
}

function Gate({ children }: { children: ReactNode }) {
  return (
    <Authenticator
      hideSignUp
      loginMechanisms={["email"]}
      components={{
        Header: () => (
          <div className="flex flex-col items-center pb-4 pt-8 text-center">
            <Bob pose="wave" size={110} />
            <p className="mt-2 font-display text-2xl font-extrabold text-white">Sign in to Bob</p>
            <p className="text-[13px] text-dim">Bob is invite only. Ask the team for an account.</p>
          </div>
        ),
      }}
      className="min-h-full bg-void"
    >
      {() => <>{children}</>}
    </Authenticator>
  );
}
