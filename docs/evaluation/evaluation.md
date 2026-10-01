# Evaluation

`citruscare.evaluation` computes deterministic operational metrics over
explicit test labels:

- retrieval precision and recall against expected synthetic entity IDs;
- citation coverage against expected synthetic source IDs;
- unsupported-claim rate from supplied claim counts (the evaluator does not
  infer whether natural-language claims are medically supported);
- tool success, policy violation count, latency, and structured-output
  validity;
- caller-supplied lexical grounding rate and summed estimated cost metadata.

The model adapter does not invent a price schedule: `estimated_cost` stays
caller-supplied and live provider responses expose no cost unless the adapter is
extended with an explicit pricing source.

The checked-in cases refer only to synthetic fixture identifiers. The engine
does not use fabricated ground truth to score medical accuracy. A future
validated dataset needs appropriate rights, provenance, review, privacy
controls, and a documented evaluation protocol before use.

Run the deterministic tests with:

```powershell
python -m pytest tests\evaluation
```
