"""Street-name normalisation shared by the centerline loader and the street matcher.

Centerline names look like 'E  72 ST', 'FRANCIS LEWIS BLVD', 'BCH 43 ST': abbreviated suffixes
and directionals, no ordinals. Project text says 'EAST 72ND STREET', 'E 72ND ST', 'Francis Lewis
Boulevard'. Both sides go through `normalize` so they compare equal. Directionals are kept:
Brooklyn has both '72 ST' and 'E 72 ST', which are different streets.
"""
import re

WORDS = {
    "STREET": "ST", "STR": "ST", "STREETS": "ST", "AVENUE": "AVE", "AV": "AVE", "AVES": "AVE",
    "ROAD": "RD", "BOULEVARD": "BLVD", "PLACE": "PL", "TERRACE": "TER", "DRIVE": "DR",
    "PARKWAY": "PKWY", "LANE": "LN", "COURT": "CT", "EXPRESSWAY": "EXPY", "EXPWY": "EXPY",
    "HIGHWAY": "HWY", "TURNPIKE": "TPKE", "SQUARE": "SQ", "PLAZA": "PLZ", "BEACH": "BCH",
    "EAST": "E", "WEST": "W", "NORTH": "N", "SOUTH": "S", "SAINT": "ST",
}
SUFFIXES = {"ST", "AVE", "RD", "BLVD", "PL", "TER", "DR", "PKWY", "LN", "CT", "EXPY", "HWY", "TPKE",
            "SQ", "PLZ", "WAY", "LOOP", "WALK", "ROW", "OVAL", "CRES", "CIR", "ALY", "BRG"}


def normalize(name: str | None) -> str:
    """'East 72nd Street' -> 'E 72 ST'; 'Francis Lewis Boulevard' -> 'FRANCIS LEWIS BLVD'."""
    s = re.sub(r"[^A-Z0-9 ]", " ", (name or "").upper())
    out = []
    for w in s.split():
        if m := re.fullmatch(r"(\d+)(ST|ND|RD|TH)", w):
            n, suffix = m.groups()
            if suffix in ("ST", "RD") and suffix != ordinal_suffix(int(n)):
                out += [n, suffix]  # '7ST' is 7 St, '3RD' an ordinal
                continue
            w = n  # 72ND -> 72
        out.append(WORDS.get(w, w))
    return " ".join(out)


def ordinal_suffix(n: int) -> str:
    if n % 100 in (11, 12, 13):
        return "TH"
    return {1: "ST", 2: "ND", 3: "RD"}.get(n % 10, "TH")


def base(name: str) -> str:
    """Name without its suffix, to match cross streets loosely: 'RECTOR ST' -> 'RECTOR'."""
    words = name.split()
    return " ".join(words[:-1]) if len(words) > 1 and words[-1] in SUFFIXES else name
