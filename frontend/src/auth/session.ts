// Runtime auth config (CONTRACTS section 14, D27). One build runs on Vite dev
// (auth "none") and on CloudFront (auth "cognito"); nothing is hard-coded.

import { Amplify } from "aws-amplify";
import { fetchAuthSession, signOut } from "aws-amplify/auth";
import type { PublicConfig } from "../api/types";

let mode: PublicConfig["auth"] = "none";

export async function loadAuthConfig(): Promise<PublicConfig> {
  const res = await fetch("/api/config/public");
  if (!res.ok) throw new Error(`Couldn't load /api/config/public (${res.status})`);
  const cfg = (await res.json()) as PublicConfig;
  mode = cfg.auth;
  if (cfg.auth === "cognito" && cfg.cognito) {
    Amplify.configure({
      Auth: {
        Cognito: {
          userPoolId: cfg.cognito.user_pool_id,
          userPoolClientId: cfg.cognito.client_id,
          loginWith: { email: true },
        },
      },
    });
  }
  return cfg;
}

export const authMode = () => mode;

/** A fresh access token (Amplify refreshes it when needed), or null when auth is "none". */
export async function accessToken(): Promise<string | null> {
  if (mode !== "cognito") return null;
  const s = await fetchAuthSession();
  return s.tokens?.accessToken?.toString() ?? null;
}

export async function authHeader(): Promise<Record<string, string>> {
  const t = await accessToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

/** 401 from the API: sign out so the Authenticator shows the sign-in form again. */
export async function onUnauthorized() {
  if (mode !== "cognito") return;
  try {
    await signOut();
  } finally {
    window.location.assign("/");
  }
}

export { signOut };
