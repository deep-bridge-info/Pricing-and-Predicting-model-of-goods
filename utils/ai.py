"""Ollama API helper with retry."""
import json
import os
import re
from typing import Optional

from openai import OpenAI
import openai

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3:8b")


def call_ai(prompt: str, timeout: int = 180) -> Optional[dict]:
    """Call local Ollama model and parse JSON response.

    Returns parsed JSON dict, or None on failure.
    Retries once on error.
    """
    client = OpenAI(
        base_url=OLLAMA_BASE_URL,
        api_key='ollama',  # required but can be any string
        timeout=timeout,
    )

    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=OLLAMA_MODEL,
                messages=[
                    {"role": "system", "content": "You are a data extraction assistant. Always respond with valid JSON only, no markdown or explanation."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
            )
            content = response.choices[0].message.content
            return _extract_json(content)

        except openai.APITimeoutError:
            if attempt == 0:
                print(f"[AI] Retry after timeout ({timeout}s)")
                continue
            print(f"[AI] Failed: timeout after {timeout}s")
            return None
        except openai.APIError as e:
            if attempt == 0:
                print(f"[AI] Retry after API error: {e}")
                continue
            print(f"[AI] Failed: {e}")
            return None
        except (KeyError, IndexError, AttributeError) as e:
            print(f"[AI] Unexpected response format: {e}")
            return None

    return None


def _extract_json(text: str) -> Optional[dict]:
    """Extract JSON object from text that may contain non-JSON content."""
    text = text.strip()

    # Strip markdown code fences
    if "```json" in text:
        match = re.search(r"```json\s*([\s\S]*?)\s*```", text)
        if match:
            text = match.group(1).strip()
    elif "```" in text:
        match = re.search(r"```\s*([\s\S]*?)\s*```", text)
        if match:
            text = match.group(1).strip()

    # Try full text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try raw_decode from first '{'
    start = text.find('{')
    if start == -1:
        return None

    try:
        obj, _ = json.JSONDecoder().raw_decode(text, start)
        return obj
    except json.JSONDecodeError:
        return None
