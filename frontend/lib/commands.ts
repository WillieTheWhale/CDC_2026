// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
import type { CommandAction } from "./types";
export function parseCommand(input: string, countries: string[]): CommandAction | null {
  const text = input.trim().toUpperCase().replace(/\s+/g," ");
  if (/LEAST.?MONITOR|WEAK(EST)? (ENFORCEMENT|CUSTOMS)|AVOID (DETECTION|POLICE)|SAFEST (PATH|ROUTE)|EVADE/.test(text)) return {intent:"blocked",params:{},message:"TRACE supports public health and prevention. Try a risk or country query."};
  let m;
  if ((m=text.match(/^(COCAINE|HEROIN|METH|CANNABIS|ALL) ROUTES$/))) return {intent:"routes",params:{drug:m[1]==="ALL"?"all":m[1].toLowerCase()}};
  if ((m=text.match(/^([A-Z]{3})(?:\s*(?:<GO>|GO))?$/)) && countries.includes(m[1])) return {intent:"country",params:{iso3:m[1]}};
  if ((m=text.match(/^RISK(?: TOP (\d+))?$/))) return {intent:"risk",params:{limit:Number(m[1]??250)}};
  if ((m=text.match(/^YEAR (\d{4})$/))) return {intent:"year",params:{year:Number(m[1])}};
  if ((m=text.match(/^PREDICT (ON|OFF)$/))) return {intent:"predict",params:{enabled:m[1]==="ON"}};
  if ((m=text.match(/^NEWS(?: (COCAINE|HEROIN|METH|CANNABIS))?$/))) return {intent:"news",params:{drug:m[1]?.toLowerCase()??"all"}};
  if ((m=text.match(/^COMPARE ([A-Z]{3}) ([A-Z]{3})$/)) && countries.includes(m[1]) && countries.includes(m[2])) return {intent:"compare",params:{iso3s:[m[1],m[2]]}};
  if (text.startsWith("SHOCK ")) return {intent:"shock",params:{scenario:input.trim().slice(6)}};
  if (/^(PRICES|MARKETS)$/.test(text)) return {intent:"prices",params:{}};
  if (/^(EXPERIMENT|AFGHAN BAN|METRICS)$/.test(text)) return {intent:"experiment",params:{}};
  return null;
}
