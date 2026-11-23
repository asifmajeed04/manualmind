# Evaluation — final

| Retrieval mode | Hit rate @6 | MRR @6 | Cross-language hit @6 | Code/part-number hit @6 | Faithfulness (1–5) | Correctness (1–5) |
|---|---|---|---|---|---|---|
| vector | 100% | 0.92 | 100% | 100% | – | – |
| keyword | 57% | 0.43 | 42% | 100% | – | – |
| hybrid | 100% | 0.91 | 100% | 100% | 5.00 (n=6) | 5.00 (n=6) |

40 questions (24 cross-language, 4 with codes/part numbers), 4 documents. Embeddings `gemini-embedding-001`, LLM `gemini-3.1-flash-lite` (fallbacks `gemini-3.5-flash,gemini-3.8-flash`); the same LLM family acts as judge.
