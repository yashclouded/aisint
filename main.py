import json
import logging
import os
import sys
from io import BytesIO
import requests
from dotenv import load_dotenv
from pypdf import PdfReader


logging.getLogger("pypdf").setLevel(logging.ERROR)

HACKCLUB_CHAT_COMPLETIONS_URL = "https://ai.hackclub.com/proxy/v1/chat/completions"
OPUS_MODEL = "anthropic/claude-opus-4.8"
TAVILY_SEARCH_URL = "https://api.tavily.com/search"



def require_env(name):
    value = os.getenv(name)
    if not value:
        print(f"Missing {name}. Add it to .env first.", file=sys.stderr)
        sys.exit(1)
    return value


def get_int_env(name, default):
    value = os.getenv(name, str(default))
    try:
        parsed = int(value)
    except ValueError:
        print(f"{name} must be a number.", file=sys.stderr)
        sys.exit(1)

    if parsed < 1:
        print(f"{name} must be at least 1.", file=sys.stderr)
        sys.exit(1)

    return parsed


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


def chat_with_opus(hackclub_api_key, messages, max_tokens, temperature=0.2):
    response = requests.post(
        HACKCLUB_CHAT_COMPLETIONS_URL,
        headers={
            "Authorization": f"Bearer {hackclub_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": OPUS_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"].strip()


def parse_json_response(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


def parse_json_or_fallback(text, fallback):
    try:
        return parse_json_response(text)
    except json.JSONDecodeError:
        fallback["notes"] = fallback.get("notes", [])
        fallback["notes"].append("Model returned malformed JSON; showing raw excerpt.")
        fallback["notes"].append(text[:1000])
        return fallback


def rephrase_for_tavily(user_clues, hackclub_api_key, max_tokens):
    system_prompt = """
You are AISINT's Search Planner.

Turn the user's plain-English OSINT clues into one precise Tavily web search query.

Rules:
- Output only the query text.
- Do not explain.
- Fix the spelling (specially in proper noun) and grammar of the clues, but do not add or remove any meaning.
- Preserve important names, usernames, organizations, locations, domains, and skills.
- Use quotes around exact names, usernames, domains, and distinctive phrases.
- Add high-signal context words only when they improve discovery.
- Do not invent facts that are not in the user's clues - Unless it might give hint and is axiom e.g. "if they mention coding, maybe add 'github' as a hint word"
""".strip()

    query = chat_with_opus(
        hackclub_api_key,
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_clues},
        ],
        max_tokens=max_tokens,
        temperature=0.2,
    )
    return " ".join(query.split())


def search_tavily(query, tavily_api_key, max_results):
    response = requests.post(
        TAVILY_SEARCH_URL,
        json={
            "api_key": tavily_api_key,
            "query": query,
            "search_depth": "basic",
            "max_results": max_results,
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def summarize_results_for_opus(results):
    summarized = []
    for index, result in enumerate(results, start=1):
        summarized.append(
            {
                "index": index,
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "score": result.get("score", ""),
                "content": result.get("content", "")[:900],
            }
        )
    return summarized


def make_singleton_cluster(index, result):
    return {
        "id": f"C{index}",
        "same_entity_confidence": 1.0,
        "merged_label": result.get("title", "Unmerged result"),
        "result_indexes": [index],
        "merged_facts": [result.get("content", "")[:200]],
        "why_same": ["Single candidate; no strong duplicate found."],
        "why_not_same": [],
    }


def normalize_merged_candidates(results, merged_candidates):
    result_by_index = {
        index: result
        for index, result in enumerate(results, start=1)
    }
    clusters = merged_candidates.get("clusters", [])
    covered_indexes = set()

    for cluster_index, cluster in enumerate(clusters, start=1):
        cluster.setdefault("id", f"C{cluster_index}")
        cluster.setdefault("same_entity_confidence", 0.0)
        cluster.setdefault("merged_label", "Candidate cluster")
        cluster.setdefault("result_indexes", [])
        cluster.setdefault("merged_facts", [])
        cluster.setdefault("why_same", [])
        cluster.setdefault("why_not_same", [])
        covered_indexes.update(cluster["result_indexes"])

    unmerged_indexes = merged_candidates.get("unmerged_result_indexes", [])
    for index in unmerged_indexes:
        if index in result_by_index and index not in covered_indexes:
            clusters.append(make_singleton_cluster(index, result_by_index[index]))
            covered_indexes.add(index)

    for index, result in result_by_index.items():
        if index not in covered_indexes:
            clusters.append(make_singleton_cluster(index, result))

    merged_candidates["clusters"] = clusters
    merged_candidates["unmerged_result_indexes"] = []
    return merged_candidates


def merge_similar_results(user_clues, query, results, hackclub_api_key, max_tokens):
    system_prompt = """
You are AISINT's Entity Merge Analyst.

Tavily may return multiple results for the same person or profile cluster.
Logically merge results that likely describe the same real-world person.

Return only JSON with this shape:
{
  "clusters": [
    {
      "id": "C1",
      "same_entity_confidence": 0.0,
      "merged_label": "short person/profile label",
      "result_indexes": [1, 2],
      "merged_facts": ["short combined fact"],
      "why_same": ["short reason these results are same entity"],
      "why_not_same": ["short uncertainty or contradiction"]
    }
  ]
}

Rules:
- Do not invent facts.
- Do not mess up - donot hesitate to not merge if uncertain.
- Merge 2 profiles if two of them have similar titles and overlapping content, even if the URLs are different.
- Every original result must appear in exactly one cluster.
- If a result has no duplicate, create a one-result cluster for it.
- Keep every string concise.
""".strip()
    payload = {
        "user_clues": user_clues,
        "query": query,
        "results": summarize_results_for_opus(results),
    }
    content = chat_with_opus(
        hackclub_api_key,
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(payload, indent=2)},
        ],
        max_tokens=max_tokens,
        temperature=0.1,
    )
    merged_candidates = parse_json_or_fallback(
        content,
        {
            "clusters": [
                make_singleton_cluster(index, result)
                for index, result in enumerate(results, start=1)
            ],
            "unmerged_result_indexes": [],
        },
    )
    return normalize_merged_candidates(results, merged_candidates)


def create_hypotheses(
    user_clues,
    tavily_query,
    results,
    merged_candidates,
    hackclub_api_key,
    max_tokens,
):
    system_prompt = """
You are AISINT's Investigation Planner.

Given the user's clues, Tavily results, and merged candidate clusters, create identity
hypotheses and clarifying questions that would help narrow the investigation.

Ask questions like:
- Is this person in college?
- Are they connected to a specific city?
- Is this GitHub/ any other social profile likely theirs?
- prettify results into short facts and use them as evidence in hypotheses
Return only JSON with this shape:
{
  "hypotheses": [
    {
      "id": "H1",
      "statement": "short hypothesis",
      "confidence": 0.0,
      "supporting_evidence": ["short evidence"],
      "contradictions": ["short contradiction or unknown"]
    }
  ],
  "questions": [
    {
      "question": "question for the user",
      "why": "what this will disambiguate"
    }
  ],
  "suggested_follow_up_query": "one Tavily query to get closer",
  "pdf_query": "one Tavily query focused on public PDFs"
}

Rules:
- Do not invent facts.
- Treat merged clusters as candidate people/profile groups.
- Do not create separate hypotheses for results that were merged into the same cluster.
- Confidence is between 0 and 1.
- Create at most 3 hypotheses.
- Ask at most 4 questions.
- Keep every string concise.
- If multiple colleges/schools appear, ask whether the target is connected to them.
- Make pdf_query use filetype:pdf when useful.
- Focus on hypotheses that would help identify the person's real-world identity, not just online profiles.
""".strip()

    payload = {
        "user_clues": user_clues,
        "tavily_query": tavily_query,
        "results": summarize_results_for_opus(results),
        "merged_candidates": merged_candidates,
    }
    content = chat_with_opus(
        hackclub_api_key,
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(payload, indent=2)},
        ],
        max_tokens=max_tokens,
        temperature=0.2,
    )
    return parse_json_or_fallback(
        content,
        {
            "hypotheses": [
                {
                    "id": "H1",
                    "statement": content[:500],
                    "confidence": 0.0,
                    "supporting_evidence": [],
                    "contradictions": ["Could not parse structured hypotheses."],
                }
            ],
            "questions": [],
            "suggested_follow_up_query": tavily_query,
            "pdf_query": f"{tavily_query} filetype:pdf",
        },
    )


