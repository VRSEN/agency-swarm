from __future__ import annotations

"""Minimal reproduction for the PDF attachment regression in OpenAI Responses.

This script uploads the shared PDF fixture and sends the *same* prompt and
instructions to multiple models. ``gpt-4.1`` and ``gpt-5`` repeat the secret
phrase, while ``gpt-4o`` refuses the request even though the PDF is attached.
"""

import asyncio
from pathlib import Path

from openai import AsyncOpenAI

PDF_PATH = Path("tests/data/files/test-pdf.pdf")
PROMPT = "Please repeat the secret phrase attached."
INSTRUCTIONS = "You are a precise assistant. Answer user questions directly."
MODELS: tuple[tuple[str, float | None], ...] = (
    ("gpt-4.1", 0.0),
    ("gpt-4o", 0.0),
    ("gpt-5", None),
)


async def query_model(client: AsyncOpenAI, *, file_id: str, model: tuple[str, float | None]) -> str:
    name, temperature = model
    response = await client.responses.create(
        model=name,
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
        for model in MODELS:
            output = await query_model(client, file_id=file_id, model=model)
            print("\n=== Responses API call ===")
            print(
                "Model: {name}\nPrompt: {prompt!r}\nInstructions: {instructions!r}\nResponse: {response}".format(
                    name=model[0], prompt=PROMPT, instructions=INSTRUCTIONS, response=output
                )
            )
    finally:
        await client.files.delete(file_id)


if __name__ == "__main__":
    asyncio.run(main())
