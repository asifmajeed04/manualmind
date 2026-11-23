# Multilingual check

Models: embeddings `gemini-embedding-001`, LLM `gemini-3.8-flash`. Documents: DP-50_Dosing_Pump_Datasheet.pdf, Kreiselpumpe_KP-300_Betriebsanleitung.pdf.

| Document → question (hybrid) | n | Retrieval hit @6 | Answer in question language | Correct page cited |
|---|---|---|---|---|
| German doc · German question | 3 | 100% | 100% | 100% |
| German doc · **English** question | 6 | 100% | 100% | 100% |
| English doc · English question | 2 | 100% | 100% | 100% |
| English doc · **German** question | 5 | 100% | 100% | 100% |
| **All** | 16 | 100% | 100% | 100% |

Cross-language questions: 11 — hit 100%, answer language 100%, citation 100%.
