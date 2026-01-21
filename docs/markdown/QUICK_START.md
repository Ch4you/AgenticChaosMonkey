# Quick Start (Standard Flow)

This project has **one standard way to run**. Follow the steps below.

## Prerequisites

- Python 3.10+
- [Ollama](https://ollama.ai/) running locally
- [mitmproxy](https://mitmproxy.org/) installed

## Install

```bash
pip install -e .
```

## Standard Run

### 1) Start the platform

```bash
agent-chaos run examples/plans/travel_agent_chaos_validate.yaml --mock-server --repeat 10
```

### 2) Route agent traffic through the proxy

```bash
export HTTP_PROXY=http://localhost:8080
export HTTPS_PROXY=http://localhost:8080
```

### 3) Run the demo agent

```bash
python examples/production_simulation/travel_agent.py \
  --query "Book a flight from New York to Los Angeles on December 25th, 2025"
```

## Results

- Dashboard: `http://127.0.0.1:8081`
- Report: `runs/<latest>/reports/compliance_audit_report.md`

Stop the experiment with `Ctrl+C`.
