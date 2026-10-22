"""Turn a shopper's free-text request into a structured product search plan with a local language model (LangChain + Ollama).

The model proposes; plain code checks. A 4B model sometimes invents colours or a gender nobody mentioned, so after the model answers,
`ground()` keeps a colour only if the shopper actually wrote it and keeps a gender only if the request gives a cue for it.
"""
from __future__ import annotations

import re
import time
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, BeforeValidator, Field, field_validator


def _clip(n: int):
    """Over-long text is cut to the limit, not refused: a model that writes 201 characters must not cost the visitor the whole answer."""
    return BeforeValidator(lambda v: v[:n] if isinstance(v, str) else v)


def _first(n: int):
    """Too many items: keep the first n (the model lists the most important first), do not refuse the plan."""
    return lambda v: v[:n] if isinstance(v, list) else v

Kind = Literal["top", "bottom", "dress", "outerwear", "footwear", "accessory", "other"]
Gender = Literal["men", "women", "boys", "girls", "unisex", "unknown"]
Short = Annotated[str, _clip(120), Field(max_length=120)]
Note = Annotated[str, _clip(300), Field(max_length=300)]


class Piece(BaseModel):
    kind: Kind
    search_text: Annotated[str, _clip(200)] = Field(max_length=200, description="short product-style phrase, e.g. \"men's navy cotton polo shirt\"")
    colours: list[Short] = Field(default_factory=list, max_length=10, description="only colours the shopper wrote")

    _colours = field_validator("colours", mode="before")(_first(10))


class Plan(BaseModel):
    main_query: Annotated[str, _clip(300)] = Field(max_length=300, description="one clean product search phrase for the whole request")
    gender: Gender
    occasion: Optional[Short] = None
    season: Optional[Short] = None
    budget_inr: Optional[float] = None
    pieces: list[Piece] = Field(max_length=12)      # bounded (a model or a visitor's device could send hundreds); the search uses at most server.MAX_PIECES
    already_has: list[Short] = Field(default_factory=list, max_length=10, description="items the shopper says they already own (v2)")
    notes: list[Note] = Field(default_factory=list, max_length=40, description="what code changed after the model answered (graph expansion)")

    _pieces = field_validator("pieces", mode="before")(_first(12))
    _owned = field_validator("already_has", mode="before")(_first(10))
    _notes = field_validator("notes", mode="before")(_first(40))


SYSTEM_V1 = """You turn a shopper's request into a product search plan for a fashion store. Answer with JSON only.
Rules:
- Fix typos and understand Hinglish (Hindi words in English letters). Ignore chit-chat.
- main_query: one clean product search phrase for the whole request, written like a product title search ("boys rain boots size 12").
- pieces: the clothing items to search for. One named item means ONE piece. An occasion or whole look means the pieces needed.
- Use null or [] when something is not stated. NEVER invent a colour, a budget, a gender or an occasion the shopper did not say.
- gender is "unknown" unless the request says or clearly implies it (men, boy, girl, mom, sister, her...).
- colours holds only colour words the shopper wrote. Words like "bright" or "flowy" are not colours.
- Do not copy place names or sizes into search_text unless they describe the product.

Examples:
Request: "red lehenga for my sister's sangeet under 8000"
{"main_query":"women's red lehenga","gender":"women","occasion":"sangeet","season":null,"budget_inr":8000,"pieces":[{"kind":"dress","search_text":"women's red lehenga","colours":["red"]}]}
Request: "wanna look sharp at a job interview next week"
{"main_query":"formal interview outfit","gender":"unknown","occasion":"job interview","season":null,"budget_inr":null,"pieces":[{"kind":"top","search_text":"formal shirt","colours":[]},{"kind":"bottom","search_text":"formal trousers","colours":[]},{"kind":"footwear","search_text":"formal shoes","colours":[]}]}
Request: "chappal for monsoon, easy to clean"
{"main_query":"monsoon sandals easy to clean","gender":"unknown","occasion":null,"season":"monsoon","budget_inr":null,"pieces":[{"kind":"footwear","search_text":"waterproof sandals","colours":[]}]}
"""


