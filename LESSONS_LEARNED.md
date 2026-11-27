# Lessons Learned: Building an AI Analytics Agent

## Introduction

AnalyticsAgentV3 is a human-supervised prototype for data preparation, statistical analysis, visualization, and interpretation using Python, OpenAI, and Docker. The project explored how an analytics professional can work with an LLM while retaining responsibility for consequential decisions. Development involved multiple architectures, code failures, tests, and independent reviews.

Five lessons emerged.

## 1. Agent Architecture: Separate Responsibilities

An important distinction is between designing the agent's workflow and using an LLM to plan analytical work. The workflow defines the sequence of steps and approval points; the LLM proposes plans and generates code within those rules. A Python controller coordinates the work, Docker executes generated code, and the human approves consequential plans.

### AnalyticsAgentV3: End-to-End Workflow

![AnalyticsAgentV3 end-to-end workflow](workflow.png)

The final architecture separates five responsibilities:

- **Planning:** OpenAI proposes analytical steps before generating code.
- **Approval:** The human reviews consequential assumptions and proposed plans.
- **Execution:** Generated Python code runs in a restricted Docker container.
- **Verification:** The controller reconciles prepared data with a preparation audit recording input rows, exclusions, output rows, and remaining missing values.
- **Interpretation:** OpenAI explains saved results and supports follow-up questions.

The approved, question-specific prepared dataset is frozen for analysis and potential follow-ups. Optional charts use saved statistical results rather than performing new statistical analyses. This separation reduces the risk of chart generation introducing unapproved calculations. It also makes the results easier to trace.

### One LLM or Two?

The earliest architecture used **Gemini to generate analytical plans and Python code**, **Claude to review them independently**, and **ChatGPT to assist the human developer**. After repeated Gemini HTTP 503 (“Service Unavailable”) errors and timeouts, **OpenAI replaced Gemini as generator**, while Claude remained the reviewer. The final runtime architecture uses **OpenAI alone**; Claude remained available for occasional external development review.

Independent review sometimes caught real defects, but it could also produce speculative objections or misjudge their importance. In one case, Claude initially treated a defect capable of producing millions of erroneous audit records as optional. We accepted the loss of a second review perspective in exchange for a simpler operational workflow, recognizing that some errors may still escape detection.

**Lesson:** Allocate responsibilities deliberately and choose the number of LLMs based on demonstrated value, not the assumption that more reviews guarantee better results.

## 2. Human Oversight: Focus on Consequential Decisions

The human should evaluate choices that materially affect the analysis, especially exclusions, assumptions, and analytical methods. However, approving a plan does not mean every line of generated code or every statistical conclusion has been independently verified.

For example, Gemini proposed excluding Divvy bicycle rides longer than 24 hours without adequate justification and treated unique ride IDs as proof of statistical independence. It also inserted hard-coded analytical conclusions rather than computing them. These problems emerged through iterative development and testing, with ChatGPT assisting in identifying and assessing defects. A controller safeguard also incorrectly rejected a legitimate pandas `dropna()` operation.

For follow-up questions, OpenAI chooses whether to **REUSE** the frozen prepared dataset, **EXTEND** it with further preparation, or **RESTART** from raw data. The human approves any new preparation and statistical plans. The controller handles one follow-up question per execution. If a statistical-plan revision requires changing the frozen dataset, the controller directs the human to stop and submit it as a new follow-up question from the parent run.

The controller saves a parent-run reference for follow-ups. When the parent question and statistical results are available, the existing interpretation request includes them and asks OpenAI to compare only compatible measures, identify differences in analytical populations, and flag uncertain comparability.

**Lesson:** Make oversight substantive: inspect consequential assumptions and results rather than treating an approval step as proof of correctness.

## 3. Execution Controls: Separate Generated Code from the Controller

