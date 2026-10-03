"""
Fuzzy matching for series names.
Tries in order:
  1. Exact (case-insensitive)
  2. Starts-with
  3. Contains
  4. Levenshtein distance (typo tolerance)
"""


def _levenshtein(a: str, b: str) -> int:
    """Calculate edit distance between two strings."""
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = curr
    return prev[-1]


def find_best_match(query: str, all_series: list[dict]) -> dict | None:
    """
    Given a user query and a list of series dicts (with 'name' and 'name_lower'),
    return the best matching series or None.
    """
    q = query.lower().strip()

    # 1. Exact match
    for s in all_series:
        if s["name_lower"] == q:
            return s

    # 2. Starts-with
    for s in all_series:
        if s["name_lower"].startswith(q):
            return s

    # 3. Contains
    for s in all_series:
        if q in s["name_lower"]:
            return s

    # 4. Levenshtein — allow up to 40% of query length as edit distance
    threshold = max(2, int(len(q) * 0.4))
    best = None
    best_dist = threshold + 1

    for s in all_series:
        dist = _levenshtein(q, s["name_lower"])
        if dist < best_dist:
            best_dist = dist
            best = s

    return best if best_dist <= threshold else None
