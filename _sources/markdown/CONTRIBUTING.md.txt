# Contributing to Agent Chaos Platform

First off, thank you for considering contributing to Agent Chaos Platform! 🎉

This document provides guidelines and instructions for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How Can I Contribute?](#how-can-i-contribute)
- [Development Setup](#development-setup)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Documentation](#documentation)
- [Pull Request Process](#pull-request-process)

## Code of Conduct

By participating in this project, you are expected to uphold our Code of Conduct:
- Be respectful and inclusive
- Welcome newcomers and help them learn
- Focus on constructive feedback

## How Can I Contribute?

### Reporting Bugs

Before creating bug reports, please check the issue list to see if the bug has already been reported.

When creating a bug report, include:
- Clear title and description
- Steps to reproduce
- Expected vs actual behavior
- Environment details (OS, Python version, etc.)
- Relevant logs or error messages

### Suggesting Enhancements

Enhancement suggestions are tracked as GitHub issues. When creating an enhancement suggestion:
- Use a clear and descriptive title
- Provide a detailed description
- Explain why this enhancement would be useful
- List any alternative solutions you've considered

### Pull Requests

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests for your changes
5. Ensure all tests pass
6. Update documentation if needed
7. Commit your changes (`git commit -m 'Add some amazing feature'`)
8. Push to the branch (`git push origin feature/amazing-feature`)
9. Open a Pull Request

## Development Setup

### Prerequisites

- Python 3.10 or higher
- Git
- (Optional) Docker for running observability stack

### Installation

```bash
# Clone the repository
git clone https://github.com/AgenticChaosMonkey/AgenticChaosMonkey.git
cd AgenticChaosMonkey

# Create a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install development dependencies (uses pyproject.toml)
pip install -e ".[dev]"

# Verify installation
pytest tests/ -v
```

**Note**: The project now uses `pyproject.toml` as the primary configuration file. The `setup.py` file is kept for backward compatibility.

## Coding Standards

### Python Style Guide

We follow [PEP 8](https://www.python.org/dev/peps/pep-0008/) with some modifications:

- Maximum line length: 100 characters
- Use type hints for all function signatures
- Use docstrings for all public functions/classes (Google style)
- Prefer f-strings over .format() or %

### Type Hints

Always use type hints:

```python
from typing import List, Optional, Dict

def process_items(items: List[str], config: Optional[Dict[str, str]] = None) -> bool:
    """Process a list of items."""
    pass
```

### Code Formatting

We use `black` for code formatting (coming soon). Currently, please follow:
- 4 spaces for indentation
- No trailing whitespace
- Consistent quote style (prefer double quotes)

### Docstrings

Use Google-style docstrings:

```python
def calculate_score(metrics: Dict[str, float]) -> float:
    """Calculate resilience score from metrics.
    
    Args:
        metrics: Dictionary of metric names to values
        
    Returns:
        Calculated resilience score (0-100)
        
    Raises:
        ValueError: If metrics dictionary is empty
    """
    pass
```

## Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=agent_chaos_sdk --cov-report=html

# Run specific test file
pytest tests/unit/test_security.py

# Run with verbose output
pytest -v
```

### Writing Tests

- Write tests for all new features
- Aim for >80% code coverage
- Use descriptive test names: `test_function_should_do_something_when_condition`
- Use fixtures for common setup
- Mock external dependencies

Example:

```python
import pytest
from agent_chaos_sdk.proxy.strategies.network import LatencyStrategy

@pytest.mark.asyncio
async def test_latency_strategy_applies_delay(mock_flow):
    """Test that latency strategy applies delay correctly."""
    strategy = LatencyStrategy(name="test", enabled=True, delay=1.0)
    await strategy.intercept(mock_flow)
    # Assertions...
```

## Documentation

### Code Documentation

- All public functions/classes need docstrings
- Use type hints for better IDE support
- Add comments for complex logic

### User Documentation

When adding features:
- Update README.md if it affects user-facing functionality
- Add examples to QUICK_START.md if relevant
- Update docstrings with usage examples

### API Documentation

API documentation is generated from docstrings. Ensure they are:
- Clear and concise
- Include parameter descriptions
- Include return value descriptions
- Include usage examples for complex functions

## Pull Request Process

### Before Submitting

1. **Update tests**: Add tests for new functionality
2. **Run tests**: Ensure all tests pass (`pytest`)
3. **Check type hints**: Run `mypy agent_chaos_sdk/` (optional, but recommended)
4. **Update documentation**: Update relevant docs
5. **Update CHANGELOG.md**: Add entry for your changes

### PR Checklist

- [ ] Code follows style guidelines
- [ ] Tests added/updated and passing
- [ ] Documentation updated
- [ ] CHANGELOG.md updated
- [ ] Type hints added
- [ ] No merge conflicts

### Review Process

1. A maintainer will review your PR
2. Address any review comments
3. Once approved, a maintainer will merge

## Adding New Chaos Strategies

1. Create a new file in `agent_chaos_sdk/proxy/strategies/`
2. Inherit from `BaseStrategy`
3. Implement `async def intercept(self, flow)` method
4. Register in `agent_chaos_sdk/proxy/addon.py` in `StrategyFactory`
5. Add tests in `tests/unit/`
6. Update documentation

Example:

```python
from agent_chaos_sdk.proxy.strategies.base import BaseStrategy
from mitmproxy import http

class MyChaosStrategy(BaseStrategy):
    """My custom chaos strategy."""
    
    async def intercept(self, flow: http.HTTPFlow) -> None:
        """Apply chaos to the flow."""
        # Your chaos logic here
        pass
```

## Questions?

Feel free to:
- Open an issue for questions
- Ask in discussions
- Reach out to maintainers

Thank you for contributing! 🚀

