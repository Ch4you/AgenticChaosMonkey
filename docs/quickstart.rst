Quick Start Guide
=================

This guide will help you get started with Agent Chaos Platform in minutes.

Installation
------------

.. code-block:: bash

   pip install agentic-chaos-monkey

Or install from source:

.. code-block:: bash

   git clone https://github.com/AgenticChaosMonkey/AgenticChaosMonkey.git
   cd AgenticChaosMonkey
   pip install -e .

Basic Usage
-----------

Run a complete chaos test:

.. code-block:: bash

   ./scripts/run_chaos_test.sh

This will:
1. Start the Mock Server
2. Start the Chaos Proxy
3. Run the Travel Agent test
4. Generate a Resilience Scorecard report

Using the CLI
-------------

Initialize a new chaos plan:

.. code-block:: bash

   agent-chaos init

Validate a chaos plan:

.. code-block:: bash

   agent-chaos validate examples/plans/travel_agent_chaos.yaml

Run an experiment:

.. code-block:: bash

   agent-chaos run examples/plans/travel_agent_chaos.yaml --mock-server

Strict Modes (Recommended for Production)
----------------------------------------

Agent Chaos supports strict validation to prevent silent misconfiguration. These are
controlled by environment variables:

* ``CHAOS_CLASSIFIER_STRICT=true``: Requires ``classifier_rule_packs`` in the chaos plan.
  If missing, startup fails with a clear error.
* ``CHAOS_REPLAY_STRICT=true``: Enforces JSONPath masking rules for replay (no best-effort fallback).
* ``CHAOS_JWT_STRICT=true``: If JWT auth is configured, ``pyjwt`` must be installed or startup fails.

Example strict-ready plan snippet:

.. code-block:: yaml

   version: "1.0"
   metadata:
     name: "Prod Ready Plan"
   classifier_rule_packs:
     - name: "default"
       rules:
         llm_patterns:
           - ".*openai\\.com.*/v1/(chat|completions|embeddings)"
         tool_patterns:
           - ".*localhost:8001/.*"
         agent_patterns:
           - ".*agent-[a-z0-9]+.*"
   replay_config:
     ignore_paths:
       - "$.timestamp"
       - "$.request_id"
     ignore_params:
       - "trace_id"

For full schema details and defaults, see :doc:`CONFIGURATION_REFERENCE`.

Python API
----------

Use the decorator for function-level chaos:

.. code-block:: python

   from agent_chaos_sdk.decorators import simulate_chaos

   @simulate_chaos(strategy="latency", probability=0.5, delay=2.0)
   def my_agent_function():
       # This function may be delayed
       pass

Load a chaos plan:

.. code-block:: python

   from agent_chaos_sdk.config_loader import load_chaos_plan

   plan = load_chaos_plan("examples/plans/travel_agent_chaos.yaml")
   print(f"Loaded plan: {plan.metadata.name}")

Next Steps
----------

* Read the :doc:`api/index` for detailed API documentation
* Check out :doc:`examples/index` for more examples
* See :doc:`contributing` to contribute to the project

