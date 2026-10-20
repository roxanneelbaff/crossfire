"""
Argument Quality Auditor — Flask application
Audience-Aware Computational Argumentation · El Baff, 2026
"""

import csv
import io
import json
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, Response, send_file

from .audience_profiles import AUDIENCE_GROUPS, GROUPS_BY_ID
from .article_fetcher import (
    fetch_aljazeera_list, fetch_aljazeera_article,
    fetch_zeteo_list, fetch_zeteo_article,
)
from .data_schema import AudienceEffectResponse, EffectLabel, GroupEffect, ModelResult, RunResult
from .model_registry import MODELS
from .paths import LOGS_DIR
from .prompts import system_prompt, task_prompt
from .quality_rules import apply_level1_majority, compute_pairwise_and_overall
from .utils import get_model, _invoke_with_retry

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "crossfire-dev-secret")

LOGS_DIR.mkdir(exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TEMPERATURE = 0.7

# ─── LLM instances ───────────────────────────────────────────────────────────

_LLM_CACHE: dict = {}


def _get_llm(model_key: str):
    """Lazily build (and cache) the chat model + structured-output wrapper."""
    if model_key not in _LLM_CACHE:
        cfg = MODELS[model_key]
        llm = get_model(cfg.model, cfg.model_provider, temperature=TEMPERATURE)
        structured = llm.with_structured_output(AudienceEffectResponse) if cfg.with_structure else None
        _LLM_CACHE[model_key] = (llm, structured)
    return _LLM_CACHE[model_key]


def _configured_models() -> dict:
    """Return model registry annotated with whether their API key is present."""
    out = {}
    for key, cfg in MODELS.items():
        out[key] = {
            "label": cfg.label,
            "configured": bool(os.environ.get(cfg.env_key)),
        }
    return out


# ─── Logging ─────────────────────────────────────────────────────────────────

_LOG_LOCK = threading.Lock()
CALLS_LOG_FILE = LOGS_DIR / "calls.jsonl"
LOG_WEBHOOK_URL = os.environ.get("LOG_WEBHOOK_URL", "")


def _append_log(log_entry: dict) -> None:
    """
    Append one LLM-call record to logs/calls.jsonl (newline-delimited JSON),
    and optionally forward it to an external webhook (LOG_WEBHOOK_URL) for
    off-disk persistence on platforms with ephemeral filesystems (e.g. Render
    free tier, where local logs/ is wiped on every redeploy/restart).
    """
    line = json.dumps(log_entry, ensure_ascii=False)
    try:
        with _LOG_LOCK:
            with open(CALLS_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception:
        logger.exception("Failed to write call log to %s", CALLS_LOG_FILE)

    if LOG_WEBHOOK_URL:
        try:
            requests.post(LOG_WEBHOOK_URL, json=log_entry, timeout=5)
        except Exception:
            logger.warning("Failed to forward log entry to LOG_WEBHOOK_URL", exc_info=True)


# ─── LLM call ────────────────────────────────────────────────────────────────

def _single_run(model_key: str, group: dict, article: dict, run_idx: int) -> RunResult:
    """Execute one structured-output LLM run for a (model, group) pair."""
    sys_p = system_prompt(group["label"], group["description"])
    usr_p = task_prompt(
        article.get("title", ""),
        article.get("author", ""),
        article.get("body", ""),
        group["label"],
    )

    llm, structured = _get_llm(model_key)

    try:
        if structured is not None:
            response: AudienceEffectResponse = _invoke_with_retry(
                llm, usr_p, sys_p, structured_model=structured
            )
        else:
            response: AudienceEffectResponse = _invoke_with_retry(
                llm, usr_p, sys_p, cls_parser=AudienceEffectResponse
            )
        result = RunResult(
            label=response.label,
            confidence=response.confidence,
            rationale=response.rationale,
        )
    except Exception as exc:
        logger.error("LLM call failed [%s/%s/run%d]: %s", model_key, group["id"], run_idx, exc)
        result = RunResult(label=EffectLabel.ERROR, confidence=None, rationale=str(exc))

    # Log to file
    cfg = MODELS.get(model_key)
    log_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "model_key": model_key,
        "model_name": cfg.model if cfg else model_key,
        "model_provider": cfg.model_provider if cfg else None,
        "temperature": TEMPERATURE,
        "audience_group": group["id"],
        "audience_group_label": group.get("label"),
        "run": run_idx,
        "label": result.label.value if result.label is not None else None,
        "confidence": result.confidence.value if result.confidence else None,
        "rationale": result.rationale,
        "article": {
            "title": article.get("title", ""),
            "url": article.get("url", ""),
            "source": article.get("source", ""),
            "domain": article.get("domain", ""),
            "author": article.get("author", ""),
            "date": article.get("date", ""),
        },
        "text_analyzed": article.get("body", ""),
        "system_prompt": sys_p,
        "user_prompt": usr_p,
    }
    _append_log(log_entry)

    return result


# ─── Analysis pipeline ────────────────────────────────────────────────────────

def run_analysis(article: dict, group_ids: list, model_keys: list) -> list:
    """
    Run the full 3-level pipeline for selected groups and models.
    Returns a list of ModelResult dicts (JSON-serialisable).
    """
    groups = [GROUPS_BY_ID[gid] for gid in group_ids if gid in GROUPS_BY_ID]
    results = []

    for model_key in model_keys:
        cfg = MODELS.get(model_key)
        if not cfg or not os.environ.get(cfg.env_key):
            results.append(ModelResult(
                model=model_key,
                model_label=cfg.label if cfg else model_key,
                configured=False,
                group_effects={},
                pairwise_quality=[],
                overall_quality=None,
            ).model_dump(mode="json"))
            continue

        # Run all (group × 3 runs) in parallel
        futures_map = {}
        with ThreadPoolExecutor(max_workers=12) as executor:
            for group in groups:
                for run_idx in range(1, 4):
                    future = executor.submit(_single_run, model_key, group, article, run_idx)
                    futures_map[future] = (group["id"], run_idx)

            raw_results: dict = {}
            for future in as_completed(futures_map):
                gid, run_idx = futures_map[future]
                raw_results.setdefault(gid, {})[run_idx] = future.result()

        # Level 1 → Level 2: aggregate per group
        group_effects = {}
        for group in groups:
            gid = group["id"]
            runs_dict = raw_results.get(gid, {})
            runs_list = [
                runs_dict.get(i, RunResult(label=EffectLabel.ERROR, confidence=None, rationale=""))
                for i in range(1, 4)
            ]
            final_label = apply_level1_majority([r.model_dump(mode="json") for r in runs_list])
            group_effects[gid] = GroupEffect(final_label=final_label, runs=runs_list)

        # Level 3: pairwise + overall quality
        flat_effects = {gid: ge.final_label.value for gid, ge in group_effects.items()}
        pairwise, overall = compute_pairwise_and_overall(flat_effects)

        results.append(ModelResult(
            model=model_key,
            model_label=cfg.label,
            configured=True,
            group_effects=group_effects,
            pairwise_quality=pairwise,
            overall_quality=overall,
        ).model_dump(mode="json"))

    return results


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    models = _configured_models()
    return render_template("index.html", groups=AUDIENCE_GROUPS, models=models)


@app.route("/fetch-article")
def fetch_article_route():
    source = request.args.get("source", "")
    url = request.args.get("url", "")

    try:
        if source == "aljazeera":
            data = fetch_aljazeera_article(url) if url else fetch_aljazeera_list()
        elif source == "zeteo":
            data = fetch_zeteo_article(url) if url else fetch_zeteo_list()
        else:
            return jsonify({"error": "Unknown source"}), 400
        return jsonify(data)
    except Exception as exc:
        logger.exception("fetch-article failed")
        return jsonify({"error": str(exc)}), 500


@app.route("/analyze", methods=["POST"])
def analyze():
    payload = request.get_json(force=True)
    article = payload.get("article", {})
    group_ids = payload.get("group_ids", [])
    model_keys = payload.get("models", list(MODELS.keys()))

    if not article.get("body"):
        return jsonify({"error": "No article body provided"}), 400
    if len(group_ids) < 2:
        return jsonify({"error": "Select at least 2 audience groups"}), 400

    # Always ensure title/source/domain are populated for the results header.
    if not article.get("domain") and article.get("url"):
        article["domain"] = urlparse(article["url"]).netloc.removeprefix("www.")
    if not article.get("source"):
        domain = article.get("domain", "")
        if "aljazeera" in domain:
            article["source"] = "Al Jazeera"
        elif "zeteo" in domain:
            article["source"] = "Zeteo"
        else:
            article["source"] = "Pasted text"
    if not article.get("title"):
        article["title"] = f"Untitled Article — {article['source']}"

    results = run_analysis(article, group_ids, model_keys)

    selected_groups = [GROUPS_BY_ID[gid] for gid in group_ids if gid in GROUPS_BY_ID]

    if request.headers.get("Accept") == "application/json":
        return jsonify({"results": results})

    return render_template(
        "result.html",
        article=article,
        selected_groups=selected_groups,
        results=results,
        models=_configured_models(),
        group_ids=group_ids,
    )


@app.route("/export-csv", methods=["POST"])
def export_csv():
    payload = request.get_json(force=True)
    results = payload.get("results", [])

    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    base_cols = ["model", "group", "final_label"]
    run_cols = []
    for i in range(1, 4):
        run_cols += [f"run{i}_label", f"run{i}_confidence", f"run{i}_rationale"]
    pair_cols = ["pairwise_g1", "pairwise_g2", "pairwise_quality"]
    writer.writerow(base_cols + run_cols + ["overall_quality"] + pair_cols)

    for model_result in results:
        model_label = model_result.get("model_label", model_result.get("model"))
        group_effects = model_result.get("group_effects", {})
        overall = model_result.get("overall_quality", "")
        pairwise = model_result.get("pairwise_quality", [])

        for gid, gdata in group_effects.items():
            runs = gdata.get("runs", [{}, {}, {}])
            run_vals = []
            for run in runs:
                run_vals += [run.get("label", ""), run.get("confidence", ""), run.get("rationale", "")]
            # Attach pairwise rows to first group only
            if pairwise and gid == list(group_effects.keys())[0]:
                for pair in pairwise:
                    writer.writerow(
                        [model_label, gid, gdata.get("final_label", "")]
                        + run_vals
                        + [overall, pair["g1"], pair["g2"], pair["quality"]]
                    )
            else:
                writer.writerow(
                    [model_label, gid, gdata.get("final_label", "")]
                    + run_vals
                    + [overall, "", "", ""]
                )

    csv_data = output.getvalue()
    filename = f"crossfire_results_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.route("/export-logs")
def export_logs():
    """
    Download the cumulative per-call LLM log (JSON Lines).

    Protected by a `key` query param matching SECRET_KEY, since logs may
    contain full article text and rationales. Useful for pulling logs off
    of ephemeral hosting (e.g. Render free tier) before a redeploy.
    """
    if request.args.get("key") != app.secret_key:
        return jsonify({"error": "unauthorized"}), 401
    if not CALLS_LOG_FILE.exists():
        return jsonify({"error": "no logs yet"}), 404
    return send_file(
        CALLS_LOG_FILE,
        mimetype="application/x-ndjson",
        as_attachment=True,
        download_name=f"crossfire_calls_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.jsonl",
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
