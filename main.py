import os
import sys
import requests
from dotenv import load_dotenv


HACKCLUB_CHAT_COMPLETIONS_URL = "https://ai.hackclub.com/proxy/v1/chat/completions"
OPUS_MODEL = "anthropic/claude-opus-4.8"
TAVILY_SEARCH_URL = "https://api.tavily.com/search"


def require_env(name):
    value = os.getenv(name)
    if not value:
        print(f"Missing {name}. Add it to .env first.", file=sys.stderr)
        sys.exit(1)
    return value


def read_user_clues():
    if not sys.stdin.isatty():
        user_input = sys.stdin.read().strip()
    else:
        print("Enter your clues. Submit a blank line when done:\n")
        lines = []
        while True:
            line = input("> ")
            if not line:
                break
            lines.append(line)
        user_input = "\n".join(lines).strip()

    if not user_input:
        print("No clues provided.", file=sys.stderr)
        sys.exit(1)
    return user_input


def rephrase_for_tavily(user_clues, hackclub_api_key):
    system_prompt = """
You are AISINT's Search Planner.

Turn the user's plain-English OSINT clues into one precise Tavily web search query.

Rules:
- Output only the query text.
- Do not explain.
- Preserve important names, usernames, organizations, locations, domains, and skills.
- Use quotes around exact names, usernames, domains, and distinctive phrases.
- Add high-signal context words only when they improve discovery.
- Do not invent facts that are not in the user's clues.
- Keep it under 180 characters.
""".strip()

    response = requests.post(
        HACKCLUB_CHAT_COMPLETIONS_URL,
        headers={
            "Authorization": f"Bearer {hackclub_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": OPUS_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_clues},
            ],
            "temperature": 0.7,
            "max_tokens": 1000,
        },
        timeout=60,
    )
    response.raise_for_status()

    data = response.json()
    query = data["choices"][0]["message"]["content"].strip()
    return " ".join(query.split())


def search_tavily(query, tavily_api_key):
    response = requests.post(
        TAVILY_SEARCH_URL,
        json={
            "api_key": tavily_api_key,
            "query": query,
            "search_depth": "basic",
            "max_results": 5,
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def print_results(query, data):
    results = data.get("results", [])

    print(f"\nOpus Tavily query:\n{query}\n")
    print(f"Found {len(results)} results:\n")

    for i, result in enumerate(results, start=1):
        print("=" * 60)
        print(f"RESULT #{i}")
        print(f"TITLE: {result.get('title', 'Untitled')}")
        print(f"URL: {result.get('url', 'No URL')}")
        print(f"SCORE: {result.get('score', 'N/A')}")
        print(f"CONTENT: {result.get('content', '')}")
        print()


def main():
    load_dotenv(".env")

    tavily_api_key = require_env("TAVILY_API_KEY")
    hackclub_api_key = require_env("HACKCLUB_API_KEY")

    user_clues = read_user_clues()

    try:
        tavily_query = rephrase_for_tavily(user_clues, hackclub_api_key)
        data = search_tavily(tavily_query, tavily_api_key)
    except requests.HTTPError as error:
        print(f"Request failed: {error}", file=sys.stderr)
        print(error.response.text, file=sys.stderr)
        sys.exit(1)
    except requests.RequestException as error:
        print(f"Network error: {error}", file=sys.stderr)
        sys.exit(1)

    print_results(tavily_query, data)


if __name__ == "__main__":
    main()
