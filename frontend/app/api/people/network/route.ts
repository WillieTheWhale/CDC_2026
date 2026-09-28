// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
import { peopleDataset } from "@/lib/people-store";
import { queryPersonNetwork } from "@/lib/people-query";

export async function GET(request: Request) {
  const personId = new URL(request.url).searchParams.get("person_id");
  if (!personId || personId.length > 160) return Response.json({ error: "person_id is required" }, { status: 400 });
  const network = queryPersonNetwork(peopleDataset, personId);
  if (!network) return Response.json({ error: "Person not found" }, { status: 404 });
  return Response.json({ data: network.data, meta: {
    total: network.data.people.length,
    total_connections: network.totalConnections,
    next_cursor: null,
  } });
}
