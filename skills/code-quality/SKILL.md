---
name: code-quality
description: Enforce SOLID principles, file/class size limits, and systematic refactoring. Activate when writing new code, reviewing for design issues, or refactoring existing projects. Replaces and integrates code-excellence, solid-principles, simplify skills.
---

# Code Quality — Meta-Skill

Integrates: `code-excellence` + `solid-principles` + `simplify`

## Trigger

Use when:
- Writing new code (SOLID-first design)
- Reviewing existing code for design issues
- Refactoring a project structure
- User asks to "simplify", "clean up", or "improve" code

## Mode Routing

| Input | Mode |
|---|---|
| New feature / new file | **Mode A: Design** |
| Existing project refactor | **Mode B: Refactor** |
| Code review / PR | **Mode C: Review** |

---

## Mode A — New Code Design (SOLID-First)

1. Define **Protocol/Interface** before implementation
2. Apply SRP: one class = one responsibility
3. Use dependency injection over direct instantiation
4. File targets: <500 lines (max 800), class <225 lines (max 450)
5. Ask before writing: will this file stay under 500 lines?

```python
# GOOD
class DataLoader(Protocol):
    def load(self, path: str) -> pd.DataFrame: ...

class CSVLoader:
    def __init__(self, validator: DataValidator):
        self.validator = validator  # injected

    def load(self, path: str) -> pd.DataFrame:
        ...
```

---

## Mode B — Project Refactoring (5-Phase)

### Phase 1: Analyze
- Map file sizes (🔴 >800 lines, 🟡 >500, 🟢 <500)
- Identify SOLID violations, duplication
- Generate improvement plan → **get user approval before proceeding**

### Phase 2: Restructure
- Create `src/`, `tests/`, `scripts/` layout
- Split oversized files by concern
- Update all import paths

### Phase 3: SOLID Verification
- Detect SRP violations (classes named "Manager", "Handler", "Utility")
- Apply Protocol-first patterns
- Remove `isinstance()` type-dispatch anti-patterns

### Phase 4: Deduplication
- Extract common base classes
- Create shared utility modules

### Phase 5: Integration
- Validate all imports work
- Create `cli.py` entry point if needed
- Update `requirements.txt`

---

## Mode C — Code Review / Simplify

Check in order:
1. Can any function be split? (>50 lines = consider)
2. Is there repeated logic? → extract helper
3. Are there unnecessary abstractions?
4. Do variable names clearly express intent?
5. Can `isinstance` chains be replaced with Protocol dispatch?

**Rule:** Three similar lines of code is better than a premature abstraction.

---

## Red Flags

| Signal | Issue |
|---|---|
| Class named "Manager", "Handler" | SRP violation |
| Method name contains "and" | Multiple responsibilities |
| Direct `DB()`, `Client()` instantiation | DIP violation |
| `isinstance` chains | OCP violation |
| >800 line files | Split required |
| >450 line classes | Split required |

---

## Replaces

- `deprecated/code-excellence` — architecture and refactoring workflow
- `deprecated/solid-principles` — SOLID principle enforcement
- `deprecated/code-validator` — code review and debugging
- `deprecated/code-implementer` — implementation guidance
