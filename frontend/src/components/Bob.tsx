import { useEffect, useState } from "react";
import { motion, useReducedMotion } from "motion/react";

import hero from "../assets/bob/hero.webp";
import idle from "../assets/bob/idle.webp";
import wave1 from "../assets/bob/wave-1.webp";
import wave2 from "../assets/bob/wave-2.webp";
import think1 from "../assets/bob/think-1.webp";
import think2 from "../assets/bob/think-2.webp";
import idea from "../assets/bob/idea.webp";
import cheer1 from "../assets/bob/cheer-1.webp";
import cheer2 from "../assets/bob/cheer-2.webp";
import cheer3 from "../assets/bob/cheer-3.webp";
import dive1 from "../assets/bob/dive-1.webp";
import dive2 from "../assets/bob/dive-2.webp";
import dive3 from "../assets/bob/dive-3.webp";
import read1 from "../assets/bob/read-1.webp";
import read2 from "../assets/bob/read-2.webp";
import read3 from "../assets/bob/read-3.webp";
import type1 from "../assets/bob/type-1.webp";
import type2 from "../assets/bob/type-2.webp";
import type3 from "../assets/bob/type-3.webp";
import stamp1 from "../assets/bob/stamp-1.webp";
import stamp2 from "../assets/bob/stamp-2.webp";
import stamp3 from "../assets/bob/stamp-3.webp";
import nope1 from "../assets/bob/nope-1.webp";
import nope2 from "../assets/bob/nope-2.webp";
import nope3 from "../assets/bob/nope-3.webp";
import nope4 from "../assets/bob/nope-4.webp";
import point1 from "../assets/bob/point-1.webp";
import point2 from "../assets/bob/point-2.webp";
import carry1 from "../assets/bob/carry-1.webp";
import carry2 from "../assets/bob/carry-2.webp";
import carry3 from "../assets/bob/carry-3.webp";
import blink1 from "../assets/bob/blink-1.webp";
import blink2 from "../assets/bob/blink-2.webp";
import blink3 from "../assets/bob/blink-3.webp";
import sweat1 from "../assets/bob/sweat-1.webp";
import sweat2 from "../assets/bob/sweat-2.webp";
import sleep1 from "../assets/bob/sleep-1.webp";
import sleep2 from "../assets/bob/sleep-2.webp";

export type BobPose =
  | "hero"
  | "idle"
  | "wave"
  | "think"
  | "idea"
  | "cheer"
  | "dive"
  | "read"
  | "type"
  | "stamp"
  | "nope"
  | "point"
  | "carry"
  | "blink"
  | "sweat"
  | "sleep";

// Each pose is a short frame loop cut from the character sheets.
const POSES: Record<BobPose, { frames: string[]; ms: number }> = {
  hero: { frames: [hero], ms: 1000 },
  idle: { frames: [idle], ms: 1000 },
  wave: { frames: [wave1, wave2, wave1, wave2, idle], ms: 260 },
  think: { frames: [think1, think2], ms: 700 },
  idea: { frames: [idea], ms: 1000 },
  cheer: { frames: [cheer1, cheer2, cheer3, cheer2], ms: 220 },
  dive: { frames: [dive1, dive2, dive3], ms: 180 },
  read: { frames: [read1, read2, read3], ms: 450 },
  type: { frames: [type1, type2, type3], ms: 220 },
  stamp: { frames: [stamp1, stamp2, stamp3], ms: 260 },
  nope: { frames: [nope1, nope2, nope3, nope4], ms: 260 },
  point: { frames: [point1, point2], ms: 480 },
  carry: { frames: [carry1, carry2, carry3], ms: 300 },
  blink: { frames: [blink1, blink2, blink3], ms: 260 },
  sweat: { frames: [sweat1, sweat2], ms: 550 },
  sleep: { frames: [sleep1, sleep2], ms: 800 },
};

// Warm the cache so pose switches never flash.
for (const p of Object.values(POSES)) {
  for (const src of p.frames) {
    const img = new Image();
    img.src = src;
  }
}

interface BobProps {
  pose?: BobPose;
  size?: number;
  float?: boolean;
  /** Show one frame only (used inside the app, where motion stays minimal). */
  still?: boolean;
  className?: string;
}

export function Bob({ pose = "idle", size = 160, float = true, still = false, className }: BobProps) {
  const reduce = useReducedMotion() || still;
  const { frames, ms } = POSES[pose];
  const [i, setI] = useState(0);

  useEffect(() => {
    setI(0);
    if (frames.length < 2 || reduce) return;
    const id = window.setInterval(() => setI((n) => (n + 1) % frames.length), ms);
    return () => window.clearInterval(id);
  }, [pose, frames.length, ms, reduce]);

  return (
    <motion.div
      className={className}
      style={{ width: size, height: size }}
      animate={float && !reduce ? { y: [0, -6, 0] } : undefined}
      transition={{ duration: 3.2, repeat: Infinity, ease: "easeInOut" }}
    >
      <img
        src={frames[i % frames.length]}
        alt="Bob the Builder"
        width={size}
        height={size}
        draggable={false}
        className="pointer-events-none h-full w-full select-none object-contain"
      />
    </motion.div>
  );
}
