# Usage Report

Final full-dataset run that produced output.csv (518 cases).

## Model usage
- Model providers: none
- Model names: none
- Model calls: 0
- Input tokens: 0
- Output tokens: 0
- Total tokens: 0
- Average tokens per request: 0
- Estimated total cost: $0.00
- Estimated cost per request: $0.00

## Notes
The runtime pipeline is fully deterministic and offline. Request classification
uses multilingual rules, and identity resolution, evidence parsing, policy
evaluation and step planning are plain Python. The final run makes no network
calls and calls no language model (verified by a source scan and by a
two-run SHA-256 comparison of output.csv).

A coding agent (Codex) was used during development only. Its session traces are
included in agent-trace.zip and log.txt. No API keys are used or required.
