# Provider-agnostic LLM with Mode Cloud and Mode Pabrik

AI processing runs in Mode Cloud (an external LLM provider) or Mode Pabrik (every model on the site's own servers, no data leaving), and the demo shows the eval scores of both side by side. Pharmaceutical plants often refuse to let data leave the company, and as of November 2026 no in-country Claude endpoint was found for Indonesia (Bedrock Jakarta serves Claude through global routing). Document reading (OCR and tables) is always local, in both modes, because dedicated OCR models of about 1B parameters beat general LLMs on document benchmarks.

## Consequences

- Initial models: Claude Haiku 5.5 for Mode Cloud and Qwen-SEA-LION v4.5 27B (open weights) for Mode Pabrik, both chosen on cost within a hard budget.
- During development the Mode Pabrik model is evaluated through a hosted API serving the same weights. This is allowed only because the data is synthetic (ADR 0001).
- Self-hosting is shown on a rented GPU (Modal) standing in for a plant GPU server: the same vLLM container can be installed on-premises. The demo says so plainly and does not call Modal "on-prem".
- The thin-slice spec tests the local-OCR assumption on the SAT scan (CPU only, scored by the OCR scorer, with RAM and time per page); a Claude vision run is only a comparison. This ADR changes only through a new ADR, and only if local OCR clearly loses.
