import { useCallback, useState } from "react";
import { AnimatePresence, LayoutGroup, motion } from "motion/react";
import { Composer } from "./components/Composer";
import { LandingBackdrop, LandingField, LandingHeader } from "./components/Landing";
import { Workspace } from "./components/workspace/Workspace";
import { mockClient } from "./lib/mockEngine";

// Swap for the real API client once the backend is up.
const client = mockClient;
const SIMULATED = true;

type Phase = "landing" | "blackout" | "workspace";

// Timing of the enter transition (ms).
const BLACKOUT_HOLD = 2100;

export default function App() {
  const [phase, setPhase] = useState<Phase>("landing");
  const [job, setJob] = useState<{ prompt: string; files: File[] } | null>(null);

  const start = useCallback((prompt: string, files: File[]) => {
    setJob({ prompt, files });
    setPhase("blackout");
    window.setTimeout(() => setPhase("workspace"), BLACKOUT_HOLD);
  }, []);

  return (
    <LayoutGroup>
      <div className="relative h-full overflow-hidden">
        {/* Landing world */}
        <AnimatePresence>
          {phase === "landing" && (
            <motion.div key="backdrop" className="absolute inset-0" exit={{ opacity: 0, transition: { duration: 0.6 } }}>
              <LandingBackdrop />
            </motion.div>
          )}
        </AnimatePresence>
        <AnimatePresence>{phase === "landing" && <LandingField key="field" />}</AnimatePresence>

        {/* The room goes black */}
        <motion.div
          className="pointer-events-none absolute inset-0 bg-void"
          initial={false}
          animate={{ opacity: phase === "landing" ? 0 : 1 }}
          transition={{ duration: 0.7, ease: "easeInOut" }}
        />

        {/* Centre stage: header + composer (landing and blackout) */}
        {phase !== "workspace" && (
          <div className="absolute inset-0 flex flex-col items-center justify-center px-4">
            <AnimatePresence>{phase === "landing" && <LandingHeader key="header" />}</AnimatePresence>
            <Composer
              variant="landing"
              intensity={phase === "blackout" ? "bright" : "calm"}
              locked={phase === "blackout" ? job?.prompt : undefined}
              onSubmit={start}
            />
            <AnimatePresence>
              {phase === "landing" && (
                <motion.p
                  key="hint"
                  className="mt-5 text-center text-[12.5px] text-bob-navy/45"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1, transition: { delay: 0.8 } }}
                  exit={{ opacity: 0, transition: { duration: 0.2 } }}
                >
                  Paste a link, attach files, or press <kbd className="font-mono">Enter</kbd> to try the suggestion
                </motion.p>
              )}
            </AnimatePresence>
          </div>
        )}

        {/* Workspace: the composer flies into the chat panel */}
        {phase === "workspace" && job && (
          <div className="absolute inset-0">
            <Workspace
              client={client}
              simulated={SIMULATED}
              prompt={job.prompt}
              files={job.files}
              renderComposer={(send) => <Composer variant="workspace" onSubmit={(t) => send(t)} />}
            />
          </div>
        )}
      </div>
    </LayoutGroup>
  );
}
