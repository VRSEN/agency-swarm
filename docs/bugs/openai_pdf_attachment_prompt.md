# OpenAI Responses PDF Attachment Prompt Sensitivity

## Summary
- The prompt wording determines whether `gpt-4.1` acknowledges an attached PDF. Asking it to “summarize” the document frequently yields "I do not see any file attached," even though the API confirms the file ID.
- Rephrasing the user message to `"Please repeat the secret phrase attached."` consistently surfaces the PDF content for `gpt-4.1` and `gpt-5` (temperature must be omitted for `gpt-5`).
- `gpt-4o` still refuses to echo the PDF contents regardless of wording, so the integration tests remain pinned to `gpt-4.1` while we await an upstream fix.

## Minimal Reproduction
Run:

```bash
uv run python examples/minimal_pdf_prompt_repro.py
```

Example output (abridged):

```
=== gpt-4.1 with summarization prompt ===
Prompt: "What content do you see in the attached PDF file? Please summarize what you find."
Response: Please upload the PDF file you would like me to review. Once you upload it, I will summarize its contents for you.

=== gpt-4.1 with secret phrase prompt ===
Prompt: "Please repeat the secret phrase attached."
Response: Your secret phrase for docx is: FIRST PDF SECRET PHRASE

=== gpt-4o with secret phrase prompt ===
Response: I'm sorry, I can't assist with that.

=== gpt-5 with secret phrase prompt ===
Response: FIRST PDF SECRET PHRASE
```

This reproduction mirrors the failing and passing integration prompts. No additional delay is required once the phrasing is updated, but the script still waits for the PDF to reach the `processed` state for completeness.

## Impact
- Integration tests and sample agents must use the deterministic secret-phrase prompt whenever they validate PDF attachments.
- Documentation and reproductions should highlight the working phrasing so the issue can be escalated to OpenAI with clear evidence.
- Additional attachments (such as images) remain subject to the same prompt sensitivity, so tests now check the returned `file_ids_map` whenever they mix attachment types.

## Workaround
- Keep polling `client.files.retrieve(file_id)` until the status is `processed`, then query using the exact secret-phrase prompt.
- Avoid `gpt-4o` for deterministic attachment verification until its refusal is resolved upstream.
