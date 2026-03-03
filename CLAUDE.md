## Comments and docs

- **Keep** existing docstrings/JSDoc — only remove if clearly stale or wrong.
- **Don't add** new docs to code you didn't write — unless matching an existing codebase pattern.

## Backward compatibility policy

- **No backward compatibility for import paths or APIs.** This is an internal tool, not a library. Remove re-export facades, wrapper shims, and compatibility layers that exist solely so old import paths keep working.
- **Keep data migration code.** Any code that converts existing `.desloppify/` state/plan JSON data from old formats to new formats must be preserved to keep data accurate.
- In short: keep what's needed for data integrity, remove what assumes external consumers.