def ask_user_questions(questions):
    if not questions:
        return []

    print("\nClarifying questions")
    print("Answer yes, no, idk, or anything useful.\n")

    answers = []
    for index, question in enumerate(questions, start=1):
        text = question.get("question", "")
        why = question.get("why", "")
        print(f"{index}. {text}")
        if why:
            print(f"   Why: {why}")

        if sys.stdin.isatty():
            answer = input("   Answer: ").strip() or "idk"
        else:
            answer = "idk"
            print("   Answer: idk")

        answers.append({"question": text, "answer": answer})

    return answers
def refine_query(user_clues, hypotheses, answers, hackclub_api_key, max_tokens):
    system_prompt = """
You are AISINT's Search Planner.

Use the original clues, current hypotheses, and user answers to create one better
Tavily query for the next search.

Output only the query text. Keep it under 180 characters. Do not invent facts.
""".strip()
    payload = {
        "user_clues": user_clues,
        "hypotheses": hypotheses,
        "user_answers": answers,
    }
    query = chat_with_opus(
        hackclub_api_key,
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(payload, indent=2)},
        ],
        max_tokens=max_tokens,
        temperature=0.2,
    )
    return " ".join(query.split())


def is_pdf_result(result):
    url = result.get("url", "").lower()
    title = result.get("title", "").lower()
    content = result.get("content", "").lower()
    return ".pdf" in url or "pdf" in title or "filetype:pdf" in content


