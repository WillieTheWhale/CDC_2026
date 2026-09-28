// AI-assisted: written with ChatGPT (OpenAI) and Claude Code (Anthropic). See docs/AI_USAGE.md.
import type { Person, PersonLegalOutcome } from "@/lib/people-types";

const LEGAL_LABEL: Record<PersonLegalOutcome, string> = {
  reported: "Reported", arrested: "Arrested", charged: "Charged", convicted: "Convicted",
  sentenced: "Sentenced", acquitted: "Acquitted", overturned: "Conviction overturned",
  dismissed: "Dismissed", sanctioned: "Sanctioned", delisted: "Delisted",
  extradited: "Extradited", released: "Released",
};
const STATUS_LABEL = {
  convicted: "Historical conviction cited",
  charged: "Historical charge cited",
  sanctioned: "Historical sanction cited",
  reported: "Reported by cited source",
};

export function personDisplayStatus(person: Person): { label: string; style: string; asOf?: string } {
  const final = person.legalHistory?.find((claim) =>
    ["acquitted", "overturned", "dismissed", "delisted"].includes(claim.status) && !claim.partial,
  );
  const laterAdverseOutcome = final && person.legalHistory?.some((claim) =>
    claim.date > final.date && ["charged", "convicted", "sentenced", "sanctioned"].includes(claim.status),
  );
  if (final && !laterAdverseOutcome && (!person.statusAsOf || final.date >= person.statusAsOf)) {
    return { label: LEGAL_LABEL[final.status], style: "reported", asOf: final.date };
  }
  return { label: STATUS_LABEL[person.status], style: person.status, asOf: person.statusAsOf };
}

export function PeopleLegalRecord({ person }: { person: Person }) {
  return <>
    {person.lifeStatus && <section className="people-legal-life" aria-label="Biographical note">
      <small>Biographical note</small>
      <strong>{person.lifeStatus.value === "deceased" ? "Deceased" : "Life status unknown"}</strong>
      {person.lifeStatus.deathDate && <span> · death reported {person.lifeStatus.deathDate}</span>}
      {person.lifeStatus.asOf && <span> · established by {person.lifeStatus.asOf}</span>}
      <a href={person.lifeStatus.source.url} target="_blank" rel="noreferrer">Source: {person.lifeStatus.source.publisher}: {person.lifeStatus.source.title}</a>
      {!person.lifeStatus.deathDate && person.lifeStatus.value === "deceased" && <small>Exact death date was not stated by this source.</small>}
      <small>This biographical fact does not change the cited legal status or legal history.</small>
    </section>}
    {!!person.legalHistory?.length && <section className="people-legal-history" aria-label="Documented legal history">
      <h3>Documented legal history</h3>
      <ol>{person.legalHistory.map((claim, index) => <li key={`${claim.status}-${claim.date}-${index}`}>
        <div><time dateTime={claim.date}>{claim.date}</time><strong>{LEGAL_LABEL[claim.status]}</strong>{claim.partial && <span>Some counts only</span>}</div>
        <p>{claim.qualifier}{claim.offense ? ` · ${claim.offense}` : ""}{claim.jurisdiction ? ` · ${claim.jurisdiction}` : ""}</p>
        <a href={claim.source.url} target="_blank" rel="noreferrer">{claim.source.publisher}: {claim.source.title}</a>
      </li>)}</ol>
      <p>Entries describe each cited case stage, newest first. An arrest or charge is an allegation, not a conviction, and a historical charge does not mean a case is still pending. &ldquo;Some counts only&rdquo; marks an outcome that the source applies to part of the case.</p>
    </section>}
  </>;
}
