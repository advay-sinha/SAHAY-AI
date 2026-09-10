import { useState } from "react";
import { MAX_MESSAGE_CHARS, validateMessage, validateOverride } from "../../console/logic";
import type { Band } from "../../types/contracts";
import type { CasePacket } from "../../types/packet";

const BANDS: Band[] = ["Low", "Moderate", "High", "Critical"];

/**
 * Band override (reason mandatory), takeover and, after takeover, a message to
 * the complainant (PC-07). All are audited server-side.
 */
export function DecisionControls({
  packet,
  canAct,
  blockedReason,
  onOverride,
  onTakeover,
  canMessage,
  messageBlockedReason,
  onMessage,
}: {
  packet: CasePacket;
  canAct: boolean;
  blockedReason: string | null;
  onOverride: (band: Band, reason: string) => Promise<string | null>;
  onTakeover: () => Promise<string | null>;
  canMessage: boolean;
  messageBlockedReason: string | null;
  onMessage: (text: string) => Promise<string | null>;
}) {
  const [message, setMessage] = useState("");
  const [messageError, setMessageError] = useState<string | null>(null);
  const [band, setBand] = useState<Band | "">("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [takeoverError, setTakeoverError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const taken = packet.header.status === "taken_over";

  async function submitOverride() {
    const invalid = validateOverride(band, reason);
    if (invalid) return setError(invalid);
    setBusy(true);
    const failure = await onOverride(band as Band, reason.trim());
    setBusy(false);
    setError(failure);
    if (!failure) {
      setBand("");
      setReason("");
    }
  }

  return (
    <section aria-labelledby="decide-h" className="space-y-3 border border-neutral-400 p-3">
      <h2 id="decide-h" className="font-semibold">Officer actions</h2>
      {!canAct && blockedReason && <p className="text-xs text-neutral-700">{blockedReason}</p>}

      <div>
        <h3 className="text-sm font-medium">Take over the conversation</h3>
        <p className="text-xs text-neutral-700">
          Mutes the assistant and tells the complainant a person has joined.
        </p>
        <button type="button" disabled={!canAct || taken || busy}
          onClick={async () => setTakeoverError(await onTakeover())}
          className="mt-1 border border-neutral-900 px-3 py-1 text-sm font-medium disabled:opacity-50">
          {taken ? "You have taken over" : "Take over"}
        </button>
        {takeoverError && <p role="alert" className="text-xs text-red-800">{takeoverError}</p>}
      </div>

      {taken && (
        <div>
          <h3 className="text-sm font-medium">Message the complainant</h3>
          <p className="text-xs text-neutral-700">
            Sent as you, a person — never as the assistant. Do not include any score, band or alert.
          </p>
          {!canMessage && messageBlockedReason && <p className="text-xs text-neutral-700">{messageBlockedReason}</p>}
          <label className="mt-1 block text-xs" htmlFor="officer-message">Your message</label>
          <textarea id="officer-message" rows={2} value={message} disabled={!canMessage || busy}
            maxLength={MAX_MESSAGE_CHARS} onChange={(e) => setMessage(e.target.value)}
            className="w-full border border-neutral-500 p-1 text-sm" />
          {messageError && <p role="alert" className="text-xs text-red-800">{messageError}</p>}
          <button type="button" disabled={!canMessage || busy}
            onClick={async () => {
              const invalid = validateMessage(message);
              if (invalid) return setMessageError(invalid);
              setBusy(true);
              const failure = await onMessage(message.trim());
              setBusy(false);
              setMessageError(failure);
              if (!failure) setMessage("");
            }}
            className="mt-1 border border-neutral-900 px-3 py-0.5 text-sm font-medium disabled:opacity-50">
            Send message
          </button>
        </div>
      )}

      <div>
        <h3 className="text-sm font-medium">Override the band</h3>
        <div className="mt-1 flex flex-wrap items-end gap-2">
          <label className="text-xs">
            Band
            <select value={band} disabled={!canAct} onChange={(e) => setBand(e.target.value as Band | "")}
              className="ml-1 border border-neutral-500 p-0.5 text-sm">
              <option value="">—</option>
              {BANDS.map((b) => <option key={b} value={b}>{b}</option>)}
            </select>
          </label>
        </div>
        <label className="mt-1 block text-xs" htmlFor="override-reason">Reason (required)</label>
        <textarea id="override-reason" rows={2} value={reason} disabled={!canAct} maxLength={1000}
          onChange={(e) => setReason(e.target.value)} className="w-full border border-neutral-500 p-1 text-sm" />
        {error && <p role="alert" className="text-xs text-red-800">{error}</p>}
        <button type="button" onClick={submitOverride} disabled={!canAct || busy}
          className="mt-1 border border-neutral-900 px-3 py-0.5 text-sm font-medium disabled:opacity-50">
          Record override
        </button>
      </div>

      {packet.overrides.length > 0 && (
        <div>
          <h3 className="text-sm font-medium">Override history</h3>
          <ul className="text-xs">
            {packet.overrides.map((o, i) => (
              <li key={i}>
                {o.from_band ?? "Needs Human"} → {o.to_band} by {o.officer}: “{o.reason}”
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
