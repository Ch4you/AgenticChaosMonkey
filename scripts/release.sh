#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:-}"
if [[ -z "${VERSION}" ]]; then
  echo "Usage: ./scripts/release.sh v0.2.0"
  exit 1
fi

echo "==> Running tests"
pytest tests/unit -q
pytest tests/integration/test_sdk_middleware_langchain.py -q || true
pytest tests/integration/test_sdk_middleware_openai_responses.py -q

echo "==> Building package"
python -m build
twine check dist/*

echo "==> Tagging release ${VERSION}"
git tag "${VERSION}"
git push --tags

echo "==> Done. Create GitHub Release with .github/RELEASE_TEMPLATE.md"
