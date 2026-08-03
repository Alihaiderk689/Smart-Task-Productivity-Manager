"""Heuristic "does this look like real text" check for task titles and
descriptions -- catches keyboard-mashing (e.g. "ahfuahsfua sfhasf uhaf")
without a dictionary lookup, so it doesn't reject real proper nouns, brand
names, acronyms, or non-English text the way a dictionary-word check would.

Mirrored on the frontend in frontend/src/lib/taskValidation.js for
real-time UX -- keep the two in sync. The backend copy here is the one
that actually matters: it's the real enforcement point, same as the
word-count/date rules in tasks/serializers.py.

How it works: in real English (and in most transliterated non-English
words, which still follow consonant-vowel alternation), almost every
two-letter sequence either touches a vowel or is one of a fairly small set
of recognized consonant clusters (th, st, ng, rd, ...). Keyboard-mashing
has no phonetic structure behind it, so it produces a much higher share of
letter pairs that are two consonants NOT forming a real cluster ("hf",
"sf", "jq"). Rather than judging word-by-word (too noisy on short/unusual
words -- a single odd word shouldn't flag a whole sentence), this counts
implausible letter-pairs across the whole field at once, which cancels
out that per-word noise: a stray unusual word barely moves the ratio, but
a field that's mostly mashing pushes it well past the threshold. See
tasks/test_tasks.py for the calibration cases this threshold was picked
against (both gibberish and ordinary task titles).
"""

from __future__ import annotations

import re

_VOWELS = frozenset("aeiouy")

# Two-consonant sequences that are legitimate English clusters -- anything
# else where *both* letters are consonants counts as implausible below.
_CONSONANT_CLUSTERS = frozenset(
    "bl br ch ck cl cr dg dr dw fl fr gh gl gn gr kn kh ph pl pr qu "
    "sc sch scr shr sk sl sm sn sp spl spr squ st str sw th thr tr tw "
    "wh wr ng nk nt nd nc ns mp mb mn lt ld lf lk lm ln lp ls lv lc lg "
    "rd rk rl rm rn rp rt rc rg rb rs rv ct pt ft gt xt "
    "ss ll ff mm nn pp tt zz dd gg bb cc rr ts ds ps cs vs ks".split()
)

_MIN_JUDGEABLE_WORDS = 2
_MIN_BIGRAMS = 6
_IMPLAUSIBLE_RATIO_THRESHOLD = 0.22


def _is_plausible_bigram(bigram: str) -> bool:
    a, b = bigram[0], bigram[1]
    if a == b:
        return True  # doubled letters (ll, ss, ...) are always fine
    if a in _VOWELS or b in _VOWELS:
        return True  # any pair touching a vowel is fine -- that's most of English
    return bigram in _CONSONANT_CLUSTERS


def looks_like_gibberish(value: str) -> bool:
    """True if `value` is dominated by letter-pairs that don't look like
    plausible English. Only words of 5+ letters count towards the ratio
    (short words/acronyms are too ambiguous to judge), and fields with too
    little judgeable text (fewer than 2 such words, or fewer than 6 total
    letter-pairs) always return False rather than guessing off a thin
    sample."""
    words = [re.sub(r"[^a-zA-Z]", "", w) for w in (value or "").split()]
    judgeable = [w for w in words if len(w) >= 5]
    if len(judgeable) < _MIN_JUDGEABLE_WORDS:
        return False

    total = 0
    implausible = 0
    for word in judgeable:
        letters = word.lower()
        for i in range(len(letters) - 1):
            bigram = letters[i : i + 2]
            total += 1
            if not _is_plausible_bigram(bigram):
                implausible += 1

    if total < _MIN_BIGRAMS:
        return False
    return (implausible / total) >= _IMPLAUSIBLE_RATIO_THRESHOLD
