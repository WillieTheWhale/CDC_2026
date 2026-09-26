// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
"use client";
import GridLayout, { useContainerWidth } from "react-grid-layout";
export function Dock({ children }: { children: React.ReactNode }) {
  const { width, containerRef, mounted } = useContainerWidth();
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
