"""AnalyticsAgentV3: minimal question-driven data preparation prototype.

Run: python controller.py
Requires: OPENAI_API_KEY in .env, Docker, and divvy-analytics:latest image.
Workflow: human input, dataset profiling, scope assessment and approval,
data preparation, frozen dataset, statistical analysis, optional charts,
interpretation and reporting, and optional follow-up questions.
"""
import csv
import json
import os
import subprocess
import shutil
import html
import re
import webbrowser
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
ROOT = Path(__file__).resolve().parent
RUNS = ROOT / "runs_v3"
MODEL = os.getenv("OPENAI_MODEL", "gpt-6")


def save(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def ask_openai(instructions, content):
    response = OpenAI().responses.create(
        model=MODEL, instructions=instructions, input=content
    )
    return response.output_text


def read_csv_profile(source):
    """Small factual profile; no extra model call."""
    import pandas as pd

    sample = pd.read_csv(source, nrows=1000)
    with source.open(newline="", encoding="utf-8-sig") as f:
        row_count = sum(1 for _ in csv.reader(f)) - 1
    return {
        "filename": source.name,
        "rows": row_count,
        "columns": list(sample.columns),
        "sample_missing_counts_first_1000_rows": sample.isna().sum().to_dict(),
        "sample_rows": sample.head(3).fillna("").astype(str).to_dict("records"),
    }


def verify_preparation(source, output_dir):
    """Three independent checks: counts, exclusions, and missing values."""
    import pandas as pd

    audit = json.loads((output_dir / "audit_summary.json").read_text(encoding="utf-8"))
    prepared = pd.read_csv(output_dir / "prepared.csv")
    with source.open(newline="", encoding="utf-8-sig") as f:
        input_rows = sum(1 for _ in csv.reader(f)) - 1

    assert audit["input_row_count"] == input_rows, "Input row count mismatch"
    assert audit["output_row_count"] == len(prepared), "Output row count mismatch"
    assert (
        input_rows - audit["unique_excluded_row_count"] == len(prepared)
    ), "Exclusion reconciliation failed"
    assert sum(item["count"] for item in audit["exclusion_reasons"]) == audit[
        "unique_excluded_row_count"
    ], "Exclusion reasons do not reconcile"

    actual_missing = prepared.isna().sum().to_dict()
    assert audit["remaining_missing_values"] == actual_missing, (
        "Missing-value counts mismatch"
    )
    print(f"Verified: {input_rows} input, {len(prepared)} prepared, "
          f"{audit['unique_excluded_row_count']} excluded")


def print_preparation_summary(audit):
    """Readable overview; the complete audit remains saved as JSON."""
    print("\nPREPARATION SUMMARY")
    print(f"  Input rows:       {audit['input_row_count']:,}")
    print(f"  Excluded rows:    {audit['unique_excluded_row_count']:,}")
    reasons = audit.get("exclusion_reasons", [])
    if reasons:
        print("  Reasons for exclusion:")
        for item in reasons:
            print(f"    {item['reason']}: {item['count']:,}")
    elif audit['unique_excluded_row_count']:
        print("  Exclusion reasons: see full audit")
    print(f"  Prepared rows:    {audit['output_row_count']:,}")
    missing = {k: v for k, v in audit['remaining_missing_values'].items() if v}
    if missing:
        print("  Columns still containing missing values:")
        for name, count in missing.items():
            print(f"    {name}: {count:,}")
    else:
        print("  Missing values in prepared data: none")
    print("  Verification: passed")
    print("  Full audit: output/audit_summary.json")


def execute_in_docker(source, code_path, output_dir, expected_output):
    """Run one approved stage; never reuse incomplete outputs."""
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / expected_output).unlink(missing_ok=True)
    command = [
        "docker", "run", "--rm", "--network", "none", "--read-only",
        "--tmpfs", "/tmp", "--env", "MPLCONFIGDIR=/tmp/matplotlib",
        "--memory", "2g", "--cpus", "1",
        "--mount", f"type=bind,source={source},target=/data/{source.name},readonly",
        "--mount", f"type=bind,source={code_path},target=/scripts/prepare.py,readonly",
        "--mount", f"type=bind,source={output_dir},target=/output",
        "divvy-analytics:latest", "timeout", "300", "python", "-B", "/scripts/prepare.py",
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=330)
        save(output_dir / "stdout.txt", result.stdout)
        save(output_dir / "stderr.txt", result.stderr)
        print("Docker exit code:", result.returncode)
        if result.returncode:
            raise RuntimeError(result.stderr or f"Docker exited {result.returncode}")
        if not (output_dir / expected_output).is_file():
            raise FileNotFoundError(f"Docker did not create {expected_output}")
    except (RuntimeError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        details = str(exc).strip().splitlines()
        print(f"\nExecution failed: {details[-1] if details else type(exc).__name__}")
        print(f"Full error details: {output_dir / 'stderr.txt'} (if Docker started)")
        print("To retry: run this controller again and answer 'y' to Resume most recent run.")
        (output_dir / expected_output).unlink(missing_ok=True)
        # Keep failed code for inspection, but regenerate it on the next attempt.
        shutil.copy2(code_path, code_path.with_suffix(".failed.py"))
        code_path.unlink(missing_ok=True)
        raise


def prepare_data(selected_run=None):
    RUNS.mkdir(exist_ok=True)
    existing = sorted(p for p in RUNS.iterdir() if (p / "context.json").exists())
    if selected_run is not None or (existing and input("Resume most recent run? (y/n): ").strip().lower() == "y"):
        run = selected_run if selected_run is not None else existing[-1]
        context = json.loads((run / "context.json").read_text(encoding="utf-8"))
        source = Path(context["source"])
        question = context["question"]
    else:
        source = Path(input("CSV file path: ").strip().strip('"')).expanduser().resolve()
        if not source.is_file() or source.suffix.lower() != ".csv":
            raise ValueError("Provide an existing CSV file")
        question = input("Research question: ").strip()
        if not question:
            raise ValueError("Research question is required")
        run = RUNS / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        run.mkdir()
        save(run / "context.json", json.dumps(
            {"source": str(source), "question": question}, indent=2))

    if not source.is_file():
        raise FileNotFoundError(source)
    if (run / "VERIFIED").exists():
        return run
    plan_path, approval_path = run / "preparation_plan.md", run / "PLAN_APPROVED"
    profile_path = run / "profile.json"
    if not profile_path.exists():
        save(profile_path, json.dumps(read_csv_profile(source), indent=2))
    profile = json.loads(profile_path.read_text(encoding="utf-8"))

    # Agree on the research question before generating a preparation plan.
    scope_path = run / "question_scope.md"
    scope_approval = run / "QUESTION_ACCEPTED"
    if not scope_approval.exists() and not approval_path.exists():
        while True:
            if not scope_path.exists():
                assessment = ask_openai(
                    "Assess ONLY whether the research question is appropriately scoped "
                    "for a focused, interpretable, computationally manageable first "
                    "analysis. Consider the dataset profile, 2 GB Docker memory, "
                    "one CPU, 300-second execution timeout, and no internet access. "
                    "Begin with exactly 'SCOPE: ACCEPTABLE' or 'SCOPE: TOO BROAD'. "
                    "If too broad, briefly explain why and suggest 2-3 narrower "
                    "research questions. Do not generate a preparation or statistical "
                    "plan, code, or results. Do not change the question yourself.",
                    f"QUESTION:\n{question}\nPROFILE:\n{json.dumps(profile)}",
                )
                save(scope_path, assessment)
            print("\nRESEARCH QUESTION SCOPE:\n", scope_path.read_text(encoding="utf-8"))
            choice = input("Accept question (a), revise question (r), or stop (s)? ").strip().lower()
            if choice == "s":
                return None
            if choice == "a":
                save(scope_approval, "Question accepted by human\n")
                break
            if choice == "r":
                revised_question = input("Revised research question: ").strip()
                if revised_question:
                    question = revised_question
                    context = json.loads((run / "context.json").read_text(encoding="utf-8"))
                    context["question"] = question
                    save(run / "context.json", json.dumps(context, indent=2))
                    scope_path.unlink(missing_ok=True)

    if not plan_path.exists():
        plan = ask_openai(
            "Propose a concise, question-driven integrated cleaning and wrangling "
            "plan. Use only the supplied dataset profile and accepted question. "
            "Specify required columns, transformations, missing/invalid data "
            "handling, exclusions and assumptions. Distinguish observed facts from "
            "proposed rules. Do not invent data-quality problems or exclude plausible "
            "outliers automatically. For an EXTEND follow-up, build only on existing "
            "accepted preparation; avoid redoing established work. Keep the plan "
            "focused on necessary changes. No statistical results or Python code.",
            f"QUESTION:\n{question}\nPROFILE:\n{json.dumps(profile)}\n"
            f"FOLLOW-UP CONTEXT:\n{json.dumps(context) if selected_run is not None else 'New research question'}",
        )
        save(plan_path, plan)

    if not approval_path.exists():
        while True:
            print("\nPROPOSED PREPARATION PLAN:\n", plan_path.read_text(encoding="utf-8"))
            choice = input("Approve (a), revise (r), or stop (s)? ").strip().lower()
            if choice == "s":
                return None
            if choice == "a":
                save(approval_path, "Approved by human\n")
                break
            if choice == "r":
                feedback = input("Revision request: ").strip()
                if feedback:
                    revised = ask_openai(
                        "Revise the question-driven data preparation plan according "
                        "to the human feedback. No code or statistical analysis.",
                        f"QUESTION:\n{question}\nCURRENT PLAN:\n"
                        f"{plan_path.read_text(encoding='utf-8')}\n"
                        f"FEEDBACK:\n{feedback}",
                    )
                    save(plan_path, revised)

    code_path = run / "prepare.py"
    verification_error_path = run / "verification_error.txt"
    if not code_path.exists():
        profile = (run / "profile.json").read_text(encoding="utf-8")
        previous_error = (verification_error_path.read_text(encoding="utf-8")
                          if verification_error_path.exists() else "None")
        generated = ask_openai(
            "Generate concise Python 3.12 pandas code implementing ONLY the "
            "approved integrated cleaning and wrangling plan. Read the named CSV "
            "from /data and write /output/prepared.csv and "
            "/output/audit_summary.json. Audit JSON must contain EXACTLY these "
            "required fields (additional fields optional): input_row_count, "
            "output_row_count, unique_excluded_row_count, "
            "remaining_missing_values (mapping EVERY output column to its "
            "missing count), and exclusion_reasons (list of objects with "
            "'reason' and 'count', using mutually exclusive categories whose "
            "counts sum to unique_excluded_row_count; empty list if none). "
            "Describe actual exclusions, not missing values in retained rows. "
            "Use pandas/NumPy methods on compatible types: .fillna() is a "
            "pandas Series/DataFrame method, not a NumPy ndarray method. "
            "Convert arrays to a Series if needed or handle missing values "
            "with NumPy functions. Preserve original data. Do not perform statistical "
            "analysis. Do not access network, subprocesses, or paths outside "
            "/data and /output. Return executable Python only, no fences.",
            f"QUESTION:\n{question}\nAPPROVED PLAN:\n"
            f"{plan_path.read_text(encoding='utf-8')}\nPROFILE:\n{profile}"
            f"\nPREVIOUS VERIFICATION FAILURE (fix if present):\n{previous_error}",
        )
        save(code_path, generated)

    output_dir = run / "output"
    if not (run / "VERIFIED").exists():
        # Never verify a fresh prepared.csv against an earlier attempt's audit.
        (output_dir / "audit_summary.json").unlink(missing_ok=True)
        try:
            execute_in_docker(source, code_path.resolve(), output_dir.resolve(), "prepared.csv")
            verify_preparation(source, output_dir)
        except Exception as exc:
            # Supply the actual Docker or verification error to the next attempt.
            save(verification_error_path, f"{type(exc).__name__}: {str(exc)[-2000:]}")
            # Docker failures already archive/remove code; handle verification failures too.
            if code_path.exists():
                shutil.copy2(code_path, code_path.with_suffix(".failed.py"))
                code_path.unlink(missing_ok=True)
            (output_dir / "prepared.csv").unlink(missing_ok=True)
            (output_dir / "audit_summary.json").unlink(missing_ok=True)
            raise
        verification_error_path.unlink(missing_ok=True)
        print_preparation_summary(json.loads(
            (output_dir / "audit_summary.json").read_text(encoding="utf-8")))
        if input("Accept prepared dataset for analysis? (y/n): ").lower() == "y":
            save(run / "VERIFIED", "Verified and accepted by human\n")
            print("Prepared dataset saved:", output_dir / "prepared.csv")
        else:
            approval_path.unlink(missing_ok=True)
            code_path.unlink(missing_ok=True)
            print("Not accepted. Resume this run to revise the preparation plan.")
            return None
    return run


def analyze_data(run):
    """Plan, approve, execute, and save descriptive statistical analysis."""
    if not (run / "VERIFIED").exists():
        raise RuntimeError("Prepared dataset has not been accepted.")
    context = json.loads((run / "context.json").read_text(encoding="utf-8"))
    question = context["question"]
    prepared = run / "output" / "prepared.csv"
    if not prepared.is_file():
        raise FileNotFoundError(prepared)

    plan_path = run / "stats_plan.md"
    approval_path = run / "STATS_PLAN_APPROVED"
    if not plan_path.exists():
        import pandas as pd
        sample = pd.read_csv(prepared, nrows=1000)
        profile = {
            "columns": list(sample.columns),
            "sample_rows": sample.head(3).fillna("").astype(str).to_dict("records"),
            "preparation_audit": json.loads(
                (run / "output" / "audit_summary.json").read_text(encoding="utf-8")
            ),
        }
        plan = ask_openai(
            "Propose a concise statistical analysis plan to answer the research "
            "question using the already-prepared dataset. Identify primary and "
            "secondary statistics, group comparisons, and limitations. Separate "
            "required from optional analyses. Do not repeat cleaning or wrangling. "
            "No charts or Python code.",
            f"QUESTION:\n{question}\nPREPARED DATA PROFILE:\n{json.dumps(profile)}",
        )
        save(plan_path, plan)

    if not approval_path.exists():
        while True:
            print("\nPROPOSED STATISTICAL PLAN:\n",
                  plan_path.read_text(encoding="utf-8"))
            choice = input("Approve (a), revise (r), or stop (s)? ").strip().lower()
            if choice == "s":
                return False
            if choice == "a":
                save(approval_path, "Approved by human\n")
                break
            if choice == "r":
                feedback = input("Revision request: ").strip()
                if feedback:
                    revised = ask_openai(
                        "Revise the statistical plan according to human feedback. "
                        "Do not repeat data preparation. No code or charts.",
                        f"QUESTION:\n{question}\nCURRENT PLAN:\n"
                        f"{plan_path.read_text(encoding='utf-8')}\nFEEDBACK:\n{feedback}",
                    )
                    save(plan_path, revised)

    code_path = run / "stats.py"
    if not code_path.exists():
        generated = ask_openai(
            "Write concise Python 3.12 pandas code implementing ONLY the approved "
            "statistical analysis plan. Read /data/prepared.csv. Write the "
            "statistical results to /output/stats_results.json as a JSON object "
            "containing numerical findings and counts, with no NaN or Infinity. "
            "Do not repeat cleaning or exclusions; derived analytical variables "
            "may be computed from existing prepared columns. Do not produce charts. "
            "Do not access network, subprocesses, or paths outside /data and /output. "
            "Return executable Python code only, without Markdown fences.",
            f"QUESTION:\n{question}\nAPPROVED STATISTICAL PLAN:\n"
            f"{plan_path.read_text(encoding='utf-8')}\n"
            f"PREPARED COLUMNS:\n{list(__import__('pandas').read_csv(prepared, nrows=0).columns)}",
        )
        save(code_path, generated)

    output_dir = run / "stats_output"
    results_path = output_dir / "stats_results.json"
    computed = not results_path.exists()
    if computed:
        execute_in_docker(prepared, code_path.resolve(), output_dir.resolve(), "stats_results.json")
    if not results_path.is_file():
        raise FileNotFoundError("Statistical code did not create stats_results.json")
    print("Stage 2: Statistical results computed and saved." if computed
          else "Stage 2: Reusing saved statistical results.")
    return True


def chart_data(run):
    """Optional charts from approved statistics; no new calculations."""
    results_path = run / "stats_output" / "stats_results.json"
    if not results_path.exists():
        return
    print(f"Statistical results size: {results_path.stat().st_size:,} bytes")
    chart_dir = run / "charts"
    chart_path = chart_dir / "chart.png"
    if chart_path.exists():
        print("Chart already saved:", chart_path)
        return
    if not (chart_dir / "chart_plan.md").exists():
        if input("Create optional charts? (y/n): ").strip().lower() != "y":
            return
        question = json.loads((run / "context.json").read_text(encoding="utf-8"))["question"]
        plan = ask_openai(
            "Propose a concise, readable chart (one figure, up to two panels) "
            "to visualize ONLY the supplied completed statistical results. "
            "Specify marks, axes, units, labels, and annotations. "
            "Do not request new statistics, raw data, or prepared row-level data. "
            "Do not generate code.",
            f"QUESTION:\n{question}\nAPPROVED STATISTICAL RESULTS:\n"
            f"{results_path.read_text(encoding='utf-8')}",
        )
        save(chart_dir / "chart_plan.md", plan)

    plan_path = chart_dir / "chart_plan.md"
    approval = chart_dir / "PLAN_APPROVED"
    if not approval.exists():
        while True:
            print("\nPROPOSED CHART PLAN:\n", plan_path.read_text(encoding="utf-8"))
            choice = input("Approve (a), revise (r), or skip (s)? ").strip().lower()
            if choice == "s":
                return
            if choice == "a":
                save(approval, "Approved by human\n")
                break
            if choice == "r":
                feedback = input("Revision request: ").strip()
                if feedback:
                    revised = ask_openai(
                        "Revise the chart plan per human feedback. Only visualize "
                        "already-computed statistics; no new analyses or code.",
                        f"CURRENT PLAN:\n{plan_path.read_text(encoding='utf-8')}"
                        f"\nFEEDBACK:\n{feedback}\nRESULTS:\n"
                        f"{results_path.read_text(encoding='utf-8')}",
                    )
                    save(plan_path, revised)

    code_path = chart_dir / "chart.py"
    if not code_path.exists():
        code = ask_openai(
            "Write concise Python 3.12 matplotlib code implementing ONLY the "
            f"approved chart plan. Read /data/{results_path.name}; save the "
            "finished figure to /output/chart.png (use Agg backend). "
            "Use ONLY statistics already present in the JSON. Do not read "
            "row-level data, calculate new statistics, or access the network. "
            "Return executable Python only, no fences.",
            f"APPROVED CHART PLAN:\n{plan_path.read_text(encoding='utf-8')}"
            f"\nRESULTS JSON:\n{results_path.read_text(encoding='utf-8')}",
        )
        save(code_path, code)

    if not chart_path.exists():
        execute_in_docker(results_path, code_path.resolve(), chart_dir.resolve(), "chart.png")
    if not chart_path.is_file():
        raise FileNotFoundError("Chart code did not create chart.png")
    print("Chart saved:", chart_path)
    print("Open chart.png to inspect the figure.")


def show_findings(run):
    """Open the interpretation and optional chart together in a local browser."""
    interpretation_path = run / "interpretation.md"
    if not interpretation_path.exists():
        return
    markdown_text = interpretation_path.read_text(encoding="utf-8")
    try:
        import mistune
        body = mistune.create_markdown(plugins=["table"])(markdown_text)
    except ImportError:
        # Small fallback for Markdown paragraphs, emphasis, and tables.
        def inline(text):
            escaped = html.escape(text.strip())
            return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)

        lines = markdown_text.splitlines()
        rendered = []
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if (line.startswith("|") and i + 1 < len(lines)
                    and re.fullmatch(r"[|:\-\s]+", lines[i + 1].strip())
                    and "-" in lines[i + 1]):
                headers = [x.strip() for x in line.strip("|").split("|")]
                rendered.append("<table><thead><tr>" + "".join(
                    "<th>" + inline(x) + "</th>" for x in headers
                ) + "</tr></thead><tbody>")
                i += 2
                while i < len(lines) and lines[i].strip().startswith("|"):
                    cells = lines[i].strip().strip("|").split("|")
                    rendered.append("<tr>" + "".join(
                        "<td>" + inline(x) + "</td>" for x in cells
                    ) + "</tr>")
                    i += 1
                rendered.append("</tbody></table>")
                continue
            if line.startswith("### "):
                rendered.append("<h3>" + inline(line[4:]) + "</h3>")
            elif line.startswith("## "):
                rendered.append("<h2>" + inline(line[3:]) + "</h2>")
            elif line.startswith("# "):
                rendered.append("<h1>" + inline(line[2:]) + "</h1>")
            elif line.startswith("- "):
                rendered.append("<p>• " + inline(line[2:]) + "</p>")
            elif line:
                rendered.append("<p>" + inline(line) + "</p>")
            i += 1
        body = "\n".join(rendered)
    chart = run / "charts" / "chart.png"
    image_tag = '<img src="charts/chart.png" alt="Analysis chart">' if chart.exists() else ""
    page = ("<!doctype html><html><head><meta charset='utf-8'>"
            "<title>Analysis findings</title><style>body{font:16px/1.55 Arial,sans-serif;"
            "max-width:1050px;margin:35px auto;padding:0 22px;color:#222}"
            "img{max-width:100%;height:auto}h1,h2,h3{margin-top:1.4em}"
            "table{border-collapse:collapse;margin:18px 0;width:100%}"
            "th,td{border:1px solid #ddd;padding:8px 12px;text-align:left}"
            "th{background:#f5f5f5}</style>"
            "</head><body><h1>Analysis findings</h1>" + image_tag + body + "</body></html>")
    report = run / "findings.html"
    save(report, page)
    webbrowser.open(report.resolve().as_uri())
    print("Findings displayed in browser:", report)


