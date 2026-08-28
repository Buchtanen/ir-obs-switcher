# Parallel plan

Rozděl backlog na nezávislé úkoly před spuštěním více agentů / worktrees.

## Pravidla
- Hosting je **GitHub** (`Buchtanen/ir-obs-switcher`), ne GitLab.
- Paralelně jen to, co nesdílí soubory a nemá společný state machine / API kontrakt.
- Každý úkol: vlastní větev + vlastní issue (AC / test plan / docs impact).
- Překryv → sekvenčně, ne „10 agentů a stash“.

## Postup
1) Vypiš kandidáty (1 řádek: cíl + hlavní soubory).
2) Seskup overlapping do jednoho streamu.
3) Pro každý nezávislý stream:
   - branch name podle `05-git-branching-convention.mdc`
   - worktree (ne ruční checkout na `master`)
   - issue number, pokud už existuje, jinak `/ensure-issue`
4) Nespouštěj agenty, dokud uživatel neschválí plán (kód bez schválení neměnit).

## Výstup
- **sequential**: seznam (závislosti)
- **parallel**: seznam (branch + files + issue)
- **skip**: co nechat (např. OBS plugin)
