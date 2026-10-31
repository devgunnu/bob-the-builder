import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router";
import { Check, Copy, Download, Loader2 } from "lucide-react";
import { api, ApiError } from "../api/client";
import type { AvailableModel, AwsSetup, BedrockAccess, ModelRoles, UserProfile } from "../api/types";
import { AppShell } from "../components/AppShell";
import { Bob } from "../components/Bob";
import { ModelsEditor } from "../components/ModelsEditor";
import { Button, ErrorBanner, Label, useTitle } from "../components/ui";

function Copyable({ text, mono = true }: { text: string; mono?: boolean }) {
  const [done, setDone] = useState(false);
  return (
    <span className="group flex min-w-0 items-center gap-2 rounded-lg bg-void px-3 py-2">
      <span className={`min-w-0 flex-1 break-all text-[12.5px] text-white/90 ${mono ? "font-mono" : ""}`}>{text}</span>
      <button
        aria-label="Copy"
        onClick={() => navigator.clipboard.writeText(text).then(() => (setDone(true), setTimeout(() => setDone(false), 1500)))}
        className="shrink-0 text-dim hover:text-white"
      >
        {done ? <Check className="size-4 text-bob-mint" /> : <Copy className="size-4" />}
      </button>
    </span>
  );
}

function StepCard({ id, n, title, done, children }: { id: string; n: number; title: string; done: boolean; children: ReactNode }) {
  return (
    <section id={id} className="scroll-mt-20 rounded-2xl bg-panel p-5">
      <div className="mb-4 flex items-center gap-3">
        <span className={`grid size-8 place-items-center rounded-full font-display text-[15px] font-bold ${done ? "bg-bob-mint text-bob-navy" : "bg-white/10 text-white"}`}>
          {done ? <Check className="size-4" /> : n}
        </span>
        <h2 className="font-display text-[19px] font-bold">{title}</h2>
        <span className={`ml-auto rounded-full px-2.5 py-1 text-[11.5px] ${done ? "bg-bob-mint/10 text-bob-mint" : "bg-bob-yellow/10 text-bob-yellow"}`}>{done ? "Verified" : "Not verified yet"}</span>
      </div>
      {children}
    </section>
  );
}