def interpret_results(run):
    """Explain completed statistics and present findings with optional chart."""
    results_path = run / "stats_output" / "stats_results.json"
    if not results_path.exists():
        return
    interpretation_path = run / "interpretation.md"
    if not interpretation_path.exists():
        question = json.loads((run / "context.json").read_text(encoding="utf-8"))["question"]
        chart_path = run / "charts" / "chart.png"
        chart_plan_path = run / "charts" / "chart_plan.md"
        chart_context = (
            "Chart was generated from the approved chart plan below. "
            "Do not claim to have visually inspected the image.\n"
            + chart_plan_path.read_text(encoding="utf-8")
            if chart_path.exists() and chart_plan_path.exists()
            else "No chart was generated."
        )
        interpretation = ask_openai(
            "Write a concise, understandable interpretation of the completed analysis "
            "that answers the research question. Use ONLY the supplied statistical "
            "results, preparation audit, and chart-plan context. Explain the key findings, relevant "
            "assumptions, limitations, and implications. Distinguish supported "
            "conclusions from speculation. Do not invent results, perform "
            "additional analysis, or propose new cleaning. "
            "Do not claim to have viewed the chart image. End with a short conclusion.",
            f"QUESTION:\n{question}\nSTATISTICAL RESULTS:\n"
            f"{results_path.read_text(encoding='utf-8')}\n"
            f"PREPARATION AUDIT:\n{(run / 'output' / 'audit_summary.json').read_text(encoding='utf-8')}\n"
            f"CHART CONTEXT:\n{chart_context}",
        )
        save(interpretation_path, interpretation)
        print("Stage 4: Interpretation saved:", interpretation_path)
    else:
        print("Stage 4: Reusing saved interpretation.")
    show_findings(run)


