# Comment Mode — Word comment insertion classification scheme (manuscript-pipeline reference)

Categorizes real-world author/mentor comment patterns. Attach a prefix tag when writing a comment so a reviewer can identify it at a glance.

## Prefix tags (first word of the Word comment)

| Tag | Meaning | Example |
|---|---|---|
| `[STRUCTURE]` | big picture — story line, paragraph organization, where the novelty sits | "The last paragraph is the crux. This is where the significance/differentiation/approach needs to appear" |
| `[FLOW]` | awkward context/flow | "This feels off in context — why is this sentence here?" |
| `[NOVELTY]` | requires an explicit statement of differentiation/novelty | "What prior work couldn't do -> frame it as a complement/addition" |
| `[NUMBERING]` | duplicate/out-of-order Figure/Table numbers | "Table 2 is duplicated: renumber one to Table 3" |
| `[ABBREV]` | abbreviation not standardized, or missing its definition | "ADP-glucose -> standardize to ADP-Glc throughout" |
| `[NOMENCLATURE]` | nomenclature (enzyme italics, species italics) | "EcXylA -> *Ec*XylA" |
| `[CITATION-LOC]` | citation placement (should be at end of sentence) | "Citation number is at the start of the sentence -> move to the end" |
| `[CITATION-MISSING]` | a key piece of prior work is missing [Critical] | "Need to add You et al. (2013) PNAS 110:7182" |
| `[METHODS-RESULTS]` | Methods vs. Results inconsistency | "Stated the temperature range as 30-50°C, but Results says 20°C" |
| `[UNIT]` | unit notation | "Please write this as mM" |
| `[FIGURE-FORMAT]` | figure numbering/subplot convention | "1.1, 1.2 -> should be 1a, 1b" |
| `[TYPO]` | typo | "brancing -> branching" |
| `[BALANCE]` | section length balance | "The food-crisis section takes up ~25% -> condense to 3-4 sentences" |
| `[DEFINE]` | term definition needs clarifying | "The relationship between branched starch and glycogen-like glucan is unclear" |
| `[EXPAND]` | needs more length | "Expand the lignocellulose section by at least one paragraph" |
| `[GRAMMAR]` | Korean grammar (for a Korean-language manuscript) | "'며.' -> a comma, or a period followed by a new sentence" |

## The Critical marker

Appending a `[Critical]` suffix to a comment flags "if this isn't fixed, the reviewer will likely reject it". Real-world examples: a missing key piece of prior work, a Methods/Results contradiction, no stated novelty.

## Output format

When inserting a Word comment, state the author's name (`Claude` or a specific agent name) — so it's distinguishable from a comment a human (author/mentor) left. The comment anchor's id = existing max + 1; commentRangeStart is inserted at a run boundary that is a direct child of `w:p`.

## Separating mentor-style vs. detail-style comments

- **Mentor-style** (big picture): `[STRUCTURE]`, `[FLOW]`, `[NOVELTY]`, `[BALANCE]`
- **Detail-style** (concrete action): `[NUMBERING]`, `[ABBREV]`, `[UNIT]`, `[CITATION-LOC]`, `[TYPO]`
- Do not mix both styles in one comment — split them into separate comments.