AI-generated code can fail or behave unexpectedly. AnalyticsAgentV3 therefore runs generated Python scripts in Docker rather than directly in the controller environment. Network, filesystem, memory, and CPU restrictions reduce some risks but do not guarantee security or correctness.

The controller saves generated code, preparation audits, statistical results, and charts as evidence for checking outcomes, understanding decisions, and resuming work. Preparation checks reconcile input rows, excluded rows, and prepared rows, along with missing-value summaries; they do **not** independently validate every statistical calculation or detect all hard-coded findings.

**Lesson:** Control code execution, preserve evidence, and recognize the limits of verification.

## 4. Verification and Recovery: Expect Errors

In testing, generated code attempted to call pandas `.fillna()` on a NumPy array. Execution failed; the controller saved the error, and after the human resumed the run, the LLM corrected the code. Other tests revealed stale audit files and inconsistent exclusion counts, prompting targeted verification fixes.

Codex reviewed the controller, reproduced three defects with synthetic inputs and simulated model responses, made targeted corrections, and ran regression tests. Resumed **EXTEND** runs now retain preparation context, statistics must be a non-empty JSON object before acceptance or reuse, and profiling and verification share a chunked pandas row count that skips blank lines. On the full-year Divvy CSV, both counting methods found 5,552,994 rows. Across three scans per method, the median was 8.56 seconds for chunked pandas and 10.62 seconds for `csv.reader`. Human-supervised end-to-end tests complemented these checks by validating **REUSE** and **EXTEND** through interruption and resumption and confirming comparison with prior results.

The prototype also completed analyses of approximately **5.55 million 2025 Divvy rides**, including a seasonal follow-up using **REUSE**. An airline arrival dataset covering **January 1–December 31, 2025** contained **539,747 flights**; excluding **16,312 cancelled** and **1,166 diverted** flights left **522,269**. The initial question compared delays of at least 15 minutes by airline. A follow-up on delays of at least 30 minutes used **EXTEND** to add an indicator and completed statistics, charting, and interpretation without further exclusions. **RESTART has not been tested.**

**Lesson:** Test the complete workflow with real datasets, document failures and their corrections, and provide a way to recover from execution errors.

## 5. Simplicity: Justify Every Additional Control

During development, reviews, approval gates, audit procedures, and recovery logic accumulated. By the third week, the controller had reached **2,737 lines**. Removing the routine second-LLM review and associated state-management complexity helped reduce it to **632 lines**, approximately **77% fewer**. The earlier write-up reported 633 lines. The committed version reviewed by Codex has 632. This reduction made the workflow easier to understand. The controller reached **666 lines** after the targeted corrections and follow-up enhancements.

The retained controls address demonstrated needs: Docker isolation, human approval of consequential plans, saved evidence, and targeted deterministic checks. But the system remains a research prototype, not a production-ready analytics service.

**Lesson:** Prefer a simple, understandable architecture, and retain controls whose purposes and benefits justify their costs.

## Results and Limitations

The Divvy and airline runs demonstrate that the prototype can complete selected end-to-end analyses and follow-up workflows. But they do not establish reliability across arbitrary datasets or analytical questions. Some errors still require human intervention, and an EXTEND audit may describe new exclusions without the full earlier exclusion history. Broader testing would be needed before deployment.

## Conclusion

A useful analytics agent requires more than a capable LLM. Its effectiveness depends on workflow design, analytical judgment, controlled execution, evidence, recovery, and meaningful human oversight. The goal is to assist the analytics professional, not remove human accountability.

*Related experience-based article: “Building a Human-Supervised AI Analytics Agent: Lessons from a Working Prototype” (manuscript prepared for editorial consideration).* 

## Acknowledgment

ChatGPT (OpenAI) contributed substantially to the controller's design and coding, debugging, architectural revisions, and preparation of this documentation. Codex contributed code review, defect reproduction, regression testing, and targeted corrections. The human developer directed the project, made the final design decisions, tested the system, and retains responsibility for the work and its conclusions.
