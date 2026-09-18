# Token usage and cost report

This file is a template for the final full-dataset run. Replace the placeholders after generating `output.csv`.

## Deterministic decision engine

The CSV joins, currency conversion, 90-day forecast, plan enumeration, validation and final decision use no model calls and therefore use zero tokens and cost $0.

## Evidence extraction

Gemini is called only when a financial event has a blank amount that must be read from a linked image and the answer is not already present in `dataset/evidence_cache.json`.

| Provider | Model | Calls | Input tokens | Output tokens | Estimated cost |
| --- | --- | ---: | ---: | ---: | ---: |
| Google | Set after final run | TODO | TODO | TODO | TODO |

Final requests processed: TODO  
Total calls: TODO  
Total input tokens: TODO  
Total output tokens: TODO  
Average tokens per request: TODO  
Estimated total cost: TODO  
Estimated cost per request: TODO

Do not claim zero calls for a final run that extracted uncached image evidence. Record the actual provider usage shown by the API or provider dashboard.
