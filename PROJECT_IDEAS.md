# Related AI Systems Projects

These ideas reuse the strongest parts of Prompt Rewriter: a fast user action, provider routing,
strict validation, safe failure behavior, and evidence instead of vague AI claims.

The ranking favors **portfolio signal**, **systems depth**, **measurable evaluation**, and a realistic
MVP scope. It is not a claim that every idea should be built.

## Reusable foundation first

Before starting another repository, extract the parts that can become a small internal library:

- selected-text or command input adapter
- one-job-at-a-time action runner
- local/cloud provider interface and fallback router
- typed output schema and validation
- timeout, cancellation, and redacted logging helpers
- focus/clipboard guard for desktop actions

Keep product-specific prompts and policies outside that library. This turns each follow-on project
into a new decision system instead of a copy of the same hotkey code.

## Ranked ideas

### 1. Evidence Lens — claim-to-source verifier

**Portfolio story:** A user highlights a claim or draft paragraph. The tool searches an approved
document set, reranks the evidence, and returns `supported`, `contradicted`, or
`insufficient evidence` with exact source passages.

**MVP:** Index a small, versioned collection of PDFs or Markdown files; retrieve candidate passages;
rerank them; return a structured verdict with document, page/section, and passage identifiers.

**Evaluate:** Build a human-reviewed claim/evidence set and report retrieval recall at k, verdict
accuracy, insufficient-evidence accuracy, and citation correctness. Publish the evaluation-set size
and provenance with every result.

**Safety boundary:** This is an evidence assistant, not a truth oracle. It must never invent a
citation, and it should prefer `insufficient evidence` when the indexed sources do not support a
decision.

### 2. Privacy-Aware Model Router

**Portfolio story:** Route requests to local or cloud models according to detected secrets, personal
data, task complexity, policy, and provider health.

**MVP:** Detect common API keys, credentials, email/phone patterns, and user-defined sensitive terms;
then block, redact, route locally, or ask for confirmation. Record decisions without storing raw
input.

**Evaluate:** Use versioned synthetic and manually reviewed fixtures. Report detection precision and
recall by entity type, routing-policy accuracy, and redaction coverage. Treat false negatives as the
highest-risk error rather than hiding them inside one aggregate score.

**Safety boundary:** Pattern detectors cannot guarantee that text is safe. Default to local or block
when uncertain, do not log sensitive spans, and never market the result as complete data-loss
prevention.

### 3. SchemaGuard SQL Copilot

**Portfolio story:** Convert a question into schema-grounded SQL while enforcing a read-only policy
before anything reaches a database.

**MVP:** Read a database schema, generate one query, parse its abstract syntax tree, reject anything
other than a single `SELECT`, run `EXPLAIN` through a read-only connection, and show SQL plus the
assumptions used.

**Evaluate:** Use a small database with reviewed question/query pairs. Report execution accuracy,
result equivalence, unsafe-query rejection rate, invalid-column rate, and timeout rate.

**Safety boundary:** Never grant write privileges. Enforce statement type, row limits, query timeout,
and an approved schema at the database layer—not only in the prompt.

### 4. Label Audit Hotkey

**Portfolio story:** Highlight CSV or TSV rows and flag likely label mistakes, ambiguous examples,
duplicates, and model/human disagreements for review.

**MVP:** Parse selected rows, run deterministic duplicate and consistency checks, add model-assisted
flags, and export a review queue with provenance and reason codes.

**Evaluate:** On a human-reviewed sample, report flag precision, recall where ground truth exists,
duplicate-detection accuracy, and reviewer agreement. Keep deterministic and model-assisted results
separate.

**Safety boundary:** Never overwrite source labels. Output must remain `pending_human_review`; it
cannot be called `human_reviewed` until a person explicitly approves it.

### 5. PromptEval Desktop Harness

**Portfolio story:** Compare prompts and providers on the same versioned cases instead of choosing a
model from anecdotes.

**MVP:** Run prompt/model variants against a small task suite and store inputs, configuration,
outputs, JSON-validity checks, task-specific assertions, token usage when available, and latency.

**Evaluate:** Report pass rate by deterministic check, schema-validity rate, error rate, and separate
warm/cold latency distributions. Preserve raw results so another person can reproduce the summary.

**Safety boundary:** An LLM judge is a noisy signal, not ground truth. Label it clearly, pair it with
deterministic checks or human review, and do not send private evaluation data to an unapproved cloud
provider.

### 6. Data Contract Generator

