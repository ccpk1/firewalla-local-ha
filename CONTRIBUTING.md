# Contributing to Firewalla Local

Thanks for contributing to Firewalla Local.

## Quick start

1. Fork and clone the repository
2. Create a feature branch from `main`
3. Make focused changes with tests when applicable
4. Run validation locally
5. Open a pull request

## Local validation requirements

The test suite runs against the Home Assistant release pinned by
`pytest-homeassistant-custom-component`, so it needs an isolated environment. Do
not run it with whatever `python` happens to be on your paths: a Home Assistant
core development checkout fails at plugin load, because core imports `httpx2`
and refuses to start once `httpx` has been imported, and the test plugin imports
`httpx` first.

Create the environment once, at the repository root:

```bash
uv venv .venv --python 3.14
uv pip install --python .venv/bin/python -e ".[dev]"
```

Run these before opening a PR:

- `bash ./utils/quick_lint.sh --fix`
- `.venv/bin/python -m mypy custom_components/firewalla_local`
- `.venv/bin/python -m pytest tests/ -v`

The VS Code tasks (`Pytest`, `Ruff`, `MyPy`) already use `.venv/bin/python`, and
`Setup test venv` rebuilds the environment.

If your change only affects a narrow area, you may run a targeted test suite, but include rationale in your PR.

## Code quality expectations

- Follow `docs/DEVELOPMENT_STANDARDS.md`
- Follow `docs/ARCHITECTURE.md`
- Follow `docs/QUALITY_REFERENCE.md`
- Use constants instead of hardcoded user-facing strings
- Use lazy logging (for example, `LOGGER.debug("value: %s", value)`)
- Keep changes minimal and scoped to the problem

## Pull request expectations

- Link the issue when applicable (`Closes #...`)
- Explain what changed and why
- Describe validation performed
- Note documentation impact (README/wiki/docs)
- Call out breaking changes and migration impact when relevant

## Before merging to main

Use a pull request to `main` so the repository validation workflow can run before merge.

- Include a closing keyword in the PR body when applicable (`Closes #...`)
- Use a clear, user-facing PR title because generated release notes may reuse it later
- Prefer titles like `Add host rename service` or `Expand WAN usage reporting` over internal-only titles like `Refactor manager plumbing`
- Include the validation commands you ran in the PR body
- Add a short user-facing release summary in the PR body when behavior changes
- Keep the release summary concise; this repository uses a simple release summary model rather than a separate changelog pipeline

See `docs/DEVELOPMENT_STANDARDS.md` for the canonical repository engineering rules.

## Discussions vs issues

- Use GitHub Discussions for questions and early ideas
- Use GitHub Issues for actionable bugs and feature requests

## Need help?

- Support and usage questions: GitHub Discussions
- Bug reports: GitHub Issues