def download_and_extract_pdf(url):
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    reader = PdfReader(BytesIO(response.content))
    pages = []
    for page in reader.pages[:8]:
        text = page.extract_text() or ""
        if text.strip():
            pages.append(text.strip())

    return "\n\n".join(pages)[:6000]


def collect_pdf_texts(pdf_results, max_downloads):
    extracted = []
    candidates = [result for result in pdf_results if is_pdf_result(result)]

    for result in candidates[:max_downloads]:
        url = result.get("url", "")
        try:
            text = download_and_extract_pdf(url)
        except (requests.RequestException, Exception) as error:
            extracted.append(
                {
                    "title": result.get("title", ""),
                    "url": url,
                    "error": str(error),
                    "text": "",
                }
            )
            continue

        extracted.append(
            {
                "title": result.get("title", ""),
                "url": url,
                "text": text,
            }
        )

    return extracted


def extract_pdf_facts(user_clues, pdf_texts, hackclub_api_key, max_tokens):
    if not pdf_texts:
        return {"facts": [], "notes": ["No PDF text extracted."]}

    system_prompt = """
You are AISINT's PDF Evidence Extractor.

Extract identity-relevant facts from public PDF text. Return only JSON:
{
  "facts": [
    {
      "fact": "short factual claim",
      "source_url": "url",
      "relevance": "why it matters",
      "confidence": 0.0
    }
  ],
  "notes": ["limits, uncertainty, or extraction issues"]
}

Rules:
- Do not invent facts.
- If a PDF is unrelated, say so in notes.
- Confidence is between 0 and 1.
- Extract at most 5 facts.
- Keep every string concise.
""".strip()
    payload = {
        "user_clues": user_clues,
        "pdfs": [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "error": item.get("error", ""),
                "text": item.get("text", "")[:2500],
            }
            for item in pdf_texts
        ],
    }
    content = chat_with_opus(
        hackclub_api_key,
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(payload, indent=2)},
        ],
        max_tokens=max_tokens,
        temperature=0.2,
    )
    return parse_json_or_fallback(
        content,
        {
            "facts": [],
            "notes": [
                "Could not parse structured PDF facts.",
            ],
        },
    )


def load_runtime_config():
    load_dotenv(".env")
    return {
        "tavily_api_key": require_env("TAVILY_API_KEY"),
        "hackclub_api_key": require_env("HACKCLUB_API_KEY"),
        "opus_max_tokens": get_int_env("OPUS_MAX_TOKENS", 3000),
        "tavily_max_results": get_int_env("TAVILY_MAX_RESULTS", 5),
        "pdf_max_downloads": get_int_env("PDF_MAX_DOWNLOADS", 3),
    }


def run_initial_investigation(user_clues, config=None, status_callback=None):
    config = config or load_runtime_config()

    def status(message):
        if status_callback:
            status_callback(message)

    status("Planning search query with Opus...")
    tavily_query = rephrase_for_tavily(
        user_clues,
        config["hackclub_api_key"],
        config["opus_max_tokens"],
    )

    status("Searching Tavily...")
    initial_data = search_tavily(
        tavily_query,
        config["tavily_api_key"],
        config["tavily_max_results"],
    )
    initial_results = initial_data.get("results", [])

    status("Merging duplicate-looking results...")
    initial_merged_candidates = merge_similar_results(
        user_clues,
        tavily_query,
        initial_results,
        config["hackclub_api_key"],
        config["opus_max_tokens"],
    )

    status("Creating hypotheses and questions...")
    analysis = create_hypotheses(
        user_clues,
        tavily_query,
        initial_results,
        initial_merged_candidates,
        config["hackclub_api_key"],
        config["opus_max_tokens"],
    )

    return {
        "user_clues": user_clues,
        "tavily_query": tavily_query,
        "initial_data": initial_data,
        "initial_results": initial_results,
        "initial_merged_candidates": initial_merged_candidates,
        "analysis": analysis,
    }


