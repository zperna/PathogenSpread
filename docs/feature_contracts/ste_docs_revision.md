# Feature contract: STE documentation revision

## Problem
The project `CLAUDE.md` now sets a writing style: Simplified Technical
English (STE). The README and docs were written before this rule. They use
long sentences, many dashes, and some figurative phrasing.

## Scope
- In scope: `README.md` and all Markdown files under `docs/`.
- In scope (added later): docstrings and `#` comments in `PathogenPy/`.
- Out of scope: executable Python code, string literals, and `CLAUDE.md`.

## Inputs
- The writing-style rules in `CLAUDE.md`.
- The current text of each in-scope file.

## Outputs
- The same files, rewritten in place in STE.

## Rules
1. Short declarative sentences with one idea each.
2. No metaphors. Plain words.
3. Em dashes and `--` in prose used rarely.
4. Ordered steps as numbered lists.
5. Brief explanations with natural variation in sentence structure.

## Constraints
- Keep every fact, number, path, function name, config key, and caveat.
- Keep code blocks, inline code, tables, links, and images unchanged.
- Do not soften the prototype and calibration caveats.

## Success criteria
- Each in-scope file reads as STE.
- No technical content is lost or changed.
- No code changes. Tests still pass.
