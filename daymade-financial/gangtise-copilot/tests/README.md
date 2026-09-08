# Diagnostic tests

Run the deterministic response-classification suite from `gangtise-copilot`:

```bash
python3 -m unittest discover -s tests -v
```

The fixtures cover the current `loginV2` shape with no `uid`, `tenantId`, or `productCode`; malformed auth success; authentication and permission rejection; the observed quota/entitlement response; and a successful RAG response with no matches. The suite never reads credentials or calls Gangtise.
