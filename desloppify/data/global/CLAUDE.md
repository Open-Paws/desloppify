## Claude Code Overlay

Use Claude subagents for subjective scoring work. **Do not use `--runner codex`** — use Claude subagents exclusively.

### Review workflow

Run `desloppify review --prepare` first to generate review data, then use Claude subagents:

1. **Prepare**: `desloppify review --prepare` — writes `query.json` and `.desloppify/review_packet_blind.json`.
2. **Launch subagents**: Split the review across N parallel Claude subagents (one message, multiple Task calls). Each agent reviews a subset of dimensions.
3. **Merge & import**: Merge agent outputs, then `desloppify review --import merged.json --manual-override --attest "Claude subagents ran blind reviews against review_packet_blind.json" --scan-after-import`.

#### How to split dimensions across subagents

- Read `dimension_prompts` from `query.json` for dimensions with definitions and seed files.
- Read `.desloppify/review_packet_blind.json` for the blind packet (no score targets, no anchoring data).
- Group dimensions into 3-4 batches by theme (e.g., architecture, code quality, testing, conventions).
- Launch one Task agent per batch with `subagent_type: "general-purpose"`. Each agent gets:
  - The codebase path and list of dimensions to score
  - The blind packet path to read
  - Instruction to score from code evidence only, not from targets
- Each agent writes output to `results/batch-N.raw.txt` (matching the batch index). Merge assessments (average overlapping dimension scores) and concatenate findings.

### Subagent rules

1. Each agent must be context-isolated — do not pass conversation history or score targets.
2. Agents must consume `.desloppify/review_packet_blind.json` (not full `query.json`) to avoid score anchoring.

### Triage workflow

Orchestrate triage with per-stage subagents:
1. `desloppify plan triage --run-stages --runner claude` — prints orchestrator instructions
2. For each stage (strategize → observe → reflect → organize → enrich → sense-check):
   - Get prompt: `desloppify plan triage --stage-prompt <stage>`
   - Launch a subagent with that prompt
   - Verify: `desloppify plan triage` (check dashboard)
   - Confirm: `desloppify plan triage --confirm <stage> --attestation "..."`
   - Note: `strategize` is auto-confirmed on record — `--confirm` is optional for that stage only
3. Complete: `desloppify plan triage --complete --strategy "..." --attestation "..."`

## Files in docs/

| File | What it covers | When to read |
|------|---------------|--------------|
| `AMP.md` | AMP (Amp Code) agent overlay | Using desloppify with AMP |
| `CLAUDE.md` | This file — Claude Code subagent workflow | Claude Code sessions |
| `CODEX.md` | Codex agent overlay | Using desloppify with Codex |
| `COPILOT.md` | GitHub Copilot agent overlay | Using desloppify with Copilot |
| `CURSOR.md` | Cursor agent overlay | Using desloppify with Cursor |
| `DEVELOPMENT_PHILOSOPHY.md` | Upstream development philosophy and scoring principles | Understanding scoring decisions |
| `DROID.md` | Droid agent overlay | Using desloppify with Droid |
| `GEMINI.md` | Gemini CLI agent overlay | Using desloppify with Gemini CLI |
| `HERMES.md` | Hermes agent overlay | Using desloppify with Hermes |
| `OPENCODE.md` | OpenCode agent overlay | Using desloppify with OpenCode |
| `QUEUE_LIFECYCLE.md` | Work queue lifecycle documentation | Understanding plan/next flow |
| `SKILL.md` | Universal skill file for any agent | When installing desloppify skill |
| `WINDSURF.md` | Windsurf agent overlay | Using desloppify with Windsurf |
| `ci_plan.md` | CI planning documentation | CI setup |
| `commit-summary-since-0.7.0.md` | Commit history since v0.7.0 | Understanding recent changes |
| `work-batches-since-0.7.0-ticket-digest.md` | Work batch digest since v0.7.0 | Understanding work history |

## Cross-References

- For the root agent instructions, see `../CLAUDE.md`
- For the identical overlay in data/global/, see `../desloppify/data/global/CLAUDE.md`
- For the full desloppify architecture, see `../CLAUDE.md`

<!-- desloppify-overlay: claude -->
<!-- desloppify-end -->
