// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
import type { Metadata } from "next";
import "maplibre-gl/dist/maplibre-gl.css";
import "react-grid-layout/css/styles.css";
import "./globals.css";
export const metadata: Metadata = {
  title: "TRACE · Global drug trade atlas",
  description:
    "An interactive research atlas for drug-trade exposure, community vulnerability, and harm prevention.",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <link rel="stylesheet" href="https://use.typekit.net/jzx3gtq.css" />
        <link rel="icon" href="/figma/trace-mark.svg" />
      </head>
      <body>{children}</body>
    </html>
  );
}
