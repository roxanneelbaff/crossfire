# CROSSFIRE — Argument Quality Auditor

> **Audience-Aware Computational Argumentation · El Baff, Bauhaus-Universität Weimar, 2026**

CROSSFIRE operationalises the argument quality auditing pipeline from the dissertation *"Audience-Aware Computational Argumentation"*. It simulates how members of different political audience groups would react to an argumentative text, then derives a principled quality label from those reactions.

---

## What It Does

1. **Load an article** — fetch directly from Al Jazeera Opinion or Zeteo, or paste any text.
2. **Select audience groups** — choose 2–7 groups from the PEW 2021 Political Typology.
3. **Run the audit** — each selected LLM impersonates each group and predicts the article's effect (3 independent runs per model × group pair, executed in parallel).
4. **Read the results** — a grid shows per-cell effectiveness labels and an overall argument quality score derived from pairwise comparisons across groups.

---

## Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python · Flask 3 |
| LLM orchestration | LangChain (`init_chat_model`, `.with_structured_output()`) |
| LLM APIs | OpenAI (`gpt-4o`) · Mistral (`mistral-large-latest`) · Together AI (`Qwen/Qwen2.5-72B`) |
| Schemas | Pydantic v2 (`data_schema.py`) |
| Frontend | Bootstrap 5 · vanilla JS · Playfair Display / Inter fonts |
| Scraping | `requests` + `BeautifulSoup` |

---

## Setup

```bash
git clone <repo>
cd crossfire

# Install the package (editable mode) and all dependencies
pip install -e .

cp .env.example .env   # add your API keys
```

**`.env` keys** (any subset works — unconfigured models are greyed out):

```
OPENAI_API_KEY=...
TOGETHER_API_KEY=...
MISTRAL_API_KEY=...
```

---

## How to Run the App

Any of the following start the Flask dev server at **http://127.0.0.1:5000**:

```bash
# Option 1 — console script (installed via pyproject.toml)
crossfire

# Option 2 — module entrypoint
python -m crossfire

# Option 3 — direct Flask app object
python -c "from crossfire.app import app; app.run(debug=True, port=5000)"
```

Open the URL in your browser, load or paste an article, select ≥2 audience groups, and click **Run Quality Audit**.

---

## How Effectiveness Is Calculated

### Step 1 — Three Independent Runs (temperature = 0.7)

For every *(model, audience group)* pair the LLM is called **three times**. Each run uses a system prompt that role-plays the group's political identity (drawn from PEW 2021 descriptions) and a task prompt asking the model to classify the article's effect as one of:

| Label | Meaning |
|-------|---------|
| `CHALLENGING` | The article conflicts with the group's beliefs and may prompt reconsideration |
| `REINFORCING` | The article confirms existing beliefs and strengthens the group's stance |
| `INEFFECTIVE` | The article feels irrelevant or unconvincing to the group |

Each run also returns a `confidence` (high / medium / low) and a `rationale` (2–4 sentences).

### Step 2 — k=1 Majority Aggregation

The three raw labels are collapsed into a single **group effect** using a priority rule:

```
if any run == CHALLENGING  →  group effect = CHALLENGING
else if any run == REINFORCING  →  group effect = REINFORCING
else  →  group effect = INEFFECTIVE
```

The logic is intentionally conservative: a single `CHALLENGING` signal is enough to flag the article as potentially debate-provoking for that group. This mirrors the dissertation's finding that even minority dissent within simulated runs is substantively meaningful.

---

## How Argument Quality Is Calculated

### Step 3 — Pairwise Quality

For every **pair of selected groups** *(gᵢ, gⱼ)* the two group effects are looked up in the dissertation's quality matrix (Chapter 3):

