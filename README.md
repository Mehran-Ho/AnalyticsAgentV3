# AnalyticsAgentV3

**A human-supervised AI analytics agent — research prototype**

AnalyticsAgentV3 explores how a large language model can help an analytics professional prepare data, perform statistical analysis, create charts, and interpret results while keeping consequential decisions under human control. It uses a Python controller, the OpenAI API, and Docker to execute generated Python code in a restricted environment.

The project is a **working prototype, not a production-ready or fully validated analytics system**.

## How it works

1. **Question and data:** The human supplies a research question and CSV file. The controller profiles the dataset and sends a compact profile to OpenAI.
2. **Scope:** OpenAI assesses the scope of question; the human accepts, revises, or stops.
3. **Data preparation:** OpenAI proposes a data preparation plan for human approval, then generates code. Docker executes the code. The controller checks row counts, exclusions, and remaining missing values against an audit. The human reviews the audit summary and accepts the prepared dataset.
4. **Analysis:** OpenAI proposes a statistical plan for human approval, generates code, and controller runs it in Docker.
5. **Charts and report:** For optional charts, OpenAI proposes two charts for human approval. Once approved, OpenAI generates the code, which the controller executes in Docker. OpenAI then interprets the results and produces an HTML report.
6. **Follow-up:** OpenAI determines whether to REUSE, EXTEND, or RESTART the prepared dataset. The human then reviews and approves any proposed data preparation or statistical analysis plan before execution.

If execution fails, the controller saves error details. The human can restart the controller and choose to resume; the saved error can inform corrected code generation.

The controller coordinates the workflow and approval gates. **OpenAI is the only LLM used at runtime.** Claude was used separately for independent review during development.

For the design rationale, experience, and known trade-offs, see [Lessons Learned](LESSONS_LEARNED.md) (to be included in the repository).

## Requirements

- Python 3 and `pip`
- [Docker Desktop / Docker Engine](https://docs.docker.com/get-docker/), installed and running
- An OpenAI API key with access to the configured model
- Python packages: `openai`, `python-dotenv`
- The project's Docker image, named **`divvy-analytics:latest`**, containing the Python analysis libraries used by the generated scripts
- Visual Studio Code (recommended, not required)

Docker runs the generated scripts separately from the controller. The controller invokes containers with no network access, read-only container filesystem, restricted file mounts, and CPU/memory limits. These controls reduce risk but do not guarantee complete isolation or correctness.

## Setup and run

The instructions below reflect the current controller. **The Dockerfile and final dependency list still need to be packaged and verified before publication.**

1. Put `controller_v3_user_guidance.py` in a project folder.
2. Install the controller's Python dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

3. Create a `.env` file in that folder containing:

   ```text
   OPENAI_API_KEY=your_api_key_here
   ```

   The controller defaults to model `gpt-6`; optionally set `OPENAI_MODEL` in `.env` to another model supported by your account and the Responses API.  The controller communicates with OpenAI models through the Responses API.

4. Start Docker. Build the project image **after the repository Dockerfile is supplied and verified**:

   ```bash
   docker build -t divvy-analytics:latest .
   ```

5. Run the controller from the project folder:

   ```bash
   python controller.py
   ```

6. Enter the path to a CSV file and your research question. Review the proposed plans and preparation summary when prompted. Optionally request charts and a follow-up question.

The controller saves run-specific artifacts under `runs_v3/`, including generated code, preparation audits, results, charts, and reports. Do not publish `.env`, API keys, or private datasets.

## Demonstrated results

The prototype completed an analysis of approximately **5.55 million Divvy bike-share trips from 2025**, including a seasonal follow-up using prepared data. It also completed a separate February 2025 analysis with **151,880 input trips**, **151,865 prepared trips**, and **15 excluded trips**. A generated-code error was encountered and successfully recovered through the resume workflow.

These demonstrations establish feasibility, **not** reliability across arbitrary datasets or questions.

## Known limitations

- Resuming certain interrupted follow-up analyses may lose some context.
- After an **EXTEND** follow-up, the audit may show only newly excluded rows rather than the complete exclusion history.
- Audit reconciliation does not independently validate every statistical method, analytical assumption, or conclusion.
- The controller currently expects CSV input and the specific Docker image named above; broader portability has not been established.

## Project status

Documentation and repository packaging are in progress. Before release, verify the Dockerfile, pinned or documented dependencies, setup steps, and sample outputs against a fresh installation.
