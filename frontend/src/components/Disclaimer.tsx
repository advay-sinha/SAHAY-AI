import { ASSESSMENT_DISCLAIMER } from "../types/contracts";

/**
 * Carried on every screen that shows an assessment. Judges photograph screens,
 * and the claim on the screen is the claim the project is making.
 */
export function Disclaimer() {
  return (
    <p role="note" className="border-t border-neutral-300 pt-2 text-xs text-neutral-700">
      {ASSESSMENT_DISCLAIMER}
    </p>
  );
}
