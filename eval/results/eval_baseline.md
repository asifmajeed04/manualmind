# Evaluation — baseline

| Retrieval mode | Hit rate @6 | MRR @6 | Cross-language hit @6 | Code/part-number hit @6 | Faithfulness (1–5) | Correctness (1–5) |
|---|---|---|---|---|---|---|
| vector | 88% | 0.72 | 83% | 100% | – | – |
| keyword | 57% | 0.43 | 42% | 100% | – | – |
| hybrid | 88% | 0.71 | 83% | 100% | – | – |

40 questions (24 cross-language, 4 with codes/part numbers), 4 documents. Embeddings `gemini-embedding-001`, LLM `gemini-3.8-flash` (fallbacks `gemini-3.1-flash-lite,gemini-3.5-flash`); the same LLM family acts as judge.