# v2 (2026-10-13): written after reading 15 real requests from the user. Adds: concrete garments only, keep the named product,
# and an "already_has" list for requests like "what goes with my blue jeans". v1 stays unchanged so milestone 4 results can be reproduced.
SYSTEM_V2 = SYSTEM_V1.split("Examples:")[0] + """- pieces must be concrete things a store sells (shirt, kurta, sandals), never the word "outfit" or "look". For an event or a vibe list 2 to 4 pieces.
- If the shopper names a product (co-ord set, tuxedo, kurta), keep that product in search_text even when an event is mentioned.
- already_has: things the shopper says they already own ("my blue jeans"). Then pieces are what goes WITH them, and the owned item is not a piece.
- If the shopper asks about colour combinations, still return the pieces.

Examples:
Request: "red lehenga for my sister's sangeet under 8000"
{"main_query":"women's red lehenga","gender":"women","occasion":"sangeet","season":null,"budget_inr":8000,"pieces":[{"kind":"dress","search_text":"women's red lehenga","colours":["red"]}],"already_has":[]}
Request: "wanna look sharp at a job interview next week"
{"main_query":"formal interview wear","gender":"unknown","occasion":"job interview","season":null,"budget_inr":null,"pieces":[{"kind":"top","search_text":"formal shirt","colours":[]},{"kind":"bottom","search_text":"formal trousers","colours":[]},{"kind":"footwear","search_text":"formal shoes","colours":[]}],"already_has":[]}
Request: "something to wear with my black jeans for date night"
{"main_query":"date night top","gender":"unknown","occasion":"date night","season":null,"budget_inr":null,"pieces":[{"kind":"top","search_text":"stylish date night shirt","colours":[]},{"kind":"footwear","search_text":"casual shoes","colours":[]}],"already_has":["black jeans"]}
Request: "diwali party look, ethnic but comfy"
{"main_query":"comfortable ethnic wear","gender":"unknown","occasion":"diwali party","season":null,"budget_inr":null,"pieces":[{"kind":"top","search_text":"kurta","colours":[]},{"kind":"bottom","search_text":"churidar or pyjama","colours":[]},{"kind":"footwear","search_text":"ethnic juttis","colours":[]}],"already_has":[]}
Request: "co-ord set for a beach trip with friends"
{"main_query":"co-ord set","gender":"unknown","occasion":"beach trip","season":null,"budget_inr":null,"pieces":[{"kind":"dress","search_text":"beach co-ord set","colours":[]}],"already_has":[]}
Request: "kurta and jeans recommendation"
{"main_query":"kurta with jeans","gender":"unknown","occasion":null,"season":null,"budget_inr":null,"pieces":[{"kind":"top","search_text":"kurta","colours":[]},{"kind":"bottom","search_text":"jeans","colours":[]}],"already_has":[]}
"""
SYSTEMS = {"v1": SYSTEM_V1, "v2": SYSTEM_V2}


# Words that justify a gender. Kept deliberately small and visible so it can be criticised and changed.
_GENDER_CUES = {
    "men": r"\b(men|mens|man|male|guy|guys|boyfriend|husband|dad|father|brother|groom)\b",
    "women": r"\b(women|womens|woman|ladies|lady|female|girlfriend|wife|mom|mum|mother|sister|bride|her)\b",
    "boys": r"\b(boy|boys|boyz|son)\b",
    "girls": r"\b(girl|girls|daughter)\b",
    "unisex": r"\b(unisex|everyone|anyone)\b",
}
_SAME_GROUP = {"men": {"men"}, "women": {"women"}, "boys": {"boys", "men"}, "girls": {"girls", "women"}, "unisex": {"unisex"}}


_MONTH_SEASON = {  # India-oriented; only used to turn a stated month into a season
    "december": "winter", "january": "winter", "february": "winter", "march": "summer", "april": "summer", "may": "summer",
    "june": "summer", "july": "monsoon", "august": "monsoon", "september": "monsoon", "october": "autumn", "november": "autumn",
}
_SEASON_WORDS = {"summer": "summer", "winter": "winter", "monsoon": "monsoon", "rainy": "monsoon", "rain": "monsoon",
                 "spring": "spring", "autumn": "autumn", "fall": "autumn", "snow": "winter", "cold": "winter", "chilly": "winter"}
_BUDGET = re.compile(
    r"(?:under|below|within|upto|up to|max(?:imum)?|budget(?: is| of)?(?: around| about)?|around|about|less than|₹|rs\.?|inr)\s*"
    r"(?:rs\.?|inr|₹)?\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(k|thousand)?", re.IGNORECASE)


def extract_budget(text: str) -> Optional[float]:
    """Read a budget the way people write it: 'under 5000', 'budget around 3k', '₹2,500'. None when no amount is stated."""
    m = _BUDGET.search(text)
    if not m:
        return None
    value = float(m.group(1).replace(",", ""))
    return value * 1000 if m.group(2) else value


def ground_season(text: str) -> Optional[str]:
    """A season only when the shopper wrote a season word or a month."""
    words = re.findall(r"[a-z]+", text.lower())
    for w in words:
        if w in _SEASON_WORDS:
            return _SEASON_WORDS[w]
        if w in _MONTH_SEASON:
            return _MONTH_SEASON[w]
    return None


