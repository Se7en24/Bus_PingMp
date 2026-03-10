"""
Fuzzy destination matching against known Malayalam + English lists.

Uses token_sort_ratio (stricter than token_set_ratio) and penalizes
large length differences to avoid garbled OCR getting 100% confidence.
"""

from rapidfuzz import process, fuzz
from config import ML_DESTINATIONS, EN_DESTINATIONS, MATCH_THRESHOLD


def _strict_score(query: str, candidate: str) -> float:
    """
    Combined scorer: token_sort_ratio penalized by length difference.
    
    token_set_ratio gives 100% if one string is a subset of the other,
    which causes garbled OCR like "കോറ്റ" to match "കോട്ടയം" at 100%.
    
    This scorer uses token_sort_ratio (order-invariant but checks ALL tokens)
    and applies a length penalty so very different-length strings score lower.
    """
    base = fuzz.token_sort_ratio(query, candidate)
    
    # Length penalty: if lengths differ a lot, reduce confidence
    len_q, len_c = len(query.strip()), len(candidate.strip())
    if max(len_q, len_c) > 0:
        length_ratio = min(len_q, len_c) / max(len_q, len_c)
    else:
        length_ratio = 0
    
    # Blend: 75% fuzzy + 25% length similarity
    final = (base * 0.75) + (length_ratio * 100 * 0.25)
    return final


def match_destination(ml_text: str | None, en_text: str | None):
    """
    Match OCR output against known destination lists.

    Returns:
        (best_match_string, score)  or  (None, 0)
    """
    best_match = None
    highest_score = 0

    # Malayalam matching
    if ml_text and len(ml_text.strip()) >= 3:
        for candidate in ML_DESTINATIONS:
            score = _strict_score(ml_text, candidate)
            if score > MATCH_THRESHOLD and score > highest_score:
                best_match, highest_score = candidate, score

    # English matching
    if en_text and len(en_text.strip()) >= 3:
        for candidate in EN_DESTINATIONS:
            score = _strict_score(en_text, candidate)
            if score > MATCH_THRESHOLD and score > highest_score:
                best_match, highest_score = candidate, score

    return best_match, round(highest_score, 1)