def follow_up(run):
    """OpenAI chooses reuse, extend, or restart for a follow-up question."""
    question = input("\nFollow-up question (Enter to finish): ").strip()
    if not question:
        return
    context = json.loads((run / "context.json").read_text(encoding="utf-8"))
    prepared = run / "output" / "prepared.csv"
    if not prepared.exists():
        raise FileNotFoundError(prepared)
    profile = read_csv_profile(prepared)
    old_plan = run / "preparation_plan.md"
    # Follow-up runs may have inherited an earlier preparation plan.
    plan = old_plan.read_text(encoding="utf-8") if old_plan.exists() else context.get("preparation_context", "")
    decision_text = ask_openai(
        "Decide whether the accepted prepared dataset can answer the NEW research "
        "question. Return ONLY a JSON object with keys 'decision' and 'reason'. "
        "decision must be exactly REUSE, EXTEND, or RESTART. "
        "Prefer REUSE when the accepted data supports the question, including "
        "ordinary analytical grouping, calculations, or derived variables based "
        "on existing columns. EXTEND only if substantive additional data "
        "preparation is needed. RESTART only if the original raw data must be "
        "prepared anew. Do not repeat completed cleaning without a specific "
        "reason. Base the choice on supplied evidence; do not invent columns "
        "or perform the analysis. Keep the explanation brief.",
        f"ORIGINAL QUESTION:\n{context['question']}\nNEW QUESTION:\n{question}\n"
        f"PREPARATION PLAN:\n{plan}\n"
        f"PREPARATION AUDIT:\n{(run / 'output' / 'audit_summary.json').read_text(encoding='utf-8')}\n"
        f"PREPARED DATA PROFILE:\n{json.dumps(profile)}",
    )
    decision = json.loads(decision_text)
    route = decision["decision"].upper()
    if route not in ("REUSE", "EXTEND", "RESTART"):
        raise ValueError("Unexpected OpenAI follow-up decision: " + route)
    print(f"Stage 5: OpenAI decision: {route} — {decision['reason']}")

    new_run = RUNS / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    new_run.mkdir()
    save(new_run / "follow_up_decision.json", json.dumps(decision, indent=2))
    raw_source = context.get("original_source", context["source"])
    if route == "REUSE":
        save(new_run / "context.json", json.dumps({
            "source": raw_source, "original_source": raw_source,
            "question": question, "prepared_from": str(run),
            "preparation_context": plan,
        }, indent=2))
        (new_run / "output").mkdir()
        shutil.copy2(prepared, new_run / "output" / "prepared.csv")
        shutil.copy2(run / "output" / "audit_summary.json",
                     new_run / "output" / "audit_summary.json")
        save(new_run / "VERIFIED", "Reused accepted prepared dataset\n")
    else:
        source = str(prepared) if route == "EXTEND" else raw_source
        save(new_run / "context.json", json.dumps({
            "source": source, "original_source": raw_source,
            "question": question, "follow_up_route": route,
            "preparation_context": plan,
            "previous_question": context["question"],
        }, indent=2))
        print(f"Stage 5: {route} requires a new preparation plan and human approval.")
        if prepare_data(selected_run=new_run) is None:
            return
        if not (new_run / "VERIFIED").exists():
            return

    if analyze_data(new_run):
        chart_data(new_run)
        interpret_results(new_run)


if __name__ == "__main__":
    run = prepare_data()
    if run is not None and (run / "VERIFIED").exists():
        if analyze_data(run):
            chart_data(run)
            interpret_results(run)
            follow_up(run)
