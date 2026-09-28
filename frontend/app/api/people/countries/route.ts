// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
import { peopleDataset } from "@/lib/people-store";
import { queryCountryCounts } from "@/lib/people-query";

export async function GET(request: Request) {
  const search = new URL(request.url).searchParams.get("search")?.trim() ?? "";
  if (search.length > 120) return Response.json({ error: "search must be 120 characters or fewer" }, { status: 400 });
  const zoom = Number(new URL(request.url).searchParams.get("zoom") ?? "3");
  if (![1, 2, 3].includes(zoom)) return Response.json({ error: "zoom must be 1, 2, or 3" }, { status: 400 });
  return Response.json({ data: queryCountryCounts(peopleDataset, search, zoom as 1 | 2 | 3) });
}
