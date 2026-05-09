"""
LLM Configuration — Google Gemini via LangChain
"""

import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()


def get_llm(temperature: float = 0.0) -> ChatGoogleGenerativeAI:
    """Get a configured Gemini LLM instance."""
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key or api_key == "your_gemini_api_key_here":
        raise ValueError(
            "GOOGLE_API_KEY not set. "
            "Copy .env.example to .env and add your key from https://aistudio.google.com/apikey"
        )

    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    return ChatGoogleGenerativeAI(
        model=model,
        google_api_key=api_key,
        temperature=temperature,
        convert_system_message_to_human=False,
    )


def extract_text(response) -> str:
    """Safely extract text from an LLM response.

    response.content may be a str or a list of content blocks (Gemini).
    This normalises it to a plain string.
    """
    content = response.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(block.get("text", ""))
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return str(content)
