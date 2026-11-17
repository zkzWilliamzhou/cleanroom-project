# Vendored skills

GitHub skill collections were pulled into `/data/workspace/.skills/` from public repositories on 2026-11-12. They are vendored as readable reference material and their procedures are applied in this project. Registering new platform-level skills is outside what this environment can do, so "installed" here means vendored, read, and enforced on the work.

| Collection | Source | Applied where |
|---|---|---|
| Anthropic Agent Skills | `anthropics/skills` | `skill-creator` and `mcp-builder` informed `skills/cleanroom/SKILL.md` and the report contract |
| Matt Pocock skills | `mattpocock/skills` | `grill-me`/`grilling` for the novelty interrogation; `tdd`, `code-review`, `improve-codebase-architecture` for implementation and the final refactor |
| Vercel Labs skills CLI | `vercel-labs/skills` | `find-skills` discovery pattern |
| Vercel Agent Skills | `vercel-labs/agent-skills` | `writing-guidelines` for README and report prose |
| Stop Slop | `tomerose/stop-slop` | Prose review gate in `AGENT_WORKFLOW.md` |
| Superpowers | `obra/superpowers` | `brainstorming`, `test-driven-development`, `verification-before-completion`, `systematic-debugging`, `requesting-code-review` |
| Superpowers skills repo | `obra/superpowers-skills` | `writing-plans`, `defense-in-depth`, `testing-anti-patterns`, `dispatching-parallel-agents` |

Platform skills also used: `scientific-brainstorming` (independent generation, transparent criteria, dissent preservation), `scientific-critical-thinking` (claim-versus-evidence separation), and `archify` (workflow diagram).

The program ships its own Agent Skill at `skills/cleanroom/SKILL.md`, written in the open `SKILL.md` format so a coding agent can invoke `cleanroom` without guessing flags.

Licenses remain with their upstream owners. Vendored copies are not redistributed inside the release archive.
