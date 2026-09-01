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

### Skills
Canonical path: **`.cursor/skills/`**. `.agents/skills/` jsou jen command wrappery / kopie — nové skilly tam neduplikuj.

- `pr-semver-label` — povinný `semver:*` label; po failu `gh run rerun`, ne empty commit
- `restart-irswitch` — start/stop/restart služby, port 17321, SSLKEYLOGFILE, `/health`, overlay cache bump (`?v=` / OBS CEF)
- `youtube-oauth` — volitelný YouTube title (ne scene switch)
- `iracing-sdk-display-format` — iRSDK jednotky, sentinely (`-1`, 32767) a HUD formát časů (`m:ss.fff`)
- `iracing-session-glossary` — session vs stream vs weekend vs `DrivingMode.RACE` vs `overlay_mode`; jeden extract path; nikdy `WeekendInfo.EventType`
- `overlay-hud-copy` — HUD tokeny v `overlay/i18n.py`; golden ≠ live OBS
- `overlay-tape-triage` — diagnostika z `recordings/overlay-*.jsonl` před `irswitch.log`
- `subagents` — kdy spouštět Task subagenty vs práci v parentovi; HUD soubory jen sekvenčně

### Doporučené workflow
- `/hotfix` → repro → minimální diff → test → restart (bez issue/PR)
- `/flow` → issue → diary → docs → QA → PR popis
- `/ensure-issue` → vytvoří/najde issue pro větev
- `/dev-diary` → zapíše průběh do issue
- `/docs-impact` → zkontroluje a doplní docs podle změn
- `/qa` → lint/test + overlay `?v=` lockstep když se měnil HUD
- `/pr-description` → připraví PR popis podle policy
- `/restart-service` → start/stop/restart + ověření health/verze + cache bump
- `/parallel-plan` → rozdělí nezávislé úkoly před worktrees / více agenty

