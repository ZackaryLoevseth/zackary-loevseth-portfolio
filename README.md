# Zackary Loevseth — Professional Portfolio

This repository contains Zackary Loevseth’s professional portfolio. The page presents work and experience in AI evaluation, security research, geospatial analysis, and climate data, with an emphasis on reproducible methods and traceable evidence.

Live site: https://hayosoai.github.io/zackary-loevseth-portfolio/

## Files

| File | Role |
| --- | --- |
| `.nojekyll` | Empty marker file at the Pages site root. |
| `index.html` | Portfolio page content and structure; loads `styles.css` and `script.js`. |
| `styles.css` | Page layout, visual styling, and responsive presentation. |
| `script.js` | Updates the displayed year, header state, reveal animations, active section navigation, and disclosure accessibility state. |

## Validation and limitations

- `git ls-files --error-unmatch .nojekyll index.html styles.css script.js && test "$(git ls-files | wc -l)" -eq 4` — passed before this README was added; confirmed the four existing source files.
- `node --check script.js` — passed.
- `git diff --check` and `git diff --cached --check` — passed.
- The tracked repository has no build or test configuration, so no automated build or test suite is available here.