def choose_final_person(context, config, rejected_profile=None, status_callback=None):
    def status(message):
        if status_callback:
            status_callback(message)

    status("Choosing the most likely person...")
    system_prompt = """
You are AISINT's Senior Investigator.

Read all search results, merged candidate clusters, user answers, and PDF evidence.
Choose exactly one most likely real-world person. Merge profiles only when names,
achievements, locations, organizations, skills, or timelines are similar and not
contradictory.

Return only JSON:
{
  "selected_person": {
    "name": "best known name",
    "headline": "short identity headline",
    "confidence": 0.0,
    "why_this_person": ["reason"],
    "merged_sources": [{"title": "title", "url": "url", "why_included": "reason"}],
    "profile": {
      "overview": "human-readable paragraph",
      "location": "known or unknown",
      "education": ["item"],
      "work": ["item"],
      "skills": ["item"],
      "projects_or_achievements": ["item"],
      "online_profiles": ["item"],
      "pdf_evidence": ["item"],
      "uncertainties": ["item"]
    },
    "next_questions": ["useful follow-up question"]
  },
  "other_candidates": [
    {
      "label": "candidate label",
      "why_not_selected": "short reason"
    }
  ],
  "report_markdown": "detailed human-readable report about selected_person only"
}

Rules:
- Do not invent facts.
- Initially select only one person.
- Do not show a ranked list in report_markdown.
- If rejected_profile is provided, avoid choosing that person unless all evidence points back to them.
- Use clear prose, not raw JSON style, in report_markdown.
- Include source URLs inside report_markdown.
- If evidence is weak, say that plainly.
""".strip()
    payload = {
        "user_clues": context.get("user_clues", ""),
        "initial_query": context.get("tavily_query", ""),
        "initial_results": summarize_results_for_opus(context.get("initial_results", [])),
        "initial_merged_candidates": context.get("initial_merged_candidates", {}),
        "hypotheses": context.get("analysis", {}).get("hypotheses", []),
        "user_answers": context.get("answers", []),
        "refined_query": context.get("refined_query", ""),
        "refined_results": summarize_results_for_opus(
            context.get("refined_data", {}).get("results", [])
        ),
        "refined_merged_candidates": context.get("refined_merged_candidates", {}),
        "pdf_query": context.get("pdf_query", ""),
        "pdf_results": summarize_results_for_opus(
            context.get("pdf_data", {}).get("results", [])
        ),
        "pdf_facts": context.get("pdf_facts", {}),
        "alternative_searches": context.get("alternative_searches", []),
        "rejected_profile": rejected_profile,
    }
    content = chat_with_opus(
        config["hackclub_api_key"],
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(payload, indent=2)},
        ],
        max_tokens=config["opus_max_tokens"],
        temperature=0.2,
    )
    return parse_json_or_fallback(
        content,
        {
            "selected_person": {
                "name": "Unknown",
                "headline": "Could not parse selected profile",
                "confidence": 0.0,
                "why_this_person": [],
                "merged_sources": [],
                "profile": {
                    "overview": content[:1000],
                    "location": "unknown",
                    "education": [],
                    "work": [],
                    "skills": [],
                    "projects_or_achievements": [],
                    "online_profiles": [],
                    "pdf_evidence": [],
                    "uncertainties": ["Model returned malformed JSON."],
                },
                "next_questions": [],
            },
            "other_candidates": [],
            "report_markdown": content,
        },
    )


