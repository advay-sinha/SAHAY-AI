import { turnNumber } from "../../console/logic";
import type { PacketTurn, SourcedField, StructuredRecord } from "../../types/packet";

/** Every structured field links back to the utterance that produced it. */
export function StructuredPanel({
  record,
  transcript,
  onEvidence,
}: {
  record: StructuredRecord;
  transcript: PacketTurn[];
  onEvidence: (turnId: string) => void;
}) {
  const sources = (f: SourcedField) =>
    f.source_turn_ids.map((id) => (
      <button key={id} type="button" onClick={() => onEvidence(id)} className="ml-1 text-xs underline">
        turn {turnNumber(id, transcript) ?? "?"}
      </button>
    ));

  const single: [string, SourcedField | null | undefined][] = [
    ["Incident", record.incident],
    ["Safety now", record.safety_now],
    ["Medical need", record.medical_need],
    ["Legal status", record.legal_status],
    ["Isolation / boycott", record.isolation],
    ["Stated request", record.requested_support],
  ];
  const lists: [string, SourcedField[] | undefined][] = [
    ["Persons mentioned", record.persons],
    ["Time references", record.timeline],
    ["Threats", record.threats],
  ];
  const empty = single.every(([, f]) => !f) && lists.every(([, l]) => !l || l.length === 0);

  return (
    <section aria-labelledby="struct-h" className="panel p-3">
      <h2 id="struct-h" className="text-headline-sm">Structured Extraction</h2>
      {empty ? (
        <p className="mt-1 text-sm text-neutral-700">Nothing extracted yet.</p>
      ) : (
        <dl className="mt-3 space-y-2 text-sm">
          {single.map(([label, f]) =>
            f ? (
              <div key={label} className="rounded bg-surface-container-low p-2">
                <dt className="text-[10px] font-semibold uppercase tracking-wide text-on-surface-variant">{label}</dt>
                <dd className="mt-1">
                  {f.value}
                  {sources(f)}
                </dd>
              </div>
            ) : null,
          )}
          {lists.map(([label, items]) =>
            items && items.length > 0 ? (
              <div key={label} className="rounded bg-surface-container-low p-2">
                <dt className="text-[10px] font-semibold uppercase tracking-wide text-on-surface-variant">{label}</dt>
                <dd>
                  <ul className="list-disc pl-5">
                    {items.map((f, i) => (
                      <li key={`${label}-${i}`}>
                        {f.value}
                        {sources(f)}
                      </li>
                    ))}
                  </ul>
                </dd>
              </div>
            ) : null,
          )}
        </dl>
      )}
    </section>
  );
}
