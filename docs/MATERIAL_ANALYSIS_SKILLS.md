# Material-analysis skills

Curriculum → subject → Books & lessons → **Skills dos materiais** exposes two
family-shared instruction sets with editable text and version history:

- **Livro em JSON**: faithful page transcription, structured visual descriptions,
  exercise identity, private key evidence and source uncertainty.
- **Relações entre materiais**: source-grounded reading/exercise connections,
  prerequisites and the exact book targeted by each answer key.

Saving creates a version; selecting an earlier version restores a draft only.
Saving instructions does not launch analysis, generate lessons or alter learner
history. Teaching skills remain in the existing **Teaching skill** tab and serve
a different purpose: age, subject pedagogy and personalized lesson preparation.

The shipped starters are `tutor/materials/{book-json,material-links}/GUIDE.md`.
On normal server startup the initial rules are preserved as version 0. Family
edits are authoritative and never overwritten by starter-file updates.
`material_skills` stores immutable versions and corresponding Markdown files in
the family folder's **Material Skills** directory. Backup and test-mode isolation
use the standard storage mechanisms. These files contain source-analysis rules,
not learner answers or book answer keys.

New analysis jobs freeze both skill versions and hashes in their plan. Provider
prompts and cache identities use that frozen content; editing a skill invalidates
an unsent cost preview but does not change an analysis already in progress.
Integrated subject-knowledge archives preserve the instruction snapshots too.

The reusable Codex workflows are also preserved in the repository:
`tutor/skills/homeschooling-book-companion/SKILL.md` and
`tutor/skills/homeschooling-material-map/SKILL.md`. Installed copies live under
the user's `.codex/skills`. They read the current app rules through
`GET /api/material-skills` and use the same canonical schemas.

## Local review

Codex can inspect PDF pages and prepare a corrected JSON without a provider call.
**Importar correção revisada** requires a review note and the current source
revision; earlier scans and source snapshots remain immutable. The companion's
native extraction stays intact. Corrections belong in its checked transcription.

**Atualizar com JSONs revisados** creates a new map snapshot from saved source
corrections without calling AI. Existing relationships are revalidated against
those sources; unsupported proposals remain pending. It is not an automatic
semantic review of every proposal and does not activate teaching or schedules.
The prior map keeps its original source snapshot when opened or exported.

`POST /api/subjects/{subject}/book-collection/source-review` also accepts explicit
relationship decisions. Proposed reading dependencies require exact checked-page
citations. A self-contained task requires a literal instruction quote. The request
pins the expected map, collection version and companion hashes; stale state is
rejected. No question or response is fabricated during this operation.
