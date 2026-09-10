import type { PacketTurn } from "../../types/packet";

/**
 * Two-sided transcript in the original language. Victim and assistant turns are
 * visually distinct, so the officer can audit exactly what the AI said. Draft
 * (unreviewed) assistant text is labelled as such.
 */
export function TranscriptPanel({
  transcript,
  highlight,
}: {
  transcript: PacketTurn[];
  highlight: string | null;
}) {
  if (transcript.length === 0) {
    return <p className="text-sm text-neutral-700">No messages yet.</p>;
  }
  return (
    <ol aria-label="Transcript" className="space-y-2">
      {transcript.map((t, i) => {
        const victim = t.speaker === "victim";
        const lit = highlight === t.id;
        return (
          <li
            key={t.id}
            id={`turn-${t.id}`}
            tabIndex={-1}
            className={`max-w-[92%] border p-2 ${victim ? "mr-auto border-neutral-500 bg-white" : "ml-auto border-neutral-300 bg-neutral-100"} ${lit ? "outline outline-4 outline-amber-500" : ""}`}
          >
            <div className="flex flex-wrap justify-between gap-2 text-xs text-neutral-700">
              <span className="font-semibold">
                {i + 1}. {victim ? "Complainant" : t.speaker === "assistant" ? "AI assistant" : "Officer"}
              </span>
              <span>
                {t.lang} · {t.state}
                {t.ts ? ` · ${new Date(t.ts).toLocaleTimeString()}` : ""}
              </span>
            </div>
            <p lang={t.lang === "hi" ? "hi" : "en"} className="mt-1 whitespace-pre-wrap text-sm">
              {t.text}
            </p>
            {!victim && t.review_status === "draft" && (
              <p className="mt-1 text-xs text-neutral-600">Draft wording — not yet reviewed ({t.intent}).</p>
            )}
          </li>
        );
      })}
    </ol>
  );
}
