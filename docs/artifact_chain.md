# Artifact-chained development workflow

## Principle
Treat each change as a small deliverable that passes through a chain of artifacts:

1. Contract
   - State the problem, scope, inputs, outputs, and definition of done.
2. Design note
   - Explain the implementation approach, data assumptions, and limitations.
3. Implementation
   - Write the code and keep it aligned with the contract.
4. Verification
   - Run the relevant workflow and capture evidence.
5. Summary
   - Record the result, next steps, and any unresolved questions.

## Recommended file pattern
- docs/feature_contracts/<feature_name>.md
- docs/notes/<feature_name>.md
- docs/summaries/<feature_name>.md

## Example for this repo
If we add a new feature such as CSV input support or a time-step model, the sequence would be:
- create a feature contract,
- write a short design note,
- implement the change,
- run the prototype,
- add a summary note with verification evidence.
