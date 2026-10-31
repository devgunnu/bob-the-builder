import { useEffect, useState, type ReactNode } from "react";
import { Authenticator, ThemeProvider, type Theme } from "@aws-amplify/ui-react";
import { Bob } from "../components/Bob";

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

/** Loads Amplify's stylesheet only when sign-in is used, inside a CSS layer so it can't override the app. */
export default function CognitoGate({ children, signup = false }: { children: ReactNode; signup?: boolean }) {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    import("@aws-amplify/ui-react/styles.layer.css").then(() => setReady(true));
  }, []);
  if (!ready) return <div className="h-full bg-void" />;

  return (
    <ThemeProvider theme={theme} colorMode="dark">
      <Authenticator.Provider>
        <Gate signup={signup}>{children}</Gate>
      </Authenticator.Provider>
    </ThemeProvider>
  );
}

function Gate({ children, signup }: { children: ReactNode; signup: boolean }) {
  return (
    <Authenticator
      hideSignUp={!signup}
      loginMechanisms={["email"]}
      components={{
        Header: () => (
          <div className="flex flex-col items-center pb-4 pt-8 text-center">
            <Bob pose="wave" size={110} />
            <p className="mt-2 font-display text-2xl font-extrabold text-white">Sign in to Bob</p>
            <p className="text-[13px] text-dim">{signup ? "Sign in, or create an account." : "Bob is invite only. Ask the team for an account."}</p>
          </div>
        ),
      }}
      className="min-h-full bg-void"
    >
      {() => <>{children}</>}
    </Authenticator>
  );
}
