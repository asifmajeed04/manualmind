"""Language of a (short) question: 'de' or 'en'.

General detectors are unreliable on one-line questions full of product names and codes
("What does E021 mean?"), so function words and German characters decide first and
langdetect only breaks ties.
"""

from __future__ import annotations

import re

from langdetect import DetectorFactory, LangDetectException, detect_langs

DetectorFactory.seed = 0

_DE = frozenset(
    "der die das den dem des ein eine einen einem einer ist sind wird werden wie was welche welcher welches "
    "warum wann wo wer muss müssen kann können darf soll sollte und oder nicht kein keine bei beim mit für von "
    "zum zur auf aus nach über unter ich mein meine man es sich auch noch nur bitte gibt hat haben bedeutet "
    "bedeuten tun läuft macht oft lang maximal zulässig".split()
)
_EN = frozenset(
    "the a an is are was were be been does do did what which who whom why when where how must can could should "
    "would will may might and or not no of on in at to for from with by my i you it this that these those there "
    "please mean means during should need needs makes make often long maximum".split()
)
_WORD = re.compile(r"[a-zäöüß]+", re.IGNORECASE)


def question_language(text: str, default: str = "en") -> str:
    words = [w.lower() for w in _WORD.findall(text)]
    de = sum(w in _DE for w in words) + 2 * len(re.findall(r"[äöüß]", text.lower()))
    en = sum(w in _EN for w in words)
    if de != en:
        return "de" if de > en else "en"
    try:
        probs = {p.lang: p.prob for p in detect_langs(text)}
    except LangDetectException:
        return default
    if probs.get("de", 0) == probs.get("en", 0):
        return default
    return "de" if probs.get("de", 0) > probs.get("en", 0) else "en"


def is_quota_error(err: BaseException | None) -> bool:
    """True if the error (or its cause chain) is an exhausted AI-provider quota (HTTP 429)."""
    while err is not None:
        if getattr(err, "code", None) == 429 or "quota" in str(err).lower():
            return True
        err = err.__cause__ or err.__context__
    return False


QUOTA_MESSAGE = {
    "en": "The free AI quota is used up for now. Please try again later (daily limits reset after 24 h).",
    "de": "Das kostenlose KI-Kontingent ist vorerst aufgebraucht. Bitte später erneut versuchen (Tageslimits werden nach 24 h zurückgesetzt).",
}

ANSWER_IN = {"de": "Antworte auf Deutsch.", "en": "Answer in English."}
