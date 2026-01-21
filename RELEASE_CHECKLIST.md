# Release Checklist (v0.2.x)

## Pre-release
- [ ] Version bumped in `agent_chaos_sdk/__init__.py`
- [ ] `CHANGELOG.md` updated with release notes
- [ ] `VERSIONING.md` references the new release
- [ ] README version banner updated

## Test Matrix
- [ ] `pytest tests/unit -q`
- [ ] `pytest tests/integration/test_sdk_middleware_langchain.py -q`
- [ ] `pytest tests/integration/test_sdk_middleware_openai_responses.py -q`

## Artifacts
- [ ] SDK tape viewer sanity check: `python scripts/tape_viewer.py tapes/sdk_*.tape --tail 2`
- [ ] `compliance_audit_report.md` generated in reports

## Publish
- [ ] Build package: `python -m build`
- [ ] Validate dist: `twine check dist/*`
- [ ] Ensure `PYPI_API_TOKEN` is set in GitHub Actions secrets
- [ ] Tag release: `git tag v0.2.x`
- [ ] Push tags: `git push --tags`
- [ ] Create GitHub release notes
