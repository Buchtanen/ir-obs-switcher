# QA: lint / format / type-check / tests

Spusť ověření kvality změn. Cíl je co nejvíc odpovídat CI a dát jasný PASS/BAD report.

## Postup
1) Zjisti co se měnilo (diff) a podle toho zvol rozsah testů.
2) Pusť lokální checky (preferuj existující repo skripty):
   - pokud existuje `run_tests.ps1` / `run_tests.sh`, použij je
   - jinak minimálně:
     - `python -m ruff check src tests`
     - `python -m black --check src tests`
     - `python -m mypy src` (pokud je dostupné)
     - `python -m pytest` (pokud je relevantní a dostupné)
3) Pokud něco chybí (např. ruff/black/mypy nejsou nainstalované), neinstaluj nové deps bez explicitního potvrzení.

## Výstup
- **pass**: příkazy, které prošly
- **bad**: co spadlo + 3–10 řádků erroru + návrh fixu
- **risks**: co nešlo ověřit (a proč) + mitigace

