## Qwen Code Overlay

Qwen Code loads skills from `.qwen/skills/<name>/SKILL.md` in a project or `~/.qwen/skills/<name>/SKILL.md` globally.

Install the project skill with:

```bash
desloppify update-skill qwen
```

Install the global skill with:

```bash
desloppify setup --interface qwen
```

Use the standard review workflow from the base skill. Automated `--runner qwen` batch reviews are not implemented yet; use the prepared packet/manual import workflow or another supported batch runner.

<!-- desloppify-overlay: qwen -->
<!-- desloppify-end -->
