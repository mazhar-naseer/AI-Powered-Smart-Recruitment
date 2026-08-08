// Every AI capability in the product is presented as SmartHire AI.
//
// The API still reports which engine produced a result — `ai_provider` carries a
// model identifier and `prompt_version` carries an engine-tagged build string —
// because those values are stored on rows that were scored long before this
// module existed. They are mapped here instead of being rendered, so the vendor
// behind the analysis stays an implementation detail and the UI has exactly one
// place to change if the provider is ever swapped.

export const AI_NAME = 'SmartHire AI';

/** The deterministic engine records itself under this fixed key. */
const DETERMINISTIC = 'deterministic-fallback';

/** Human label for whichever engine produced a stored result. */
export function aiEngineLabel(provider?: string | null, fallback = 'Not configured'): string {
  if (!provider) return fallback;
  return provider === DETERMINISTIC ? 'SmartHire Deterministic Engine' : AI_NAME;
}

/**
 * Build tag for the audit trail, with any vendor token folded into the product
 * name. The rest of the tag is kept so a result stays traceable to a release.
 */
export function aiVersionLabel(version?: unknown): string {
  const label = version == null ? '' : String(version);
  if (!label) return 'legacy';
  return label.replace(/gemini/gi, 'smarthire');
}
