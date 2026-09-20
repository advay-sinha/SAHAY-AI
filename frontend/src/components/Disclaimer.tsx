import { ASSESSMENT_DISCLAIMER } from "../types/contracts";

/**
 * Carried on every screen that shows an assessment. Judges photograph screens,
 * and the claim on the screen is the claim the project is making.
 */
export function Disclaimer() {
  return (
    <p role="note" className="text-[10px] text-inherit">
      {ASSESSMENT_DISCLAIMER}
    </p>
  );
}