export default function AccountScreen() {
  useTitle("Account");
  const [me, setMe] = useState<UserProfile | null>(null);
  const [setup, setSetup] = useState<AwsSetup | null>(null);
  const [loadErr, setLoadErr] = useState<ApiError | null>(null);

  // AWS access form
  const [roleArn, setRoleArn] = useState("");
  const [region, setRegion] = useState("");
  const [awsBusy, setAwsBusy] = useState(false);
  const [awsMsg, setAwsMsg] = useState<{ ok: boolean; text: string } | null>(null);

  // Models form
  const [models, setModels] = useState<ModelRoles | null>(null);
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [modelBusy, setModelBusy] = useState(false);
  const [modelResults, setModelResults] = useState<Record<string, string> | null>(null);
  const [modelErr, setModelErr] = useState<ApiError | null>(null);
  const [available, setAvailable] = useState<AvailableModel[] | null>(null);
  const [availBusy, setAvailBusy] = useState(false);
  const [availErr, setAvailErr] = useState<ApiError | null>(null);
  const loadAvailable = async () => {
    setAvailBusy(true);
    setAvailErr(null);
    try {
      setAvailable(await api.availableModels());
    } catch (e) {
      setAvailErr(e as ApiError);
    } finally {
      setAvailBusy(false);
    }
  };

  useEffect(() => {
    Promise.all([api.me(), api.awsSetup()])
      .then(([p, st]) => {
        setMe(p);
        setSetup(st);
        setRoleArn(p.bedrock?.role_arn ?? "");
        setRegion(p.bedrock?.region ?? "us-east-1");
        setModels(p.models);
      })
      .catch(setLoadErr);
  }, []);

  useEffect(() => {
    if (me && window.location.hash) document.querySelector(window.location.hash)?.scrollIntoView({ behavior: "smooth" });
  }, [me]);

  const saveAws = async () => {
    setAwsBusy(true);
    setAwsMsg(null);
    try {
      const access: BedrockAccess = localMode
        ? { mode: "default", region: region.trim() }
        : { mode: "assume_role", role_arn: roleArn.trim(), external_id: me?.external_id ?? null, region: region.trim() };
      const p = await api.saveAws(access);
      setMe(p);
      const v = await api.verifyAws();
      setAwsMsg(v.ok ? { ok: true, text: "Bob can reach Bedrock in your account." } : { ok: false, text: v.error ?? "Verification failed." });
      setMe(await api.me());
    } catch (e) {
      setAwsMsg({ ok: false, text: (e as ApiError).message });
    } finally {
      setAwsBusy(false);
    }
  };

  const saveModels = async () => {
    if (!models) return;
    setModelBusy(true);
    setModelErr(null);
    setModelResults(null);
    try {
      const p = await api.saveModels(models, Object.fromEntries(Object.entries(keys).filter(([, v]) => v)));
      setKeys({});
      setModels(p.models);
      const v = await api.verifyModels();
      setModelResults(v.roles);
      setMe(await api.me());
    } catch (e) {
      setModelErr(e as ApiError);
    } finally {
      setModelBusy(false);
    }
  };

  const awsOk = !!me?.bedrock_verified_at;
  // Local development (BOB_BEDROCK_AUTH=default): Bob uses this machine's AWS credentials, no role.
  const localMode = me?.bedrock?.mode === "default";
  const modelsOk = !!me?.models_verified_at;

  return (
    <AppShell title="Account">
      <div className="mx-auto max-w-3xl px-4 py-8">
        <div className="mb-6 flex items-center gap-4">
          <Bob pose={awsOk && modelsOk ? "hero" : "idea"} size={72} float={false} still />
          <div>
            <h1 className="font-display text-[28px] font-extrabold leading-tight">Your account</h1>
            <p className="text-[14px] text-dim">
              {awsOk && modelsOk ? (
                <>You're all set. <Link to="/" className="text-bob-sky hover:underline">Start a dataset</Link></>
              ) : (
                "Two quick steps before your first job. Bedrock runs and bills in your own AWS account."
              )}
            </p>
          </div>
        </div>

        <ErrorBanner error={loadErr} title="Couldn't load your account" />
        {!me && !loadErr && <div className="grid place-items-center py-16 text-dim"><Loader2 className="size-6 animate-spin" /></div>}

        {me && setup && (
          <div className="space-y-5">
            <StepCard id="aws" n={1} title="Connect AWS" done={awsOk}>
              {localMode ? (
                <div className="space-y-3 text-[13.5px]">
                  <p className="text-white/85">Local mode. Bob calls Bedrock with this machine's AWS credentials, so there is no role to deploy. Pick the region and check it.</p>
                  <div className="flex flex-wrap items-center gap-2">
                    <input value={region} onChange={(e) => setRegion(e.target.value)} placeholder="us-east-1" aria-label="Bedrock region" className="w-40 rounded-lg border border-line bg-transparent px-3 py-2 font-mono text-[12.5px] outline-none" />
                    <Button busy={awsBusy} disabled={!region.trim()} onClick={saveAws}>Check access</Button>
                  </div>
                  {awsMsg && (
                    <div className={`rounded-lg px-3 py-2 text-[12.5px] ${awsMsg.ok ? "bg-bob-mint/10 text-bob-mint" : "bg-rose-400/10 font-mono text-rose-200"}`}>{awsMsg.text}</div>
                  )}
                </div>
              ) : (
              <ol className="space-y-5 text-[13.5px]">
                <li>
                  <div className="mb-2 text-white/85"><b className="text-white">a.</b> Download the access template. It creates one role that can only call Bedrock.</div>
                  <Button tone="ghost" onClick={() => api.downloadTemplate().catch((e) => setAwsMsg({ ok: false, text: e.message }))}>
                    <Download className="size-4" /> bedrock-role.yaml
                  </Button>
                </li>
                <li>
                  <div className="mb-2 text-white/85"><b className="text-white">b.</b> Deploy it in your AWS account:</div>
                  <Copyable text={setup.cli_command} />
                  <div className="mt-2 grid gap-2 sm:grid-cols-2">
                    <div>
                      <Label>Bob's account id</Label>
                      {setup.bob_account_id ? <Copyable text={setup.bob_account_id} /> : <p className="rounded-lg bg-void px-3 py-2 text-[12.5px] text-bob-yellow">Not set on the server (BOB_ACCOUNT_ID). Ask the team for it.</p>}
                    </div>
                    <div><Label>Your external id</Label><Copyable text={setup.external_id} /></div>
                  </div>
                </li>
                <li>
                  <div className="mb-2 text-white/85"><b className="text-white">c.</b> Paste the role it created, then check it.</div>
                  <div className="grid gap-2 sm:grid-cols-[1fr_160px]">
                    <input value={roleArn} onChange={(e) => setRoleArn(e.target.value)} placeholder="arn:aws:iam::123456789012:role/BobBedrockAccess" aria-label="Role ARN" className="rounded-lg border border-line bg-transparent px-3 py-2 font-mono text-[12.5px] outline-none placeholder:text-dim" />
                    <input value={region} onChange={(e) => setRegion(e.target.value)} placeholder="us-east-1" aria-label="Bedrock region" className="rounded-lg border border-line bg-transparent px-3 py-2 font-mono text-[12.5px] outline-none" />
                  </div>
                  <Button className="mt-3" busy={awsBusy} disabled={!roleArn.trim() || !region.trim()} onClick={saveAws}>Save and check</Button>
                  {awsMsg && (
                    <div className={`mt-3 rounded-lg px-3 py-2 text-[12.5px] ${awsMsg.ok ? "bg-bob-mint/10 text-bob-mint" : "bg-rose-400/10 font-mono text-rose-200"}`}>{awsMsg.text}</div>
                  )}
                </li>
              </ol>
              )}
            </StepCard>

            <StepCard id="models" n={2} title="Choose models" done={modelsOk}>
              <p className="mb-3 text-[13px] text-dim">
                Any Bedrock model id or inference profile works. The defaults are filled in.
                {awsOk && !available && (
                  <button onClick={() => void loadAvailable()} disabled={availBusy} className="ml-1 text-bob-sky hover:underline disabled:opacity-50">
                    {availBusy ? "Loading your models…" : "Show the models in your account"}
                  </button>
                )}
                {available && <span className="ml-1 text-bob-mint">{available.length} models available as suggestions.</span>}
              </p>
              <ErrorBanner error={availErr} title="Couldn't list your Bedrock models" />
              {models && <ModelsEditor value={models} onChange={setModels} keys={keys} onKeys={setKeys} results={modelResults} options={available} />}
              <ErrorBanner error={modelErr} title="Couldn't save the models" />
              <Button className="mt-3" busy={modelBusy} disabled={!models?.writer.model_id || !models?.planner.model_id || !models?.judge.model_id} onClick={saveModels}>
                Save and check
              </Button>
              {!awsOk && <p className="mt-2 text-[12px] text-dim">Tip: connect AWS first, since Bedrock models are checked through your account.</p>}
            </StepCard>
          </div>
        )}
      </div>
    </AppShell>
  );
}
