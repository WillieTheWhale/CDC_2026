// AI-assisted: written with ChatGPT (OpenAI) and Claude Code (Anthropic). See docs/AI_USAGE.md.
"use client";
import GridLayout, { useContainerWidth } from "react-grid-layout";
export function Dock({ children }: { children: React.ReactNode }) {
  // Start from the real viewport rather than the library default (1280), so the first paint never overflows.
  const { width, containerRef, mounted } = useContainerWidth({
    initialWidth: typeof window === "undefined" ? 1024 : Math.min(window.innerWidth, 1280),
  });
  return (
    <div className="dock" ref={containerRef}>
      {mounted && (
        <GridLayout
          width={width}
          layout={
            width < 700
              ? [
                  { i: "risk", x: 0, y: 0, w: 12, h: 1 },
                  { i: "wire", x: 0, y: 1, w: 12, h: 1 },
                ]
              : [
                  { i: "risk", x: 0, y: 0, w: 6, h: 1 },
                  { i: "wire", x: 6, y: 0, w: 6, h: 1 },
                ]
          }
          gridConfig={{
            cols: 12,
            rowHeight: 235,
            margin: [0, 0],
            containerPadding: [0, 0],
          }}
          dragConfig={{ handle: ".panel-handle", enabled: width >= 700 }}
          resizeConfig={{ enabled: false }}
        >
          {children}
        </GridLayout>
      )}
    </div>
  );
}
