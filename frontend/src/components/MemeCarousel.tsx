import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Bob, type BobPose } from "./Bob";

// Drop images into src/assets/memes/ and they join the rotation automatically.
// Caption comes from the filename: "bob-reads-the-terms-of-service.webp"
// becomes "Bob reads the terms of service". Optional captions.json can
// override: { "file-name.webp": "Custom caption" }.
const files = import.meta.glob("../assets/memes/*.{png,jpg,jpeg,webp,gif,avif}", { eager: true, import: "default" }) as Record<string, string>;
const captionOverrides = (Object.values(import.meta.glob("../assets/memes/captions.json", { eager: true, import: "default" }))[0] ?? {}) as Record<string, string>;

type Slide = { kind: "image"; src: string; caption: string } | { kind: "pose"; pose: BobPose; caption: string };

// Placeholder slides until the meme images land.
const FALLBACK: Slide[] = [
  { kind: "pose", pose: "think", caption: "Bob reading row 4,812 of the terms of service" },
  { kind: "pose", pose: "idea", caption: "When the docs finally say what the default timeout is" },
  { kind: "pose", pose: "cheer", caption: "Zero hallucinations. Bob deserves a snack." },
  { kind: "pose", pose: "wave", caption: "Bob waving goodbye to the rows that made stuff up" },
  { kind: "pose", pose: "think", caption: "“Is this a fact or is this marketing?”" },
  { kind: "pose", pose: "hero", caption: "One cube of verified data, freshly built" },
];

function captionFromPath(path: string): string {
  const name = path.split("/").pop() ?? "";
  if (captionOverrides[name]) return captionOverrides[name];
  const base = name.replace(/\.[^.]+$/, "").replace(/[-_]+/g, " ").trim();
  return base.charAt(0).toUpperCase() + base.slice(1);
}

export function MemeCarousel({ intervalMs = 5200, compact = false }: { intervalMs?: number; compact?: boolean }) {
  const slides = useMemo<Slide[]>(() => {
    const imgs = Object.entries(files).map(([p, src]) => ({ kind: "image" as const, src, caption: captionFromPath(p) }));
    return imgs.length ? imgs : FALLBACK;
  }, []);
  const [i, setI] = useState(() => Math.floor(Math.random() * slides.length));

  useEffect(() => {
    const id = window.setInterval(() => setI((n) => (n + 1) % slides.length), intervalMs);
    return () => window.clearInterval(id);
  }, [slides.length, intervalMs]);

  const s = slides[i];
  const size = compact ? 110 : 150;
  return (
    <div className="flex flex-col items-center text-center">
      <div className="relative grid place-items-center" style={{ height: size + 8, width: "100%" }}>
        <AnimatePresence mode="wait">
          <motion.div
            key={i}
            initial={{ opacity: 0, scale: 0.9, rotate: -3 }}
            animate={{ opacity: 1, scale: 1, rotate: 0 }}
            exit={{ opacity: 0, scale: 0.9, rotate: 3 }}
            transition={{ duration: 0.35 }}
          >
            {s.kind === "image" ? (
              <img src={s.src} alt={s.caption} className="max-w-full rounded-xl object-contain" style={{ maxHeight: size }} />
            ) : (
              <Bob pose={s.pose} size={size} />
            )}
          </motion.div>
        </AnimatePresence>
      </div>
      <AnimatePresence mode="wait">
        <motion.p
          key={i}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -6 }}
          className="mt-2 max-w-[260px] text-[12.5px] italic text-dim"
        >
          {s.caption}
        </motion.p>
      </AnimatePresence>
    </div>
  );
}
