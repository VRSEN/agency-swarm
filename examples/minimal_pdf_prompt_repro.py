"""Minimal reproduction for the PDF attachment regression in OpenAI Responses.

This script uploads the shared PDF fixture and sends the *same* prompt and
instructions to multiple models. ``gpt-4.1`` and ``gpt-5`` repeat the secret
phrase, while ``gpt-4o`` refuses the request even though the PDF is attached.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from openai import AsyncOpenAI

PDF_PATH = Path("tests/data/files/test-pdf.pdf")
PROMPT = "Please repeat the secret phrase attached."
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
    temperature: float | None,
) -> str:
    response = await client.responses.create(
        model=model_name,
        instructions=INSTRUCTIONS,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": PROMPT},
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
        # Immediate query without waiting for processing.
        no_wait_output = await query_model(client, file_id=file_id, model_name="gpt-4.1", temperature=0.0)
        print("\n=== Immediate call (no wait) ===")
        print(no_wait_output)

        # Poll until OpenAI finishes processing, then retry.
        await _wait_for_file_processed(client, file_id)
        waited_output = await query_model(client, file_id=file_id, model_name="gpt-4.1", temperature=0.0)
        print("\n=== After waiting for processing ===")
        print(waited_output)

        # Re-use the processed file for the remaining models.
        for model_name, temperature in FOLLOW_UP_MODELS:
            output = await query_model(
                client,
                file_id=file_id,
                model_name=model_name,
                temperature=temperature,
            )
            print("\n=== Responses API call ===")
            print(
                f"Model: {model_name}\nPrompt: {PROMPT!r}\nInstructions: {INSTRUCTIONS!r}\nResponse: {output}"
            )
    finally:
        await client.files.delete(file_id)


if __name__ == "__main__":
    asyncio.run(main())