**Portfolio story:** Turn an example DataFrame, SQL result, or schema into reviewable Pandera or
Great Expectations checks.

**MVP:** Infer candidate types, null rules, ranges, categories, and uniqueness constraints; generate
a contract; then validate it in a sandbox against held-out sample data.

**Evaluate:** Use mutation tests that introduce known schema problems. Report the percentage of
mutations detected, false-positive rate on clean data, and rules rejected or changed by a reviewer.

**Safety boundary:** Inferred constraints are hypotheses. Do not silently deploy them or claim they
represent business rules without domain-owner approval.

### 7. Reproducible Experiment Card

**Portfolio story:** Convert training configuration, logs, and metric artifacts into a compact model
experiment card with provenance.

**MVP:** Extract dataset version, split strategy, seed, model/config hash, environment, metrics, and
artifact paths. Mark absent values as unknown rather than asking a model to fill them.

**Evaluate:** Compare extracted fields with reviewed experiment records. Report exact field accuracy,
missing-field detection, and unsupported-field rate.

**Safety boundary:** Never invent a metric, data split, seed, or hardware claim. Keep reported facts,
derived values, and narrative suggestions visually distinct.

### 8. LogSherlock — evidence-linked incident assistant

**Portfolio story:** Turn an error trace plus an approved runbook collection into ranked hypotheses
with evidence and safe diagnostic steps.

**MVP:** Parse logs, retrieve relevant runbook sections, show the exact evidence for each hypothesis,
and propose read-only checks. Require the user to run or approve any state-changing command.

**Evaluate:** Use historical or synthetic incidents with reviewed root causes. Measure whether the
correct cause and useful runbook passage appear in the top k, plus citation correctness.

**Safety boundary:** Never auto-execute a repair, and redact tokens, user data, hostnames, and other
sensitive log content before cloud inference.

### 9. Fact-Locked Plain-Language Transformer

**Portfolio story:** Simplify dense text while preserving names, numbers, dates, negation, and
citations.

**MVP:** Extract protected facts before rewriting, require structured output, and reject a rewrite
when invariants are missing or changed.

**Evaluate:** Report exact preservation of protected spans, numeric consistency, negation changes,
reading-level change, and human-rated meaning preservation on a reviewed test set.

**Safety boundary:** Automated invariant checks do not prove semantic equivalence. High-stakes
medical, legal, or financial text still requires qualified human review.

### 10. Evidence-Only Job Matcher

**Portfolio story:** Compare a live job description with a verified personal evidence store and
return supported matches, honest gaps, and questions to resolve.

**MVP:** Store projects, skills, dates, and links with source references; parse a saved job
description; map requirements only to cited evidence; and generate a reviewable fit brief.

**Evaluate:** Use human-reviewed requirement/evidence pairs. Report mapping precision and recall,
unsupported-claim count, stale-job detection, and reviewer acceptance—not an invented “chance of
hiring.”

**Safety boundary:** Never fabricate experience, metrics, sponsorship facts, or recruiter identity.
Live job status and policy must be reverified at action time.

## Recommended build order

Do not build ten disconnected demos. Build one reusable system in this order:

1. **Extract the action engine from Prompt Rewriter.** Keep provider routing, schemas, timeouts, and
   safe desktop actions reusable, but preserve a small public API.
2. **Build Privacy-Aware Model Router.** It improves every later project by making local/cloud
   decisions explicit and testable.
3. **Build Evidence Lens as the flagship project.** It adds retrieval, reranking, calibrated
   abstention, citations, and a real evaluation set—the strongest next portfolio story.
4. **Add PromptEval Desktop Harness.** Use it to benchmark the router and Evidence Lens with
   repeatable cases instead of one-off examples.
5. **Choose one specialization:** SchemaGuard for ML/platform engineering, or Label Audit for data
   science and research workflows.

If there is time for only one new repository, start with **Evidence Lens**. If the goal is a coherent
multi-project platform, build the **Privacy-Aware Model Router** first and reuse it everywhere.

## Evidence checklist for every project

Before calling any project portfolio-ready, include:

- a versioned evaluation set with clear provenance
- deterministic checks alongside model-based scoring
- exact test-set size and label distribution from files
- failure examples, not only successful demos
- cold and warm latency reported separately on named hardware
- explicit local/cloud data flow
- screenshots or video labeled as demonstrations, not benchmarks
- reproducible commands and dependency versions
- a `pending_human_review` state wherever human approval is still required

Strong portfolio claims come from artifacts and repeatable tests—not adjectives.
