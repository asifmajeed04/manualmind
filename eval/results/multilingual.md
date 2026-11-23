# Multilingual check

Models: embeddings `gemini-embedding-001`, LLM `gemini-3.8-flash`. Documents: Danfoss_VLT_Micro_Drive_FC51_Operating_Guide_EN.pdf, Grundfos_CR_CRI_CRN_Installation_Operating_EN.pdf, SEW_MOVITRAC_LTE-B_Betriebsanleitung_DE.pdf, Wilo-Stratos_PICO_plus_Betriebsanleitung_DE.pdf.

| Document → question (hybrid) | n | Retrieval hit @6 | Answer in question language | Correct page cited |
|---|---|---|---|---|
| German doc · German question | 7 | 71% | 100% | 71% |
| German doc · **English** question | 13 | 85% | 100% | 85% |
| English doc · English question | 9 | 89% | 100% | 89% |
| English doc · **German** question | 11 | 82% | 100% | 82% |
| **All** | 40 | 82% | 100% | 82% |

Cross-language questions: 24 — hit 83%, answer language 100%, citation 83%.
