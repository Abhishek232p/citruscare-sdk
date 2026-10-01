# Intelligence workflows

Run the offline end-to-end synthetic workflow:

```powershell
python examples\intelligence_demo\run.py
```

The output includes request and audit IDs, model/provider identity,
provenance-bearing evidence, tool calls, safety decision, latency, and a
synthetic-data warning. See the [engine architecture](../architecture/intelligence-engine.md)
and [evaluation scope](../evaluation/evaluation.md).
