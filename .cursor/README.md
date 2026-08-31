## Cursor automation (repo-local)

Rules, commands, agents a skills **jsou v gitu**. Lokální opt-in:
- `.cursor/hooks.json` (gitignored) — kopie z `hooks.example.json`

### Co je zapnuté defaultně
- **Subagenti**: `.cursor/agents/`
- **Commands**: `.cursor/commands/`
- **Skills**: `.cursor/skills/`
- **Rules**: `.cursor/rules/`
- **Hooks**: defaultně **vypnuté** (viz níže)

### Proč jsou hooks vypnuté
Na Windows Cursor často spouští hook skripty přes PowerShell a posílá hook input jako base64 JSON.
Microsoft Defender/AV to někdy vyhodnotí jako „škodlivý příkazový řádek“ a zablokuje.

Proto je `.cursor/hooks.json` **gitignored** (lokální opt-in). V repu je jen template:
- `.cursor/hooks.example.json`

### Jak hooks zapnout (opt-in)
1) Zkopíruj `.cursor/hooks.example.json` → `.cursor/hooks.json`
2) Pokud Defender blokuje, řeš to lokálně:
   - buď přidej výjimku pro repo/skripty (podle interní policy),
   - nebo hooks nepoužívej (kvalitu pokrývá `/qa` + lokální git hooky v `scripts/`).

### Dokumentace kódu (před grepem **a** po změně)
- `docs/dokumentace/README.md` — mapa domén a lookup
- `docs/dokumentace/inflight/` — otevřené PR, které ještě nejsou na `master`
- Rule: `.cursor/rules/09-dokumentace-index.mdc` (always apply) — číst **i aktualizovat**
- Skill: `.cursor/skills/dokumentace/SKILL.md` — handover checklist
- `/flow` → `/docs-keeper` musí vzít `docs/dokumentace/` (nebo `Docs: no change (reason …)`)
- Cursor **stop hook** `dokumentace_handover.py` — reminder když `src/` změněný a index ne; jen při opt-in hooks (Windows default off, viz výše)

### Skills
- `dokumentace` — údržba `docs/dokumentace/` po každé změně `src/irswitch/`
- `pr-semver-label` — povinný `semver:*` label na každý PR do `master`
- `restart-irswitch` — start/stop/restart služby, port 17321, SSLKEYLOGFILE, `/health`
- `youtube-oauth` — volitelný YouTube title (ne scene switch)
- `iracing-sdk-display-format` — iRSDK jednotky, sentinely (`-1`, 32767) a HUD formát časů (`m:ss.fff`)
- `subagents` — kdy spouštět Task subagenty vs práci v parentovi; `/flow` typy a worktrees

### Doporučené workflow
- `/flow` → provede celý proces (issue → diary → docs → QA → PR popis)
- `/ensure-issue` → vytvoří/najde issue pro větev
- `/dev-diary` → zapíše průběh do issue
- `/docs-impact` → zkontroluje a doplní docs podle změn
- `/qa` → ověří lint/format/type-check/tests
- `/pr-description` → připraví PR popis podle policy
- `/restart-service` → start/stop/restart + ověření health/verze
- `/parallel-plan` → rozdělí nezávislé úkoly před worktrees / více agenty

