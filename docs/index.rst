Agent Chaos Platform Documentation
==================================

Welcome to the Agent Chaos Platform documentation!

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   quickstart
   api/index
   examples/index
   contributing
   changelog
   CONFIGURATION_REFERENCE
   OBSERVABILITY
   KUBERNETES

.. toctree::
   :maxdepth: 1
   :caption: Governance:

   ../SECURITY
   ../CODE_OF_CONDUCT
   ../SUPPORT
   ../VERSIONING

Introduction
------------

Agent Chaos Platform is a Universal Chaos Engineering SDK for AI Agents. 
It provides comprehensive tools for testing agent robustness against network failures, 
data corruption, protocol fuzzing, and race conditions.

Key Features
------------

* **Network Chaos**: Inject latency, errors, and data corruption
* **Protocol Fuzzing**: Schema-aware fuzzing for tool calls (MCP protocol)
* **Race Condition Detection (Heuristic)**: Detect tool-call ordering issues via scorecard analysis
* **Security & Compliance**: Audit logging, PII redaction, strict auth modes
* **Deterministic Replay**: Tape-based record/replay for flaky failures
* **Group-based Chaos**: Apply chaos to agents by role
* **Resilience Scorecard**: Automated analysis and reporting
* **Observability**: OpenTelemetry integration with Jaeger and Prometheus

Quick Start
-----------

.. code-block:: bash

   # Install
   pip install agentic-chaos-monkey

   # Run a chaos test
   agent-chaos run examples/plans/travel_agent_chaos.yaml --mock-server

For more details, see :doc:`quickstart`.

API Reference
-------------

The complete API reference is available in :doc:`api/index`.

Examples
--------

Check out our :doc:`examples/index` for usage examples.

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

