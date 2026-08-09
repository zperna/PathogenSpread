# CLAUDE.md

## Project purpose
This workspace contains a prototype Python project for pathogen spread risk modeling. The current goal is to build an explainable, extensible risk-flagging system for tree health and invasive pathogen scenarios.

## Working stance
This project should be treated as a contract-first, artifact-chained development effort:
- Start with a clear contract for each feature or change.
- Produce or update artifacts in sequence before implementation is considered complete.
- Keep changes grounded in evidence and verification.
- Avoid overstating predictive accuracy; frame the work as a prototype scaffold unless the contract explicitly requires validation.

## Core design principles
- Keep the spread engine generic and reusable.
- Store pathogen behavior in configuration dictionaries rather than hard-coding logic.
- Prefer explainable, simple math over opaque black-box behavior.
- Keep the code modular so new data sources, kernels, and time steps can be added later.

## Repository conventions
- Main code lives in the PathogenPy directory.
- The engine should accept a pandas DataFrame inventory plus pathogen configuration and optional environment data.
- New features should be implemented in a way that preserves the existing prototype architecture.
- Any change that affects modeling behavior should include a short verification note.

## Artifact chain workflow
For each feature, follow this chain:
1. Contract: define the problem, scope, inputs, outputs, and success criteria.
2. Design note: describe the implementation approach and any assumptions.
3. Implementation: build the feature in code.
4. Verification: run the relevant script or test and capture the result.
5. Update summary: record what changed and what remains for the next iteration.

## Suggested artifact locations
- docs/project_contract.md: overall product contract and roadmap.
- docs/feature_contracts/: one contract file per feature.
- docs/notes/: design notes and implementation summaries.

## Definition of done
A task is not complete until:
- the contract is written or updated,
- the implementation exists,
- the relevant code runs without breaking the current workflow,
- and the result is summarized in an artifact.
