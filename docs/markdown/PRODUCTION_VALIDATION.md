# Production Validation Checklist

Use this guide to validate **local**, **Kubernetes**, and **CI** readiness.

---

## 1) Local Validation (Developer Machine)

### Prereqs
- Python 3.10+
- `mitmproxy` installed

### Steps
```bash
pip install -e .
agent-chaos health-check --plan examples/plans/travel_agent_chaos.yaml --mode live

# Core functional flow
agent-chaos run examples/plans/travel_agent_chaos.yaml --mock-server
```

In a second terminal:
```bash
export HTTP_PROXY=http://localhost:8080
export HTTPS_PROXY=http://localhost:8080
python examples/production_simulation/travel_agent.py --query "Book a flight from New York to Los Angeles"
```

Pass criteria:
- Dashboard loads: `http://127.0.0.1:8081`
- Report generated: `reports/resilience_report.md`

---

## 2) Kubernetes Validation (Cluster)

```bash
kubectl apply -f k8s/
kubectl rollout status deployment/agent-app
kubectl logs deployment/agent-app -c agent-chaos
```

Pass criteria:
- Pod is `Ready`
- Sidecar logs show proxy running
- App traffic routes through proxy (see chaos logs)

See full guide: `docs/KUBERNETES.md`.

---

## 3) CI Validation (Automated)

```bash
python -m pip install -e .[dev]
agent-chaos health-check --plan examples/plans/travel_agent_chaos.yaml --mode live
pytest
```

Pass criteria:
- Health-check passes
- Test suite passes

