import { useCallback, useEffect, useState } from "react";
import { AnimatePresence, LayoutGroup, motion, useReducedMotion } from "motion/react";
import { AppShell } from "../components/AppShell";
import { Bob } from "../components/Bob";
import { Composer } from "../components/Composer";
import { LandingBackdrop, LandingField, LandingHeader } from "../components/Landing";
import { SetupScreen } from "./Setup";

type Phase = "landing" | "blackout" | "setup";

// How long the room stays black with only the glowing bar (ms).
const BLACKOUT_HOLD = 2100;

/** Route "/": landing -> blackout -> Setup. The composer morphs between them (layoutId="composer"). */
export default function Home() {
  const [phase, setPhase] = useState<Phase>("landing");
  const [goal, setGoal] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [sleeping, setSleeping] = useState(false);
  const reduceMotion = useReducedMotion() ?? false;

  useEffect(() => {
    if (phase !== "landing") {
      setSleeping(false);
      return;
    }
    let timeout = window.setTimeout(() => setSleeping(true), 60_000);
    const wake = () => {
      setSleeping(false);
      window.clearTimeout(timeout);
      timeout = window.setTimeout(() => setSleeping(true), 60_000);
    };
    const events: (keyof WindowEventMap)[] = ["keydown", "pointerdown", "pointermove", "touchstart"];
    events.forEach((event) => window.addEventListener(event, wake));
    return () => {
      window.clearTimeout(timeout);
      events.forEach((event) => window.removeEventListener(event, wake));
    };
  }, [phase]);

  const enter = useCallback((text: string, picked: File[]) => {
    setGoal(text);
    setFiles(picked);
    setPhase("blackout");
    window.setTimeout(() => setPhase("setup"), BLACKOUT_HOLD);
  }, []);

  return (
    <LayoutGroup>
      <div className="relative h-full overflow-hidden">
        <AnimatePresence>
          {phase === "landing" && (
            <motion.div key="backdrop" className="absolute inset-0" exit={{ opacity: 0, transition: { duration: 0.6 } }}>
              <LandingBackdrop />
            </motion.div>
          )}
        </AnimatePresence>
        <AnimatePresence>{phase === "landing" && <LandingField key="field" />}</AnimatePresence>

        {/* the room goes black */}
        <motion.div
          className="pointer-events-none absolute inset-0 bg-void"
          initial={false}
          animate={{ opacity: phase === "landing" ? 0 : 1 }}
          transition={{ duration: 0.7, ease: "easeInOut" }}
        />

        {phase !== "setup" && (
          <div className="absolute inset-0 flex flex-col items-center justify-center px-4">
            <AnimatePresence>{phase === "landing" && <LandingHeader key="header" sleeping={sleeping} />}</AnimatePresence>
            <Composer variant="landing" intensity={phase === "blackout" ? "bright" : "calm"} locked={phase === "blackout" ? goal : undefined} onSubmit={enter} />
            <AnimatePresence>
              {phase === "landing" && (
                <motion.p
                  key="hint"
                  className="mt-5 text-center text-[12.5px] text-bob-navy/45"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1, transition: { delay: 0.8 } }}
                  exit={{ opacity: 0, transition: { duration: 0.2 } }}
                >
                  Describe your dataset, paste a docs link, or press <kbd className="font-mono">Enter</kbd> to try the suggestion
                </motion.p>
              )}
            </AnimatePresence>
          </div>
        )}

        <AnimatePresence>
          {phase === "blackout" && (
            <motion.div
              key="dive"
              className="pointer-events-none absolute left-1/2 top-1/2 z-10 -ml-16 -mt-40"
              initial={reduceMotion ? false : { opacity: 0, x: -28, y: -180, rotate: -20, scale: 0.8 }}
              animate={reduceMotion ? { opacity: 1, y: 80 } : { opacity: [0, 1, 1, 0], x: [-28, -8, 0, 8], y: [-180, -100, 42, 92], rotate: [-20, -12, 8, 18], scale: [0.8, 1, 1, 0.7] }}
              transition={reduceMotion ? { duration: 0 } : { duration: 1.15, ease: "easeInOut" }}
            >
              <Bob pose="dive" size={128} float={false} still={reduceMotion} />
            </motion.div>
          )}
        </AnimatePresence>

        {phase === "setup" && (
          <motion.div className="absolute inset-0" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.4 }}>
            <AppShell pose="idea" title="New dataset" step="sources">
              <SetupScreen
                goal={goal}
                initialFiles={files}
                composer={(create, onFiles, busy) => (
                  <Composer
                    variant="workspace"
                    value={goal}
                    onValueChange={setGoal}
                    keepOnSubmit
                    disabled={busy}
                    onFiles={onFiles}
                    placeholder="What should the dataset teach a model to do?"
                    onSubmit={() => create()}
                  />
                )}
              />
            </AppShell>
          </motion.div>
        )}
      </div>
    </LayoutGroup>
  );
}
