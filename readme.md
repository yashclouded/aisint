# AISINT

**AI-Powered Open Source Intelligence Investigator**

Describe a person, username, company, domain, or digital footprint in plain English.

AISINT autonomously plans investigations, gathers evidence across multiple sources, builds an identity graph, identifies contradictions, performs iterative research, and generates confidence-scored intelligence reports.

Unlike traditional OSINT tools that dump links, AISINT attempts to answer:

> Who is this?
>
> How confident are we?
>
> What evidence supports this conclusion?
>
> What evidence contradicts it?

---

## Example

Input:

```text
Yash Singh

High school student
Interested in programming
Lives in India
Works on startup projects
```

AISINT:

1. Generates investigation hypotheses.
2. Creates search plans.
3. Searches the web.
4. Searches GitHub.
5. Searches PDFs.
6. Extracts entities.
7. Builds an evidence graph.
8. Detects contradictions.
9. Performs follow-up searches.
10. Produces confidence-scored findings.

Output:

```text
Candidate Profile #1
Confidence: 87%

Supporting Evidence:
✓ Personal website
✓ GitHub repositories
✓ Programming-related activity
✓ Matching location

Contradictory Evidence:
⚠ No school information found

Suggested Next Searches:
- Hackathon participation
- Competition records
```

---

# Core Architecture

```text
User Clues
      │
      ▼
Investigation Planner
      │
      ▼
Hypothesis Generator
      │
      ▼
Search Planner
      │
      ▼
Multi-Source Collection
      │
      ▼
Entity Extraction
      │
      ▼
Knowledge Graph
      │
      ▼
Contradiction Engine
      │
      ▼
Investigation Agent
      │
      ▼
Confidence Model
      │
      ▼
Final Intelligence Report
```

---

# Modules

## 1. Investigation Planner

Model:

* Claude Opus

Responsibilities:

* Understand user intent
* Generate investigation hypotheses
* Prioritize evidence requirements
* Create investigation strategy

Example:

Input:

```text
Yash Singh
Programming
India
```

Generated Hypotheses:

```text
H1: Has GitHub profile
H2: Has personal website
H3: Participates in hackathons
H4: Appears on public PDFs
H5: Uses same username elsewhere
```

---

## 2. Search Planner

Model:

* Claude Opus

Converts hypotheses into search operations.

Example:

```text
site:github.com "Yash Singh"

site:devpost.com "Yash Singh"

site:linkedin.com "Yash Singh"

filetype:pdf "Yash Singh"

"Yash Singh" programming
```

---

## 3. Multi-Source Collection Layer

### Tavily

Purpose:

* General web search
* Discovery
* Mentions
* News
* Profiles

---

### GitHub API

Purpose:

* Repositories
* Organizations
* Followers
* Contribution patterns
* Programming languages

---

### PDF Collector

Purpose:

* Resumes
* Conference papers
* Competition records
* Public documents

Libraries:

* pypdf
* pymupdf

---

### Domain Intelligence

Purpose:

* DNS
* SSL
* Technologies
* Infrastructure

Libraries:

* python-whois
* dnspython

---

### Archive Collector

Purpose:

* Historical snapshots
* Deleted content
* Website evolution

Sources:

* Internet Archive

---

## 4. Entity Extraction Engine

Model:

* Claude Opus

Converts webpages into structured facts.

Example:

```json
{
  "name": "Yash Singh",
  "location": "Lucknow",
  "skills": [
    "Python",
    "AI"
  ],
  "organization": [
    "STEMist"
  ]
}
```

---

## 5. Knowledge Graph

Framework:

* NetworkX initially
* Neo4j later

Nodes:

```text
Person
Organization
Project
Website
Username
Email
School
Repository
```

Relationships:

```text
WORKS_ON
MEMBER_OF
OWNS
PARTICIPATED_IN
LIKELY_SAME_AS
```

---

## 6. Contradiction Engine

Detects conflicting evidence.

Example:

```text
Source A:
Location = Lucknow

Source B:
Location = Mumbai
```

Contradiction score increases.

Confidence decreases.

---

## 7. Active Investigation Agent

Model:

* Claude Opus

Responsibilities:

* Identify missing evidence
* Generate follow-up searches
* Continue investigation autonomously

Example:

```text
Confidence only 54%.

Need more evidence.

Search:
"Yash Singh STEMist"

Search:
"Yash Singh Hack Club"
```

---

## 8. Confidence Engine

Not AI-based.

Rule-based and probabilistic.

Evidence:

```text
Same username +30
Same location +25
Same organization +40

Contradiction -35
```

Produces:

```text
Confidence: 87%
```

---

## 9. Report Generator

Model:

* Claude Opus

Produces:

* Executive Summary
* Findings
* Supporting Evidence
* Contradictions
* Confidence Scores
* Recommended Follow-up Investigation

---

# Technology Stack

Backend

* Python
* FastAPI
* AsyncIO

AI

* Claude Opus

Search

* Tavily

Data

* SQLite (MVP)
* PostgreSQL (Production)

Graph

* NetworkX
* Neo4j

Extraction

* BeautifulSoup
* PyPDF
* PyMuPDF

Domain Intelligence

* python-whois
* dnspython

Deployment

* Docker
* Railway
* Fly.io

---

# Future Features

* Multi-agent investigations
* Live investigation dashboard
* Timeline reconstruction
* Relationship graph visualization
* Autonomous research loops
* Digital footprint scoring
* Threat intelligence mode
* Startup intelligence mode
* Researcher mode
* Journalist mode

---

# Goal

Build an AI investigator that behaves less like a chatbot and more like a junior analyst.

Not:

```text
Search
↓
Summarize
```

But:

```text
Hypothesize
↓
Investigate
↓
Verify
↓
Contradict
↓
Research Again
↓
Conclude
```
