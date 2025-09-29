"""Minimal reproduction for the PDF attachment prompt sensitivity in OpenAI Responses.

Uploading the shared PDF fixture and asking for a summary makes ``gpt-4.1`` insist
that no file was provided. Repeating the secret phrase works for ``gpt-4.1`` and
``gpt-5`` (temperature must be omitted), while ``gpt-4o`` continues to refuse.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from openai import AsyncOpenAI

PDF_PATH = Path("tests/data/files/test-pdf.pdf")
SUMMARY_PROMPT = "What content do you see in the attached PDF file? Please summarize what you find."
SECRET_PHRASE_PROMPT = "Please repeat the secret phrase attached."
INSTRUCTIONS = "You are a precise assistant. Answer user questions directly."
FOLLOW_UP_MODELS: tuple[tuple[str, float | None], ...] = (
    ("gpt-4o", 0.0),
    ("gpt-5", None),
)


async def _wait_for_file_processed(client: AsyncOpenAI, file_id: str, *, timeout: float = 60.0) -> None:
    """Poll OpenAI until the uploaded file reports a processed status."""
    deadline = time.monotonic() + timeout
    while True:
        file_info = await client.files.retrieve(file_id)
        status = getattr(file_info, "status", None)
        if status == "processed":
            return
        if status in {"failed", "error", "deleted"}:
            raise RuntimeError(f"File {file_id} entered unexpected status: {status}")
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Timed out waiting for file {file_id} to process (last status: {status})")
        await asyncio.sleep(1)


async def query_model(
    client: AsyncOpenAI,
    *,
    file_id: str,
    model_name: str,
    prompt: str,
    temperature: float | None,
) -> str:
    response = await client.responses.create(
        model=model_name,
        instructions=INSTRUCTIONS,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_file", "file_id": file_id},
                ],
            }
        ],
        **({"temperature": temperature} if temperature is not None else {}),
    )
    return response.output_text or ""


async def main() -> None:
    if not PDF_PATH.exists():
        raise SystemExit(f"Missing reproduction asset at {PDF_PATH}")

    client = AsyncOpenAI()
    uploaded = await client.files.create(file=PDF_PATH.open("rb"), purpose="assistants")
    file_id = uploaded.id
    print(f"Uploaded {PDF_PATH.name}: {file_id}")

    try:
        await _wait_for_file_processed(client, file_id)
        failing_output = await query_model(
            client,
            file_id=file_id,
            model_name="gpt-4.1",
            prompt=SUMMARY_PROMPT,
            temperature=0.0,
        )
        print("\n=== gpt-4.1 with summarization prompt ===")
        print(f"Prompt: {SUMMARY_PROMPT!r}")
        print(f"Response: {failing_output}")

        succeeding_output = await query_model(
            client,
            file_id=file_id,
            model_name="gpt-4.1",
            prompt=SECRET_PHRASE_PROMPT,
            temperature=0.0,
        )
        print("\n=== gpt-4.1 with secret phrase prompt ===")
        print(f"Prompt: {SECRET_PHRASE_PROMPT!r}")
        print(f"Response: {succeeding_output}")

        # Re-use the processed file for the remaining models.
        for model_name, temperature in FOLLOW_UP_MODELS:
            output = await query_model(
                client,
                file_id=file_id,
                model_name=model_name,
                prompt=SECRET_PHRASE_PROMPT,
                temperature=temperature,
            )
            print("\n=== Responses API call ===")
            print(
                f"Model: {model_name}\nPrompt: {SECRET_PHRASE_PROMPT!r}\nInstructions: {INSTRUCTIONS!r}\nResponse: {output}"
            )
    finally:
        await client.files.delete(file_id)


if __name__ == "__main__":
    asyncio.run(main())