def complete_investigation(context, answers, config=None, status_callback=None):
    config = config or load_runtime_config()

    def status(message):
        if status_callback:
            status_callback(message)

    context["answers"] = answers

    status("Planning refined search from your answers...")
    refined_query = refine_query(
        context["user_clues"],
        context["analysis"].get("hypotheses", []),
        answers,
        config["hackclub_api_key"],
        config["opus_max_tokens"],
    )
    context["refined_query"] = refined_query

    status("Running refined Tavily search...")
    refined_data = search_tavily(
        refined_query,
        config["tavily_api_key"],
        config["tavily_max_results"],
    )
    context["refined_data"] = refined_data

    status("Merging refined candidates...")
    refined_merged_candidates = merge_similar_results(
        context["user_clues"],
        refined_query,
        refined_data.get("results", []),
        config["hackclub_api_key"],
        config["opus_max_tokens"],
    )
    context["refined_merged_candidates"] = refined_merged_candidates

    status("Searching public PDFs...")
    pdf_query = context["analysis"].get("pdf_query") or f"{refined_query} filetype:pdf"
    context["pdf_query"] = pdf_query
    pdf_data = search_tavily(
        pdf_query,
        config["tavily_api_key"],
        config["tavily_max_results"],
    )
    context["pdf_data"] = pdf_data

    status("Extracting PDF text...")
    pdf_texts = collect_pdf_texts(
        pdf_data.get("results", []),
        config["pdf_max_downloads"],
    )
    context["pdf_texts"] = pdf_texts

    status("Extracting PDF facts with Opus...")
    pdf_facts = extract_pdf_facts(
        context["user_clues"],
        pdf_texts,
        config["hackclub_api_key"],
        config["opus_max_tokens"],
    )
    context["pdf_facts"] = pdf_facts

    final_profile = choose_final_person(context, config, status_callback=status)
    context["final_profile"] = final_profile
    return context


def answer_profile_question(context, question, config=None):
    config = config or load_runtime_config()
    system_prompt = """
You answer follow-up questions about AISINT's selected person.
Use only the investigation context. If the context does not support an answer, say so.
Be concise, natural, and cite URLs when relevant.
""".strip()
    payload = {
        "question": question,
        "selected_profile": context.get("final_profile", {}),
        "pdf_facts": context.get("pdf_facts", {}),
        "initial_results": summarize_results_for_opus(context.get("initial_results", [])),
        "refined_results": summarize_results_for_opus(
            context.get("refined_data", {}).get("results", [])
        ),
    }
    return chat_with_opus(
        config["hackclub_api_key"],
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(payload, indent=2)},
        ],
        max_tokens=config["opus_max_tokens"],
        temperature=0.2,
    )


def plan_alternative_query(context, rejected_profile, config):
    system_prompt = """
You are AISINT's Search Planner.

The user said the selected person is not the target. Create one Tavily query that
looks for a different person matching the original clues while avoiding the rejected
profile's sources, organizations, domains, and distinctive facts.

Output only the query text. Keep it under 180 characters. Do not invent facts.
""".strip()
    payload = {
        "user_clues": context.get("user_clues", ""),
        "rejected_profile": rejected_profile,
        "previous_hypotheses": context.get("analysis", {}).get("hypotheses", []),
        "previous_answers": context.get("answers", []),
    }
    query = chat_with_opus(
        config["hackclub_api_key"],
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(payload, indent=2)},
        ],
        max_tokens=config["opus_max_tokens"],
        temperature=0.2,
    )
    return " ".join(query.split())


def choose_alternative_person(context, config=None, status_callback=None):
    config = config or load_runtime_config()
    rejected_profile = context.get("final_profile", {}).get("selected_person", {})
    if status_callback:
        status_callback("Planning an alternate search...")
    alternative_query = plan_alternative_query(context, rejected_profile, config)

    if status_callback:
        status_callback("Searching for another plausible person...")
    alternative_data = search_tavily(
        alternative_query,
        config["tavily_api_key"],
        config["tavily_max_results"],
    )
    alternative_merged_candidates = merge_similar_results(
        context.get("user_clues", ""),
        alternative_query,
        alternative_data.get("results", []),
        config["hackclub_api_key"],
        config["opus_max_tokens"],
    )
    context.setdefault("alternative_searches", []).append(
        {
            "query": alternative_query,
            "results": summarize_results_for_opus(alternative_data.get("results", [])),
            "merged_candidates": alternative_merged_candidates,
        }
    )

    alternative = choose_final_person(
        context,
        config,
        rejected_profile=rejected_profile,
        status_callback=status_callback,
    )
    context.setdefault("rejected_profiles", []).append(rejected_profile)
    context["final_profile"] = alternative
    return alternative


