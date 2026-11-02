# Artifact-chained development workflow

## Principle
Treat each change as a small deliverable. It passes through a chain of artifacts.

1. Contract
   - State the problem, scope, inputs, outputs, and definition of done.
2. Design note
   - Explain the implementation approach, data assumptions, and limitations.
3. Implementation
   - Write the code. Keep it aligned with the contract.
4. Verification
   - Run the relevant workflow. Capture the evidence.
5. Summary
   - Record the result, next steps, and any unresolved questions.

## Recommended file pattern
- docs/feature_contracts/<feature_name>.md
- docs/notes/<feature_name>.md
- docs/summaries/<feature_name>.md

## Example for this repo
If we add a new feature, such as CSV input support or a time-step model, follow this sequence:
1. Create a feature contract.
2. Write a short design note.
3. Implement the change.
4. Run the prototype.
5. Add a summary note with verification evidence.