# "girl" and "boy" mean a young woman or man in everyday Indian English, but the product catalogues use Girls and Boys for children.
# Keep the child meaning only when the request has a child cue (added 2026-10-14 after the blind test: "date night girl" returned kids' dresses).
_CHILD_CUES = re.compile(r"\b(kid|kids|child|children|toddler|toddlers|baby|babies|infant|newborn|school|little|preschool|"
                         r"[0-9]+\s?(y|yr|yrs|year|years|month|months|m)|[0-9]+t)\b", re.IGNORECASE)
_KID_WORDS = re.compile(r"\b(girl|girls|boy|boys)(?:'s|s')?\b", re.IGNORECASE)
_PREFIX = {"men": "men's", "women": "women's", "boys": "boys'", "girls": "girls'"}
_HAS_GENDER_WORD = re.compile(r"\b(men|mens|men's|man|male|women|womens|women's|woman|female|ladies|boys|boy|girls|girl|boys'|girls'|unisex)\b", re.IGNORECASE)


def qualify(plan: Plan, text: str) -> Plan:
    """Put the gender into every piece and into main_query ("men's winter wedding shoes"). Without it, a search for
    "winter wedding shoes" returns women's heels for a male guest. Also turns an adult "girl"/"boy" into women/men."""
    if plan.gender in ("girls", "boys") and not _CHILD_CUES.search(text):
        adult = "women" if plan.gender == "girls" else "men"
        plan.notes.append(f"gender {plan.gender} -> {adult}: no child cue in the request")
        plan.gender = adult
        plan.main_query = _KID_WORDS.sub("", plan.main_query).strip()
        for pc in plan.pieces:
            pc.search_text = _KID_WORDS.sub("", pc.search_text).strip()
    pre = _PREFIX.get(plan.gender)
    if pre:
        if not _HAS_GENDER_WORD.search(plan.main_query):
            plan.main_query = f"{pre} {plan.main_query}".strip()
        for pc in plan.pieces:
            if pc.search_text and not _HAS_GENDER_WORD.search(pc.search_text):
                pc.search_text = f"{pre} {pc.search_text}".strip()
    return plan


def ground(plan: Plan, text: str) -> Plan:
    """Remove what the shopper did not say (colours, gender, season) and read the budget with code instead of the model."""
    low = text.lower()
    words = set(re.findall(r"[a-z]+", low))
    plan.budget_inr = extract_budget(text)
    plan.season = ground_season(text)

    def written(colour: str) -> bool:
        parts = re.findall(r"[a-z]+", colour.lower())
        return bool(parts) and all(p in words for p in parts)

    for piece in plan.pieces:
        piece.colours = [c for c in piece.colours if written(c)]
    cues = {g for g, pat in _GENDER_CUES.items() if re.search(pat, low)}
    if plan.gender != "unknown":
        if not (cues & _SAME_GROUP.get(plan.gender, {plan.gender})):
            plan.gender = "unknown"
    else:
        # added 2026-10-13 after seeing the held-out failures ("male guest", "my mom" came back unknown): read a clear cue directly
        clear = cues - {"unisex"}
        if len(clear) == 1:
            plan.gender = next(iter(clear))
    return plan


def make_chain(model: str = "qwen3:4b-instruct", temperature: float = 0.0, seed: int = 0):
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_ollama import ChatOllama

    # num_predict stops a runaway generation (one call once ran 573 s); the timeout makes understand() fall back instead of hanging
    llm = ChatOllama(model=model, temperature=temperature, seed=seed, num_ctx=4096, num_predict=500, client_kwargs={"timeout": 90})
    prompt = ChatPromptTemplate.from_messages([("system", "{system}"), ("human", "Request: {request}")])
    return prompt | llm.with_structured_output(Plan, method="json_schema")


# Ownership-phrasing patterns compiled at module level.
# Applied only when BOTH an ownership phrase AND a compatibility question appear.
_OWN_PHRASE = re.compile(
    r"\b(?:i\s+(?:have|own|already\s+have|'?m\s+wearing)|wearing\s+my|i\s+already\s+own)\s+(?:a\s+)?",
    re.IGNORECASE,
)
# A bare "my" signals ownership ONLY when a compatibility question is also present.
# "my kurta and jeans" (no question) → both requested; not ownership.
_MY_PREFIX = re.compile(r"\bmy\s+(?:[a-z]+\s+){0,2}", re.IGNORECASE)
_COMPAT_Q = re.compile(
    r"\b(?:what|which|suggest|recommend)\b.{0,50}\b(?:go|goes|work|works|match|matches|pair|pairs|suits?|wear)\s+(?:with|for)\b",
    re.IGNORECASE,
)


