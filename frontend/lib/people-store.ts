// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
import manifest from "../data/people/manifest.json";
import countryFixture from "../../contracts/fixtures/countries.json";
import { normalizeDataset } from "./people-api";
import type { PeopleCountry } from "./people-types";

// This module is imported only by route handlers; the browser receives bounded JSON pages.
export const peopleDataset = normalizeDataset(manifest);
export const peopleCountries = countryFixture.data.map((country) => ({
  iso3: country.iso3,
  name: country.name,
  lat: country.lat,
  lon: country.lon,
})) as PeopleCountry[];
