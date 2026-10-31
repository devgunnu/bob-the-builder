import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { api, ApiError } from "../api/client";
import type { AvailableModel, ModelRoles, UserProfile } from "../api/types";
import { AppShell } from "../components/AppShell";
import { ModelsEditor } from "../components/ModelsEditor";
import { Button, ErrorBanner, useTitle } from "../components/ui";

export default function AccountScreen() {
  useTitle("Model settings");
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [models, setModels] = useState<ModelRoles | null>(null);
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [error, setError] = useState<ApiError | null>(null);
  const [results, setResults] = useState<Record<string, string> | null>(null);
  const [available, setAvailable] = useState<AvailableModel[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [loadingModels, setLoadingModels] = useState(false);

  useEffect(() => {
    api.me().then((p) => { setProfile(p); setModels(p.models); }).catch(setError);
  }, []);

  async function save() {
    if (!models) return;
    setBusy(true);
    setError(null);
    setResults(null);
    try {
      const updated = await api.saveModels(models, Object.fromEntries(Object.entries(keys).filter(([, value]) => value)));
      setModels(updated.models);
      setKeys({});
      const checked = await api.verifyModels();
      setResults(checked.roles);
      setProfile(await api.me());
    } catch (e) {
      setError(e as ApiError);
    } finally {
      setBusy(false);
    }
  }

  async function listModels() {
    setLoadingModels(true);
    setError(null);
    try {
      setAvailable((await api.availableModels()).models.filter((model) => model.on_demand));
    } catch (e) {
      setError(e as ApiError);
    } finally {
      setLoadingModels(false);
    }
  }

  return (
    <AppShell title="Model settings">
      <div className="mx-auto max-w-3xl px-4 py-8">
        <h1 className="font-display text-[28px] font-extrabold">Model settings</h1>
        <p className="mt-1 text-[14px] text-dim">Bob runs Bedrock models in its hosting account. The defaults are ready to use.</p>
        <ErrorBanner error={error} title="Model settings" />
        {!profile && !error && <div className="grid place-items-center py-16 text-dim"><Loader2 className="size-6 animate-spin" /></div>}
        {profile && models && (
          <section id="models" className="mt-6 scroll-mt-20 rounded-2xl bg-panel p-5">
            <h2 className="font-display text-[19px] font-bold">Choose models</h2>
            <p className="mb-4 mt-1 text-[13px] text-dim">
              {profile.models_verified_at ? "The current models have been verified." : "Bob checks the models automatically when a job starts."}{" "}
              <button onClick={() => void listModels()} disabled={loadingModels} className="text-bob-sky hover:underline disabled:opacity-50">
                {loadingModels ? "Loading models…" : "Show available models"}
              </button>
            </p>
            <ModelsEditor value={models} onChange={setModels} keys={keys} onKeys={setKeys} results={results} options={available} />
            <Button className="mt-4" busy={busy} disabled={!models.writer.model_id || !models.planner.model_id || !models.judge.model_id} onClick={save}>Save and check</Button>
          </section>
        )}
      </div>
    </AppShell>
  );
}