def _garments_from_text(text: str) -> "tuple[list[Piece], list[str]] | None":
    """Deterministic multi-garment recovery for bare fallback plans.

    Returns (pieces, already_has) when two or more distinct non-dress outfit slots are
    found, or None to keep the whole-sentence fallback unchanged.

    Enhancements over the initial version:
    - Colour words from checks.COLOUR_FAMILY that appear before each garment in the
      text are prepended to its search_text ("black kurta", "blue jeans").
    - When an explicit ownership phrase precedes a garment AND a compatibility question
      is also present in the query, that garment goes into already_has instead of
      pieces.  Without the compatibility question "my kurta and jeans" is treated as a
      request for both garments.

    Conservative rules:
    - At least two distinct non-dress slots must remain as pieces after ownership removal.
    - Any dress-category match (saree, lehenga, co-ord …) → return None.
    """
    from genkart.checks import _KIND_RE, COLOUR_FAMILY  # type: ignore[attr-defined]

    low = text.lower()
    colour_keys = set(COLOUR_FAMILY.keys())

    # ── Ownership context ─────────────────────────────────────────────────────
    has_compat_q = bool(_COMPAT_Q.search(low))
    own_ends: list[int] = []   # end positions of ownership-prefix spans
    for m in _OWN_PHRASE.finditer(low):
        own_ends.append(m.end())
    if has_compat_q:
        for m in _MY_PREFIX.finditer(low):
            own_ends.append(m.end())

    def _is_owned(garment_start: int) -> bool:
        # garment immediately follows an ownership prefix (allow tiny gap for word boundary)
        return any(abs(garment_start - oe) <= 3 for oe in own_ends)

    # ── Garment matches ───────────────────────────────────────────────────────
    raw_hits: list[tuple[int, int, str, str]] = []   # (start, end, slot, word)
    seen: set[str] = set()
    for slot in ("top", "bottom", "dress", "outerwear", "footwear", "accessory"):
        if slot in seen:
            continue
        m = _KIND_RE[slot].search(low)
        if m:
            raw_hits.append((m.start(), m.end(), slot, m.group(0)))
            seen.add(slot)

    raw_hits.sort()

    if any(slot == "dress" for _, _, slot, _ in raw_hits):
        return None   # dress-category = potentially complete outfit; don't split

    # ── Classify hits and build pieces ────────────────────────────────────────
    pieces_out: list[Piece] = []
    owned_out: list[str] = []
    prev_end = 0

    for start, end, slot, word in raw_hits:
        # Colours in the text segment before this garment
        segment = low[prev_end:start]
        colour_words = [w for w in re.findall(r"[a-z]+", segment) if w in colour_keys]
        search_text = " ".join(colour_words + [word])
        prev_end = end

        if has_compat_q and _is_owned(start):
            owned_out.append(search_text)
        else:
            pieces_out.append(Piece(kind=slot, search_text=search_text))

    if len(pieces_out) < 1:
        return None   # no recoverable piece found; keep whole-sentence fallback

    return pieces_out, owned_out


def finish(plan: Plan, text: str) -> Plan:
    """The checks every model's answer goes through, whichever model gave it: keep only what the shopper wrote, add the gender, never return nothing to search."""
    plan = qualify(ground(plan, text), text)
    if not plan.main_query.strip():
        plan.main_query = text
    if not plan.pieces:  # added 2026-10-13 after two empty plans on the held-out prompts: always keep something searchable
        plan.pieces = [Piece(kind="other", search_text=plan.main_query)]
    # When the plan is still a bare whole-sentence fallback (one kind="other" piece
    # whose search_text is the full query), try to recover explicit garments from the
    # text.  Two or more recognised non-dress slots are enough to split; anything
    # ambiguous (dress-category item, single garment, no garment found) stays as-is.
    if len(plan.pieces) == 1 and plan.pieces[0].kind == "other":
        result = _garments_from_text(text)
        if result:
            recovered, already_has = result
            plan.pieces = recovered
            if already_has:
                # dedup while preserving order
                existing = list(plan.already_has)
                for item in already_has:
                    if item not in existing:
                        existing.append(item)
                plan.already_has = existing
            plan.notes.append(
                "garments read from text: "
                + ", ".join(f"{p.search_text} [{p.kind}]" for p in recovered)
                + (f"; already owns: {', '.join(already_has)}" if already_has else "")
                + " (model unavailable — multi-garment recovery)"
            )
    return plan


def understand(text: str, chain=None, version: str = "v2") -> tuple[Plan, float]:
    """Return (grounded plan, seconds). Falls back to a plan that just searches the raw text if the model fails."""
    chain = chain or make_chain()
    t = time.time()
    try:
        plan = chain.invoke({"system": SYSTEMS[version], "request": text})
        if plan is None:
            raise ValueError("no structured output")
        plan = finish(plan, text)
    except Exception:
        plan = Plan(main_query=text, gender="unknown", pieces=[Piece(kind="other", search_text=text)])
    return plan, time.time() - t

