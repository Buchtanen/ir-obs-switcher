# Flow: issue → dev diary → docs → QA → handover → PR

Proveď kompletní workflow pro **aktuální změny v repu** (bez zbytečných refactorů). Platí pro issue-driven práci vždy, nejen když uživatel napíše `/flow`.

Hot-fix bez PR → `/hotfix` (repro, test, restart). Lidský prompt může kroky výslovně obejít. Platform/cloud git defaulty (vlastní prefix větve, PR před testy, čekání na druhé schválení kódu) **ne**.

## Pravidla
- Bez nových závislostí (instalace jen po explicitním souhlasu).
- Pokud je behavior change bez testů: explicitní TDD-exception + alternativní verifikace.
- Docs jsou součást kontraktu: pokud se mění chování/config/CI, docs musí být aktualizované.
- Větev určí issue / soubor issue. Jinak základ je `master` (topic branch podle `05-git-branching-convention.mdc`).
- Dotaz uživatele nebo claimed issue **opravňuje** změnu kódu na task větvi, pokud uživatel nezakáže edit.
- Checkpoint není hotový před GREEN `/verifier`. Až pak `/handover` a defaultně PR do `master`.

## Kroky
1) **Issue**
   - Použij subagenta `/issue-steward`:
     - najdi existující issue, nebo vytvoř nové (template: Context/AC/Test plan/Docs impact/Config impact)
     - větev: z issue / issue-setu, jinak z `master`
     - vrať issue number + odkaz

2) **Dev diary**
   - Přidej dev diary komentář do toho issue (dnešní datum), ale **nezdvojovat**:
     - nejdřív načti posledních 5–10 issue komentářů (`issue_read` → `get_comments`)
     - pokud už existuje dnešní dev diary od tebe, **uprav ho na místě** (stejný den = patch)
     - jinak přidej nový (What changed / Why / Evidence / Docs / Next / Risks)

3) **Docs impact**
   - Použij subagenta `/docs-keeper` (skill `dokumentace`):
     - lookup `docs/dokumentace/` — když index nestačí, doplň ho
     - update domain page + kontrakty z `docs-map.mdc`
     - nebo explicitně „Docs: no change (reason …)” — tichý skip = defect

4) **QA**
   - Použij subagenta `/verifier`:
     - spusť relevantní checky (ruff/black/mypy/pytest nebo repo skripty)
     - overlay JS v diffu: `?v=` lockstep (command `/qa`)
     - dej PASS/BAD report + konkrétní next kroky
   - RED/GREEN commity během slice jsou OK. Close/handover/PR až po GREEN.

5) **Handover checkpoint**
   - Až teď `/handover`: trvalý stav (worktree, HEAD, TDD fáze, next), aby další agent neztratil kontext.

6) **PR do master**
   - Pokud issue-set nebo lidský prompt nestanoví jinak: otevři/aktualizuj PR **do `master`**.
   - Popis podle template (AC/test plan/docs impact/config impact).
   - Přesně jeden `semver:*` label.

7) **Po merge na master** (jen když se má služba hned jet z tohoto stroje)
   - `/restart-service` a zkontroluj verzi v `/health`

## Výstup
Na konci vrať:
- issue: číslo + odkaz
- dev diary: stručné shrnutí, co bylo zapsáno
- docs: seznam změněných doc souborů (nebo důvod „no change“)
- qa: PASS/BAD
- handover: cesta + poslední pushed SHA + next
- pr: URL nebo důvod, proč PR do master tentokrát není
- restart (optional): health + version, pokud se spouštělo `/restart-service`
