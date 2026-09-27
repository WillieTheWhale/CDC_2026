// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
import type { Connection, PeopleDataset, Person } from "@/lib/people-types";

interface PeopleGraphProps {
  dataset: PeopleDataset;
  selectedId: string | null;
  onSelect: (person: Person) => void;
  totalConnections?: number | null;
}

export function PeopleGraph({ dataset, selectedId, onSelect, totalConnections }: PeopleGraphProps) {
  const selected = dataset.people.find((person) => person.id === selectedId);
  const relevant = selected
    ? dataset.connections.filter((edge) => edge.fromId === selected.id || edge.toId === selected.id)
    : [];
  const edges = relevant.slice(0, 48);
  const nodesById = new Map<string, Person>();
  if (selected) nodesById.set(selected.id, selected);
  for (const edge of edges) {
    const id = edge.fromId === selected?.id ? edge.toId : edge.fromId;
    const person = dataset.people.find((item) => item.id === id);
    if (person) nodesById.set(person.id, person);
  }
  const neighbors = [...nodesById.values()].filter((person) => person.id !== selectedId).slice(0, 48);
  const nodes = selected ? [selected, ...neighbors] : [];
  const positions = new Map<string, { x: number; y: number }>();
  if (selected) positions.set(selected.id, { x: 500, y: 292 });
  neighbors.forEach((person, index) => {
    const angle = (index / Math.max(neighbors.length, 1)) * Math.PI * 2 - Math.PI / 2;
    positions.set(person.id, {
      x: 500 + Math.cos(angle) * 360,
      y: 292 + Math.sin(angle) * 210,
    });
  });
  const personById = new Map(nodes.map((person) => [person.id, person]));
  const visibleEdges = edges.filter((edge) => personById.has(edge.fromId) && personById.has(edge.toId));

  if (!selected) {
    return <div className="people-graph-empty">Choose a sourced person to inspect their documented connections.</div>;
  }

  return (
    <div className="people-graph-wrap">
      <div className="people-graph-heading">
        <span>{nodes.length} people · {visibleEdges.length} documented claims</span>
        {(totalConnections ?? relevant.length) > edges.length && <span>Showing {edges.length} of {(totalConnections ?? relevant.length).toLocaleString()} cited claims</span>}
      </div>
      <svg className="people-graph" viewBox="0 0 1000 585" role="img" aria-label={`Sourced connection graph centered on ${selected.name}`}>
        {visibleEdges.map((edge: Connection) => {
          const from = positions.get(edge.fromId);
          const to = positions.get(edge.toId);
          if (!from || !to) return null;
          return <g key={edge.id}>
            <line x1={from.x} y1={from.y} x2={to.x} y2={to.y} />
            <title>{edge.label} · cited source</title>
          </g>;
        })}
        {nodes.map((person) => {
          const point = positions.get(person.id)!;
          const center = person.id === selected.id;
          return <g key={person.id} className={center ? "is-center" : ""} role="button" tabIndex={0} aria-label={`Select ${person.name}`} onClick={() => onSelect(person)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") onSelect(person); }}>
            <circle cx={point.x} cy={point.y} r={center ? 36 : 27} />
            <text x={point.x} y={point.y + 4} textAnchor="middle">{person.name.slice(0, 1).toUpperCase()}</text>
            <text className="people-graph-name" x={point.x} y={point.y + (center ? 58 : 47)} textAnchor="middle">{person.name}</text>
          </g>;
        })}
      </svg>
      <ul className="people-graph-claims">
        {visibleEdges.map((edge) => {
          const otherId = edge.fromId === selected.id ? edge.toId : edge.fromId;
          const other = personById.get(otherId);
          return <li key={edge.id}>
            <button onClick={() => other && onSelect(other)}>{edge.label}</button>
            <span>{other?.name}</span>
            <small><a href={edge.sources[0]?.url} target="_blank" rel="noreferrer">{edge.sources[0]?.publisher}: {edge.sources[0]?.title}</a></small>
          </li>;
        })}
      </ul>
      <p className="people-graph-caution">Every line is a claim made by its cited source. A documented connection alone is not proof of guilt.</p>
    </div>
  );
}
