// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
import type { NextConfig } from "next";
import path from "node:path";
const config: NextConfig = {
  devIndicators: false,
  turbopack: { root: path.resolve(process.cwd(), "..") },
  outputFileTracingRoot: path.resolve(process.cwd(), ".."),
};
export default config;
