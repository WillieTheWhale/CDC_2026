// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
// Local QA utility: receives a screenshot captured by the connected browser.
// It does not automate or capture the browser itself. Bind to loopback only.
import http from "node:http";
import { mkdirSync, writeFileSync } from "node:fs";
const dir = new URL("../design/qa/", import.meta.url);
mkdirSync(dir, { recursive: true });
http
  .createServer(async (req, res) => {
    if (req.method === "GET") {
      res.setHeader("Content-Type", "text/html; charset=utf-8");
      res.end(
        '<form method="post"><label>Screenshot name <input name="name" value="atlas-desktop"></label><label>Image data <textarea name="image"></textarea></label><button>Save screenshot</button></form>',
      );
      return;
    }
    let input = "";
    for await (const part of req) {
      input += part;
      if (input.length > 12000000) {
        res.writeHead(413).end();
        return;
      }
    }
    const fields = new URLSearchParams(input),
      name = fields.get("name") ?? "capture";
    if (!/^[a-z0-9-]{1,50}$/.test(name)) {
      res.writeHead(400).end("Invalid name");
      return;
    }
    const bytes = Buffer.from(fields.get("image") ?? "", "base64");
    const ext =
      bytes.subarray(1, 4).toString() === "PNG"
        ? "png"
        : bytes[0] === 255 && bytes[1] === 216
          ? "jpg"
          : null;
    if (bytes.length < 8 || !ext) {
      res.writeHead(400).end("PNG or JPEG required");
      return;
    }
    writeFileSync(new URL(`${name}.${ext}`, dir), bytes);
    res.setHeader("Content-Type", "text/plain");
    res.end(`Saved ${name}.${ext} (${bytes.length} bytes)`);
  })
  .listen(8766, "127.0.0.1", () =>
    console.log("Screenshot save form: http://127.0.0.1:8766"),
  );
