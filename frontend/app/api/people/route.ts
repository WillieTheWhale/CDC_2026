// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
import { peopleCountries, peopleDataset } from "@/lib/people-store";
import { parsePeopleQuery, queryPeople } from "@/lib/people-query";

export async function GET(request: Request) {
  try {
    const query = parsePeopleQuery(new URL(request.url).searchParams);
    return Response.json(queryPeople(peopleDataset, peopleCountries, query));
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "Invalid query" }, { status: 400 });
  }
}
