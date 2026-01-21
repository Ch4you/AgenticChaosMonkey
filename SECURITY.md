## Security Policy

Thank you for helping keep AgenticChaosMonkey secure.

### Reporting a Vulnerability

Please **do not** open a public issue for security problems.

Email: `support@agent-chaos-platform.com`  
Subject: `SECURITY: <short description>`

Include:
- A clear description of the issue and impact
- Steps to reproduce
- Affected versions/commits
- Any mitigation you have tested

We aim to acknowledge reports within **3 business days** and provide a fix or mitigation plan within **14 days**.

### Supported Versions

We support the latest `main` branch and the most recent tagged release.

### Safe Testing

Use the mock server (`python -m agent_chaos_sdk.tools.mock_server`) or a dedicated test environment.  
Do not target production systems without explicit authorization.
