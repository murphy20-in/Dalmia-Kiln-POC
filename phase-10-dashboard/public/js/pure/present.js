/** Drop presentation of figures Phase 8 withholds from this layer. Does not alter stored evidence. */

const WITHHELD = /\bAUC\b|lead[\s-]?time|coverage\s+[0-9]|false[- ]positive rate/i;

export function evidenceForDisplay(text) {
  if (text == null || text === "") return "";
  if (WITHHELD.test(String(text))) return "";
  return String(text);
}

export const FORBIDDEN_UI = [
  /\bpredicted\b/i,
  /\bprediction\b/i,
  /\bprobability\b/i,
  /\balarm\b/i,
  /early warning active/i,
  /failure probability/i,
  /deposit probability/i,
  /ring probability/i,
  /lead[\s-]?time/i,
  /\bAUC\b/,
];

const NEGATION = /not\b|never|without|prohibited|must not|no live|does not|do not|is not|are not|≠|withheld/i;

/** A forbidden word is allowed only on a line that states the absence of the claim. */
export function lineAllowsForbidden(line) {
  return NEGATION.test(line);
}
