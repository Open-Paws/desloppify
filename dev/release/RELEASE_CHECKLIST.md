# Release Checklist

Replace `CURRENT` with the version being released (e.g., `0.9.11`) and `NEXT` with the following version (e.g., `0.9.12`).

## Setup

The release branch should be named after the version (e.g., `0.9.11`). The version in `pyproject.toml` should match.

Create a GitHub label for the release:
```bash
gh label create "release:vCURRENT" --description "Included in vCURRENT" --color 1D76DB
```

Tag every issue and PR that lands during this cycle with `release:vCURRENT`.

---

## Pre-Merge Checklist

Complete these **before** merging the release branch into `main`:

- [ ] All changes committed and pushed to the release branch
- [ ] `make ci-fast` passes (lint, typecheck, arch contracts, tests)
- [ ] `make ci` passes if full validation needed (includes `tests-full` and `package-smoke`)
- [ ] Write release notes using the template in `dev/RELEASE_NOTES_TEMPLATE.md`
  - Reference past examples in `dev/release-notes-examples/` for tone and structure
- [ ] Release notes reviewed and saved to `dev/release-notes-drafts/vCURRENT.md`

---

## Merge & Release

- [ ] Merge release branch into `main`:
  ```bash
  git checkout main
  git merge CURRENT
  git push origin main
  ```
- [ ] Create the GitHub release with the release notes:
  ```bash
  gh release create vCURRENT --title "vCURRENT" --notes-file dev/release-notes-drafts/vCURRENT.md
  ```

---

## Post-Release Cleanup

After pushing to `main` and publishing the release:

- [ ] Find all issues/PRs tagged with this release and notify + close them:
  ```bash
  # Comment on and close all tagged issues
  gh issue list --label "release:vCURRENT" --state open --json number --jq '.[].number' | while read num; do
    gh issue comment "$num" --body "Released in vCURRENT — https://github.com/peteromallet/desloppify/releases/tag/vCURRENT"
    gh issue close "$num"
  done

  # Comment on tagged PRs (PRs usually auto-close, but comment for visibility)
  gh pr list --label "release:vCURRENT" --state all --json number --jq '.[].number' | while read num; do
    gh pr comment "$num" --body "Released in vCURRENT — https://github.com/peteromallet/desloppify/releases/tag/vCURRENT"
  done
  ```

- [ ] Create the next release branch, bump version, and clean up:
  ```bash
  # Create next branch from main
  git checkout main
  git checkout -b NEXT

  # Bump version in pyproject.toml
  sed -i '' 's/version = "CURRENT"/version = "NEXT"/' pyproject.toml

  # Commit and push the version bump
  git add pyproject.toml
  git commit -m "chore: bump version to NEXT"
  git push -u origin NEXT

  # Delete the old release branch locally and remotely
  git branch -d CURRENT
  git push origin --delete CURRENT
  ```

- [ ] Create the next release label:
  ```bash
  gh label create "release:vNEXT" --description "Included in vNEXT" --color 1D76DB
  ```
