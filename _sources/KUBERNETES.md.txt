# Kubernetes Deployment Guide

This guide shows how to run Agent Chaos as a **sidecar** in Kubernetes.

## Quick Start

```bash
kubectl apply -f k8s/
```

This creates:
- A ConfigMap with `chaos_plan.yaml`
- A Deployment with your app + `agent-chaos` sidecar
- A Service exposing the app

## How It Works

The deployment runs two containers:
- **agent-app**: Your agent or service.
- **agent-chaos**: Sidecar running `agent-chaos run /etc/agent-chaos/chaos_plan.yaml`.

The app container uses the sidecar as an HTTP/HTTPS proxy:

```yaml
env:
  - name: HTTP_PROXY
    value: "http://localhost:8080"
  - name: HTTPS_PROXY
    value: "http://localhost:8080"
  - name: NO_PROXY
    value: "localhost,127.0.0.1"
```

## Customize the Chaos Plan

Edit `k8s/configmap.yaml` and update the embedded plan:

```yaml
data:
  chaos_plan.yaml: |
    version: "1.0"
    revision: 1
    metadata:
      name: "k8s-sidecar-demo"
      experiment_id: "k8s-demo"
    targets:
      - name: "agent_api"
        type: "http_endpoint"
        pattern: "http://agent-app:8000/.*"
    scenarios:
      - name: "latency_injection"
        type: "latency"
        target_ref: "agent_api"
        enabled: true
        probability: 0.3
        params:
          delay: 0.25
```

Apply changes:

```bash
kubectl apply -f k8s/configmap.yaml
kubectl rollout restart deployment/agent-app
```

## Image References

Update the Deployment images to your own:

```yaml
containers:
  - name: agent-app
    image: your-org/agent-app:latest
  - name: agent-chaos
    image: agentic-chaos-monkey:latest
```

If you publish `agent-chaos` under a different name, replace it here.

## Troubleshooting

Check logs:

```bash
kubectl logs deployment/agent-app -c agent-chaos
kubectl logs deployment/agent-app -c agent-app
```

Verify sidecar is running:

```bash
kubectl describe pod -l app=agent-app
```
