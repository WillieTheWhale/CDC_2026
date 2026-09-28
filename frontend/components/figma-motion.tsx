// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
"use client";
import { motion, useReducedMotion } from "motion/react";

// Figma 2:37, from get_motion_context. Shared by the React beacon and the
// equivalent CSS ring used inside MapLibre's DOM markers.
const pulseTrack = {
  duration: 2,
  times: [0, 0.25, 0.5, 0.75, 0.9999, 1],
  ease: "linear" as const,
  repeat: Infinity,
};
export function SignalBeacon() {
  const reduced = useReducedMotion();
  return (
    <div className="signal-beacon" data-node-id="2:36" aria-hidden="true">
      <motion.div
        className="signal-ring"
        data-node-id="2:37"
        initial={
          reduced ? false : { opacity: 0.65, scaleX: 0.65, scaleY: 0.65 }
        }
        animate={
          reduced
            ? { opacity: 0.4, scaleX: 1, scaleY: 1 }
            : {
                opacity: [
                  0.65, 0.60413, 0.42993000000000003, 0.17337, 0.02817, 0,
                ],
                scaleX: [0.65, 0.717, 0.972, 1.347, 1.559, 1.6],
                scaleY: [0.65, 0.717, 0.972, 1.347, 1.559, 1.6],
              }
        }
        transition={
          reduced
            ? { duration: 0 }
            : { opacity: pulseTrack, scaleX: pulseTrack, scaleY: pulseTrack }
        }
      >
        <img src="/figma/signal-ring.svg" alt="" />
      </motion.div>
      <img
        className="signal-carrier"
        src="/figma/signal-carrier.svg"
        alt=""
        data-node-id="2:38"
      />
      <img
        className="signal-core"
        src="/figma/signal-core.svg"
        alt=""
        data-node-id="2:39"
      />
    </div>
  );
}

// The exact exported path from Figma 2:50; path-level motion requires it inline.
export function RouteStudy() {
  const reduced = useReducedMotion();
  return (
    <svg
      className="route-study"
      width="280"
      height="140"
      viewBox="0 0 280 140"
      fill="none"
      role="img"
      aria-label="Animated corridor between two endpoints"
      data-node-id="2:49"
    >
      <motion.path
        data-node-id="2:50"
        d="M16 118C62 -20 200 -20 264 118"
        stroke="#DF4B27"
        strokeWidth="1.5"
        pathLength={1}
        initial={
          reduced ? false : { strokeDasharray: "0 1", strokeDashoffset: 0 }
        }
        animate={{ strokeDasharray: reduced ? "1 1" : ["0 1", "1 1", "1 1"] }}
        transition={
          reduced
            ? { duration: 0 }
            : {
                duration: 2,
                ease: ["easeOut", "linear"],
                times: [0, 0.6, 1],
                repeat: Infinity,
              }
        }
      />
      <circle data-node-id="2:53" cx="16" cy="118" r="4" fill="#DF4B27" />
      <circle data-node-id="2:54" cx="264" cy="118" r="4" fill="#8B358B" />
    </svg>
  );
}
