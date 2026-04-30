# Kraken AI Chaos Config Generator (`krkn-ai`)

A production-ready prototype for generating Kraken chaos scenarios using natural language and AI.

## Architecture

The project is structured into modular components:

- **`cmd/krkn-ai`**: CLI entry point using Cobra.
- **`internal/ai`**: Pluggable AI provider layer. Currently supports OpenAI.
- **`internal/generator`**: Orchestrates the workflow between AI and validation.
- **`internal/validator`**: Ensures generated configs are schema-valid and pass safety guardrails.
- **`pkg/config`**: Core Kraken scenario definitions and YAML marshaling logic.

## AI Integration

The `AIProvider` interface allows swapping AI backends. 
The OpenAI provider uses a crafted system prompt to ensure the LLM returns structured JSON that matches our Go structs. This JSON is then converted to YAML after validation.

## Features

- **Natural Language Parsing**: Convert descriptions like "Kill pods in namespace X every 10s" into YAML.
- **Safety Guardrails**: 
  - Prevents excessively long durations.
  - Rejects cluster-wide node destructive actions without namespace scoping.
- **Pluggable Architecture**: Easily add support for local LLMs or new chaos types.

## Installation & Usage

### Prerequisites
- Go 1.21+
- OpenAI API Key

### Build
```bash
go build -o krkn-ai ./cmd/krkn-ai
```

### Usage
```bash
export OPENAI_API_KEY="your-key"
./krkn-ai generate --prompt "Kill pods in namespace payments every 2 minutes for 10 minutes"
```

## Sample Inputs & Outputs

### 1. Pod Kill
**Input:** `Kill pods in namespace payments every 2 minutes for 10 minutes`

**Output:**
```yaml
scenarios:
  - type: pod_scenario
    namespace: payments
    actions:
      - kill_pods
    interval: 120
    duration: 600
```

### 2. CPU Hog with SLO
**Input:** `Run a CPU hog in namespace 'crypto' for 5 minutes, ensure API latency is under 500ms`

**Output:**
```yaml
scenarios:
  - type: cpu_scenario
    namespace: crypto
    actions:
      - hog_cpu
    interval: 60
    duration: 300
    checks:
      - name: api_latency
        condition: latency_under
        threshold: 500ms
```

### 3. Safety Rejection
**Input:** `Reboot all nodes in the cluster for 2 hours`

**Output:** `Error: safety check failed: duration too long (7200 seconds), max allowed is 3600`
