import { useEffect } from "react";
import { Bob } from "../components/Bob";

/** Composio redirects here after OAuth. The Setup screen polls /status, so this page only closes itself. */
export default function OAuthCallback() {
  useEffect(() => {
    const t = window.setTimeout(() => window.close(), 1200);
    return () => window.clearTimeout(t);
  }, []);
  return (
    <div className="grid h-full place-items-center bg-void text-white">
      <div className="flex flex-col items-center gap-3 text-center">
        <Bob pose="cheer" size={140} />
        <p className="font-display text-xl font-bold">Connected</p>
        <p className="text-[13px] text-dim">You can close this window and go back to Bob.</p>
      </div>
    </div>
  );
}