def print_results(title, query, data):
    results = data.get("results", [])

    print(f"\n{title}")
    print(f"Query: {query}")
    print(f"Found {len(results)} results:\n")

    for index, result in enumerate(results, start=1):
        print("=" * 60)
        print(f"RESULT #{index}")
        print(f"TITLE: {result.get('title', 'Untitled')}")
        print(f"URL: {result.get('url', 'No URL')}")
        print(f"SCORE: {result.get('score', 'N/A')}")
        print(f"CONTENT: {result.get('content', '')}")
        print()


def print_hypotheses(analysis):
    print("\nHypotheses")
    for hypothesis in analysis.get("hypotheses", []):
        confidence = hypothesis.get("confidence", "unknown")
        print(f"- {hypothesis.get('id', '?')}: {hypothesis.get('statement', '')}")
        print(f"  Confidence: {confidence}")
        for evidence in hypothesis.get("supporting_evidence", []):
            print(f"  Evidence: {evidence}")
        for contradiction in hypothesis.get("contradictions", []):
            print(f"  Contradiction/unknown: {contradiction}")


def print_merged_candidates(title, merged_candidates):
    print(f"\n{title}")
    for cluster in merged_candidates.get("clusters", []):
        indexes = ", ".join(str(index) for index in cluster.get("result_indexes", []))
        confidence = cluster.get("same_entity_confidence", "unknown")
        print(f"- {cluster.get('id', '?')}: {cluster.get('merged_label', '')}")
        print(f"  Results: {indexes}")
        print(f"  Same-entity confidence: {confidence}")
        for fact in cluster.get("merged_facts", []):
            print(f"  Fact: {fact}")
        for reason in cluster.get("why_same", []):
            print(f"  Merge reason: {reason}")
        for uncertainty in cluster.get("why_not_same", []):
            print(f"  Uncertainty: {uncertainty}")


# PDF facts are often lower confidence but can be high relevance, so we show them
# separately with their own relevance and confidence notes.

def print_pdf_facts(pdf_facts):
    print("\nPDF Facts")
    for fact in pdf_facts.get("facts", []):
        print(f"- {fact.get('fact', '')}")
        print(f"  Source: {fact.get('source_url', '')}")
        print(f"  Relevance: {fact.get('relevance', '')}")
        print(f"  Confidence: {fact.get('confidence', '')}")

    for note in pdf_facts.get("notes", []):
        print(f"- Note: {note}")


def main():
    config = load_runtime_config()
    user_clues = read_user_clues()

    try:
        context = run_initial_investigation(user_clues, config=config)
        answers = ask_user_questions(context.get("analysis", {}).get("questions", []))
        context = complete_investigation(context, answers, config=config)
    except requests.HTTPError as error:
        print(f"Request failed: {error}", file=sys.stderr)
        print(error.response.text, file=sys.stderr)
        sys.exit(1)
    except requests.RequestException as error:
        print(f"Network error: {error}", file=sys.stderr)
        sys.exit(1)
    except KeyError as error:
        print(f"Could not parse model response: {error}", file=sys.stderr)
        sys.exit(1)

    final_profile = context.get("final_profile", {})
    selected = final_profile.get("selected_person", {})
    report = final_profile.get("report_markdown", "")

    print("\nSelected Person")
    print("=" * 60)
    print(f"Name: {selected.get('name', 'Unknown')}")
    print(f"Headline: {selected.get('headline', '')}")
    print(f"Confidence: {selected.get('confidence', 'unknown')}")
    print("\nDetailed Report")
    print("=" * 60)
    print(report)

    while sys.stdin.isatty():
        question = input("\nAsk more, type 'not the one', or press Enter to quit: ").strip()
        if not question:
            break
        try:
            if "not the one" in question.lower() or "wrong person" in question.lower():
                alternative = choose_alternative_person(context, config=config)
                context["final_profile"] = alternative
                selected = alternative.get("selected_person", {})
                print("\nAlternative Selected Person")
                print("=" * 60)
                print(f"Name: {selected.get('name', 'Unknown')}")
                print(f"Headline: {selected.get('headline', '')}")
                print(f"Confidence: {selected.get('confidence', 'unknown')}")
                print(alternative.get("report_markdown", ""))
            else:
                print(answer_profile_question(context, question, config=config))
        except requests.HTTPError as error:
            print(f"Request failed: {error}", file=sys.stderr)
            print(error.response.text, file=sys.stderr)
        except requests.RequestException as error:
            print(f"Network error: {error}", file=sys.stderr)


if __name__ == "__main__":
    main()