| Effect for gᵢ | Effect for gⱼ | Pairwise Quality |
|--------------|--------------|-----------------|
| CHALLENGING | CHALLENGING | **High** |
| CHALLENGING | REINFORCING | **High** |
| REINFORCING | CHALLENGING | **High** |
| REINFORCING | REINFORCING | **Medium** |
| CHALLENGING | INEFFECTIVE | **Medium** |
| INEFFECTIVE | CHALLENGING | **Medium** |
| REINFORCING | INEFFECTIVE | **Low** |
| INEFFECTIVE | REINFORCING | **Low** |
| INEFFECTIVE | INEFFECTIVE | **Lowest** |

**Intuition:** an argument that challenges one group while reinforcing another is maximally effective — it is doing real argumentative work across the ideological divide. An argument that is ineffective for everyone has the lowest quality.

### Step 4 — Overall Quality Label

All C(N, 2) pairwise labels are computed and the **worst** label determines the overall quality:

```
overall = max(pairwise_labels, key=QUALITY_ORDER.index)
# where QUALITY_ORDER = ["High", "Medium", "Low", "Lowest"]
```

The overall label is therefore the most conservative estimate: even one very weak pairwise relationship pulls the whole score down.

---

## Output

| Component | Description |
|-----------|-------------|
| **Results grid** | Rows = models, Columns = groups. Each cell shows the aggregated label + expandable 3-run detail |
| **Overall Quality badge** | Per-model quality label (High / Medium / Low / Lowest) |
| **Pairwise panel** | Collapsible table of all group pairs with the worst pair highlighted |
| **CSV export** | Full matrix including all run labels, rationales, pairwise pairs, and overall quality |
| **Run logs** | Every LLM call saved to `logs/` as JSON (prompt, raw response, parsed result) |

---

## Project Structure

```
crossfire/
├── pyproject.toml           # Package definition (pip install -e .)
├── requirements.txt         # -> -e .
├── .env.example
├── prompts/                  # Prompt templates (*.md, project-level)
│   ├── system_role_play.md
│   ├── task_assess_effect.md
│   └── json_retry_reminder.md
├── profiles/                 # Audience profile sets (*.json, project-level)
│   └── american_political_ideology/
│       ├── faith_and_flag_conservatives.json
│       ├── committed_conservatives.json
│       ├── populist_right.json
│       ├── stressed_sideliners.json
│       ├── outside_left.json
│       ├── democratic_mainstays.json
│       └── progressive_left.json
├── logs/                     # Per-call JSON logs (auto-created)
└── src/crossfire/
    ├── __init__.py
    ├── __main__.py           # `python -m crossfire` / `crossfire` entrypoint
    ├── app.py                # Flask routes, parallel LLM execution
    ├── paths.py              # PROJECT_ROOT, PROMPTS_DIR, PROFILES_DIR, LOGS_DIR
    ├── model_registry.py     # ModelConfig dataclass + MODELS registry
    ├── data_schema.py         # All Pydantic models (incl. AudienceEffectResponse)
    ├── parsers.py            # Structured-JSON parsing for non-tool-calling models
    ├── utils.py              # get_model, _read_prompt, _invoke_with_retry
    ├── prompts.py            # Renders prompt templates from prompts/
    ├── quality_rules.py      # Chapter 3 matrix, pairwise, aggregation
    ├── audience_profiles.py  # Loads profile sets from profiles/
    ├── article_fetcher.py    # Al Jazeera + Zeteo scrapers
    ├── templates/
    │   ├── base.html
    │   ├── index.html        # Article loader, group selector, run button
    │   └── result.html       # Results grid + pairwise panels
    └── static/style.css      # Navy / crimson / teal design system
```

---

## Audience Groups (PEW 2021 Typology)

| Group | Ideology |
|-------|---------|
| Faith & Flag Conservatives | Conservative |
| Committed Conservatives | Conservative |
| Populist Right | Conservative |
| Stressed Sideliners | Moderate |
| Outside Left | Liberal |
| Democratic Mainstays | Liberal |
| Progressive Left | Liberal |

---

*Based on: Roxanne El Baff, "Audience-Aware Computational Argumentation", Bauhaus-Universität Weimar, 2026.*
