# Docs impact (update required docs)

Vyhodnoť dopad změn na dokumentaci a udělej minimální update relevantních `.md` souborů.

Nejdřív `docs/dokumentace/README.md` + matching `domeny/*.md`. Grep `src/` není první krok.

## Postup
1) Z diffu určete typ změn:
   - runtime chování / config / API / overlay / build / release / CI / docs-only
2) Podle `docs-map.mdc` + skill `dokumentace` vypiš, které docs jsou relevantní (včetně domain page).
3) Udělej update (docs-keeper to **musí zapsat**, ne jen navrhnout):
   - krátce, přesně, copy-paste-friendly snippety
   - když se docs nemění: explicitně napiš „Docs: no change (reason …)“

## Výstup
- **Updated docs**: seznam souborů
- **Pending docs**: seznam souborů + co doplnit
- **Lookup**: stačí `docs/dokumentace/`? ano/ne (když ne, pending musí obsahovat doplnění indexu)
- **Notes**: proč / `Docs: no change (reason …)`

