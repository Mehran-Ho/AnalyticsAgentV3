# AnalyticsAgentV3

**A human-supervised AI analytics agent — research prototype**

AnalyticsAgentV3 explores how a large language model can help an analytics professional prepare data, perform statistical analysis, create charts, and interpret results while keeping consequential decisions under human control. It uses a Python controller, the OpenAI API, and Docker to execute generated Python code in a restricted environment.

The project is a **working prototype, not a production-ready or fully validated analytics system**.

## How it works

1. **Question and data:** The human supplies a research question and CSV file. The controller profiles the dataset and sends a compact profile to OpenAI.  This includes column names, missing-value counts, and three sample rows.
2. **Scope:** OpenAI assesses the scope of the question; the human accepts, revises, or stops.
3. **Data preparation:** OpenAI proposes a question-specific data preparation plan for human approval, then generates code.  Docker executes the approved code. The controller checks row counts, exclusions, and remaining missing values against an audit. The human reviews the audit summary and accepts the prepared dataset, which is then frozen for analysis and possible follow-ups.
4. **Analysis:** OpenAI proposes a statistical plan for human approval, generates code, and the controller runs it in Docker.
5. **Charts and report:** For optional charts, OpenAI proposes one figure with up to two panels for human approval. Once approved, OpenAI generates code to create charts based on saved statistical results only; the controller executes it in Docker. OpenAI then interprets the results and produces an HTML report.
6. **Follow-up:** OpenAI chooses whether to **REUSE** the prepared dataset, **EXTEND** it with additional preparation, or **RESTART** from the original data. The human reviews and approves any new preparation or statistical analysis plan before execution. The current controller handles **one follow-up question per execution**. If the question is revised after routing, it **does not automatically reconsider** the original REUSE/EXTEND/RESTART decision.

If execution fails, the controller saves error details. The human can restart the controller and choose to resume. During data preparation, saved verification errors inform corrected code generation; in later stages, error details are not automatically reused.

The controller coordinates the workflow and approval gates. **OpenAI is the only LLM used at runtime.** Earlier development used Gemini for generation and Claude for independent review; OpenAI later replaced Gemini as generator. Claude was also used for occasional independent development reviews.

For the design rationale, experience, and known trade-offs, see [Lessons Learned](LESSONS_LEARNED.md).

## Requirements

- Python 3 and `pip`
- [Docker Desktop / Docker Engine](https://docs.docker.com/get-docker/), installed and running
- An OpenAI API key with access to the configured model
- Python packages: `openai`, `python-dotenv`
- The project's Docker image, named **`divvy-analytics:latest`**, containing the Python analysis libraries used by the generated scripts
- Visual Studio Code (recommended, not required)

Docker runs generated scripts separately from the controller. The controller runs the approved code in a Docker container with no network access, a read-only container filesystem, restricted file mounts, and CPU/memory limits. These controls reduce risk but do not guarantee complete isolation or correctness.

## Setup and run

1. Put `controller.py` in a project folder.
2. Install the controller's Python dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

3. Create a `.env` file in that folder containing:

   ```text
   OPENAI_API_KEY=your_api_key_here
   ```

   The controller defaults to model `gpt-6`; optionally set `OPENAI_MODEL` in `.env` to another model supported by your account and the Responses API. The controller communicates with OpenAI models through the Responses API.

4. Start Docker. Build the project image:

   ```bash
   docker build -t divvy-analytics:latest .
   ```

5. Run the controller from the project folder:

   ```bash
   python controller.py
   ```

6. Enter the path to a CSV file and your research question. Review proposed plans and the preparation summary when prompted. Optionally request charts and a follow-up question.

The controller saves run-specific artifacts under `runs_v3/`, including generated code, preparation audits, results, charts, and reports. Do not publish `.env`, API keys, or private datasets.


## Data sources
Divvy: [Divvy System Data](https://divvybikes.com/system-data) — monthly bike-share trip files.

Airline: [Bureau of Transportation Statistics — On-Time Performance](https://www.transtats.bts.gov/DL_SelectFields.aspx?QO_fu146_anzr=b0-gvzr&gnoyr_VQ=FGJ) — airline flight data.

## Demonstrated results

- **Divvy bicycle-sharing data:** The prototype completed an analysis of approximately **5.55 million rides from 2025**, including a summer-versus-winter follow-up that used **REUSE** without repeating preparation. A separate February 2025 analysis used **151,880 input rides**, **151,865 prepared rides**, and **15 excluded rides**.
- **Airline arrival data:** On a 2025 dataset containing **539,747 flights**, the controller excluded **16,312 cancelled** and **1,166 diverted** flights, leaving **522,269** flights for a comparison of arrivals delayed at least 15 minutes by 15 airlines. A follow-up on delays of at least 30 minutes used **EXTEND** to add a delay indicator, then completed statistics, chart generation, and interpretation without further exclusions.
- **Error recovery:** A generated-code error involving `.fillna()` on a NumPy array was corrected after a human-resumed run.

These demonstrations establish feasibility, **not** reliability across arbitrary datasets or questions. **REUSE and EXTEND have been tested; RESTART has not.**

## Known limitations

- Only one follow-up question is handled per execution; changing a question after routing does not automatically trigger a new routing decision.
- Resuming certain interrupted follow-up analyses may lose some context.
- After an **EXTEND** follow-up, the audit may show only newly excluded rows rather than the complete exclusion history.
- Audit reconciliation does not independently validate every statistical method, analytical assumption, or conclusion.
- The controller currently expects CSV input and the specific Docker image named above; broader portability has not been established.

## Project status

**Published research prototype.** The repository contains the controller, Dockerfile, dependencies, workflow diagram, and documentation. It is available for inspection and experimentation, but has not been validated for production use or broadly tested on fresh installations and arbitrary datasets.

## Acknowledgment

ChatGPT (OpenAI) assisted substantially with the design, coding, debugging, and documentation of AnalyticsAgentV3. The human developer retains responsibility for the project and its conclusions.