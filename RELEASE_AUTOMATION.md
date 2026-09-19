# Automatizace Release Procesu

## Aktuální stav

### Kdo vytváří tag?
**Vývojář ručně** - tag se vytváří lokálně a pushne se do repozitáře:

```bash
git tag -a v0.7.0 -m "Release version 0.7.0"
git push origin v0.7.0
```

### Kdo spouští release?
**GitHub Actions automaticky** - release workflow se spustí při push tagu `v*`.

---

## Možnosti automatizace

### Varianta 1: Ruční tag (aktuální) ✅

**Výhody:**
- Plná kontrola nad tím, kdy se vytvoří release
- Možnost review před release
- Flexibilita - můžeš vytvořit tag kdykoliv

**Nevýhody:**
- Musíš si pamatovat vytvořit tag
- Riziko zapomenutí

**Workflow:**
```
1. Vývojář: git commit -m "feat: nová funkce"  # Verze se zvýší automaticky
2. Vývojář: Aktualizuje CHANGELOG.md
3. Vývojář: git commit -m "chore: update changelog"
4. Vývojář: git push
5. CI běží a ověří kód
6. Vývojář: git tag -a v0.8.0 -m "Release 0.8.0"
7. Vývojář: git push origin v0.8.0
8. GitHub Actions: Automaticky vytvoří release
```

---

### Varianta 2: Automatický tag při merge do main/master

**Jak to funguje:**
- Po úspěšném CI na main/master
- Pokud byla verze zvýšena (detekce změny v `pyproject.toml`)
- Automaticky vytvoří tag a pushne ho
- Spustí release workflow

**Výhody:**
- Plně automatické
- Žádné zapomenutí
- Release hned po merge

**Nevýhody:**
- Méně kontroly
- Release se vytvoří i pro malé změny
- Potřebuješ aktualizovat CHANGELOG před merge

**Workflow:**
```
1. Vývojář: git commit -m "feat: nová funkce"  # Verze se zvýší
2. Vývojář: Aktualizuje CHANGELOG.md
3. Vývojář: git commit -m "chore: update changelog"
4. Vývojář: git push (nebo PR merge)
5. CI běží a ověří kód
6. GitHub Actions: Detekuje změnu verze
7. GitHub Actions: Automaticky vytvoří tag v0.8.0
8. GitHub Actions: Pushne tag → spustí release workflow
9. GitHub Actions: Vytvoří release
```

---

### Varianta 3: Automatický tag jen pro patch verze

**Jak to funguje:**
- Automaticky pro PATCH (0.7.0 → 0.7.1) - bugfixy
- Ručně pro MINOR/MAJOR (0.7.0 → 0.8.0) - větší změny

**Výhody:**
- Automatické bugfix releases
- Ruční kontrola pro větší změny
- Kompromis mezi automatizací a kontrolou

**Workflow:**
```
PATCH (automaticky):
1. git commit -m "fix: oprava bugu"  # 0.7.0 → 0.7.1
2. git push
3. CI → automatický tag v0.7.1 → release

MINOR/MAJOR (ručně):
1. git commit -m "feat: nová funkce"  # 0.7.0 → 0.8.0
2. git push
3. CI běží
4. Vývojář: git tag -a v0.8.0 → release
```

---

### Varianta 4: GitHub Actions workflow pro vytvoření tagu

**Jak to funguje:**
- Workflow, který se spustí po úspěšném CI
- Vytvoří tag z aktuální verze v `pyproject.toml`
- Pushne tag → spustí release workflow

**Výhody:**
- Automatické, ale s možností kontroly
- Můžeš spustit manuálně (workflow_dispatch)
- Můžeš nastavit podmínky (jen na main/master)

---

## Doporučení

### Pro tento projekt: **Varianta 1 (ruční tag) + Varianta 4 (volitelná automatizace)**

**Důvody:**
1. **Kontrola** - chceš mít kontrolu nad tím, kdy se vytvoří release
2. **CHANGELOG** - musíš aktualizovat CHANGELOG.md před release
3. **Flexibilita** - můžeš vytvořit tag kdykoliv, i později

**Možné vylepšení:**
- Přidat workflow, který **navrhne** vytvoření tagu (notification)
- Nebo workflow, který vytvoří tag **po manuálním schválení** (workflow_dispatch)

---

## Implementace automatického tagu (Varianta 4)

### Workflow: `create-release-tag.yml`

```yaml
name: Create Release Tag

on:
  workflow_run:
    workflows: ["CI"]
    types:
      - completed
    branches: [main, master]
  workflow_dispatch:  # Manuální spuštění

jobs:
  create-tag:
    if: ${{ github.event.workflow_run.conclusion == 'success' || github.event_name == 'workflow_dispatch' }}
    runs-on: ubuntu-latest
    permissions:
      contents: write
    
    steps:
    - uses: actions/checkout@v4
      with:
        fetch-depth: 0
        token: ${{ secrets.GITHUB_TOKEN }}
    
    - name: Get current version
      id: version
      run: |
        version=$(python -c "import tomllib; f=open('pyproject.toml','rb'); d=tomllib.load(f); print(d['project']['version'])")
        echo "version=$version" >> $GITHUB_OUTPUT
        echo "Current version: $version"
    
    - name: Check if tag exists
      id: check-tag
      run: |
        if git rev-parse "v${{ steps.version.outputs.version }}" >/dev/null 2>&1; then
          echo "exists=true" >> $GITHUB_OUTPUT
          echo "Tag v${{ steps.version.outputs.version }} already exists"
        else
          echo "exists=false" >> $GITHUB_OUTPUT
          echo "Tag v${{ steps.version.outputs.version }} does not exist"
        fi
    
    - name: Create and push tag
      if: steps.check-tag.outputs.exists == 'false'
      run: |
        git config user.name "github-actions[bot]"
        git config user.email "github-actions[bot]@users.noreply.github.com"
        git tag -a "v${{ steps.version.outputs.version }}" -m "Release version ${{ steps.version.outputs.version }}"
        git push origin "v${{ steps.version.outputs.version }}"
```

**Použití:**
- Automaticky se spustí po úspěšném CI na main/master
- Nebo manuálně přes GitHub Actions UI
- Vytvoří tag z aktuální verze v `pyproject.toml`
- Pushne tag → spustí release workflow

---

## Shrnutí

### Aktuální proces:
1. ✅ Vývojář vytvoří tag ručně
2. ✅ Pushne tag
3. ✅ GitHub Actions automaticky vytvoří release

### Možné vylepšení:
1. ⚠️ Automatický tag po úspěšném CI (volitelné)
2. ⚠️ Notification, když je připraveno k release
3. ⚠️ Workflow pro manuální vytvoření tagu z UI

### Doporučení:
- **Zachovat ruční proces** - dává kontrolu
- **Přidat workflow pro manuální vytvoření tagu** - usnadní proces
- **Možnost automatického tagu** - pro ty, co chtějí plnou automatizaci
