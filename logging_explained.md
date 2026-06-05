# 🪵 How Logging Works in Our Project
### Python Logger + OpenTelemetry — A Complete Breakdown

---

## 🧩 The Two Worlds of Logging

There are **two completely separate logging systems** involved here:

| System | What it is | Your role |
|--------|-----------|-----------|
| **Python `logging` module** | Built into Python. You call `logger.info()`. Records stay in memory. | You write `logger.info(...)` calls in your code |
| **OpenTelemetry logging** | A separate system that knows how to *ship* logs to external backends | You configure it once in `setup_otel_logging()` |

The magic happens when **OTel intercepts Python's logging** — so your `logger.info()` calls automatically flow into OTel's pipeline without you doing anything extra.

---

## 📍 Part 1 — Python Logger (`nodes.py`)

### What you wrote:
```python
# arithmetic_agent/nodes.py — Line 1-16

import logging

logger = logging.getLogger(__name__)
#                           ↑
#                    __name__ = "arithmetic_agent.nodes"
#                    (the full module path becomes the logger name)
```

### What `logging.getLogger(__name__)` does:

Python has a **hierarchy of loggers** — like a tree:

```
root logger  (the trunk)
    │
    └── arithmetic_agent  (a branch)
            │
            └── arithmetic_agent.nodes  (a leaf) ← your logger
```

- `getLogger("arithmetic_agent.nodes")` creates (or retrieves) a logger at that specific position in the tree.
- If it doesn't exist yet, Python creates it with **no handlers** and **no level** (inherits from parent).
- The dot notation (`.`) defines the hierarchy — `arithmetic_agent.nodes` is a child of `arithmetic_agent`.

### When you call `logger.info(...)`:

```python
logger.info(
    "Orchestrator decision: multiply",   # ← the message (appears as "body" in OpenObserve)
    extra={                              # ← structured key-value data
        "action": "multiply",
        "action_input": parsed,
    },
)
```

Python creates a **LogRecord** object containing:
- The message string
- The `extra` fields as additional attributes
- Automatic metadata: timestamp, module name, line number, level

**Nothing is sent anywhere yet.** The record just exists in memory.

---

## 📍 Part 2 — The OTel Setup (`main.py`)

This is where you configure **what happens to those LogRecords**.

### Line by line:

```python
from opentelemetry.sdk.resources import Resource
```
`Resource` is a metadata container — it holds static information about your app that gets attached to EVERY log record automatically. Think of it as a permanent label on a box.

---

```python
from opentelemetry.sdk._logs import LoggerProvider
```
`LoggerProvider` is the **central manager** of OTel's logging system. It owns the pipeline: receives records → processes them → exports them.

---

```python
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
```
A **processor** sits between receiving a record and exporting it. `BatchLogRecordProcessor` specifically:
- Collects records into a buffer
- Flushes (sends) the buffer every **5 seconds** OR when it hits **512 records**
- Whichever comes first

---

```python
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
```
The **exporter** is the delivery truck. It takes a batch of records and sends them via **gRPC** (a fast binary protocol) to the Collector on port `4317`.

---

```python
from opentelemetry._logs import set_logger_provider
```
A global setter — registers your LoggerProvider as THE provider for the entire Python process.

---

```python
from opentelemetry.instrumentation.logging import LoggingInstrumentor
```
The **bridge** — the most important import. This is what connects Python's `logging` module to OTel's pipeline.

---

### Inside `setup_otel_logging()`:

```python
resource = Resource.create({"service.name": "arithmetic-orchestrator"})
```
Creates a resource that says: *"Every log from this process belongs to the service called 'arithmetic-orchestrator'"*. This becomes a field in OpenObserve.

---

```python
exporter = OTLPLogExporter(
    endpoint="http://localhost:4317",
    insecure=True,
)
```
Configures the delivery truck:
- `endpoint`: send to `localhost:4317` (your running OTel Collector)
- `insecure=True`: skip TLS/HTTPS since we're on localhost

---

```python
provider = LoggerProvider(resource=resource)
provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
```
Wires the pipeline together:
```
LoggerProvider
    └── BatchLogRecordProcessor
            └── OTLPLogExporter → localhost:4317
```

---

```python
set_logger_provider(provider)
```
Registers this provider **globally**. Now the OTel system knows where to route log records when they arrive.

---

```python
LoggingInstrumentor().instrument(set_logging_format=True)
```
This is the **magic line**. Here's exactly what it does:

1. Creates an `OTelLoggingHandler` — a Python `logging.Handler` that forwards records into the OTel pipeline
2. Attaches it to the **root logger** (the trunk of the tree)
3. With `set_logging_format=True`: also modifies the log format string to include OTel fields like `trace_id`

After this line, every log record that propagates up to the root logger gets intercepted by this handler.

---

## 📍 Part 3 — The Full Flow (end to end)

```
nodes.py:
    logger.info("Orchestrator decision: multiply", extra={...})
         │
         ▼
Python creates a LogRecord
    {
      message: "Orchestrator decision: multiply",
      name: "arithmetic_agent.nodes",
      level: INFO,
      extra: {action: "multiply", ...},
      timestamp: 2026-06-05T...,
      lineno: 127,
    }
         │
         ▼
LogRecord propagates UP the logger hierarchy:
    arithmetic_agent.nodes → arithmetic_agent → root logger
         │
         ▼
Root logger has OTelLoggingHandler (installed by LoggingInstrumentor)
    OTelLoggingHandler.emit(record) is called
         │
         ▼
OTelLoggingHandler converts Python LogRecord → OTel LogRecord
    Adds: service.name, trace_id, resource attributes
         │
         ▼
LogRecord enters the LoggerProvider pipeline
         │
         ▼
BatchLogRecordProcessor receives it
    Adds to internal buffer
    After 5 seconds (or 512 records)...
         │
         ▼
OTLPLogExporter.export(batch) called
    Serializes records to protobuf binary format
    Sends via gRPC to localhost:4317
         │
         ▼
OTel Collector receives on port 4317
    batch processor groups records
         │
         ▼
otlphttp exporter sends to OpenObserve
    HTTP POST to localhost:5080/api/default/v1/logs
         │
         ▼
OpenObserve stores the log
    Each `extra={}` field becomes a searchable column
    Visible in the Logs tab under stream "default"
```

---

## 📍 Part 4 — Why `extra={}` Creates Dropdowns in OpenObserve

When you write:
```python
logger.info(
    "Tool executed: multiply(700.0, 0.05) = 35.0",
    extra={
        "operation": "multiply",
        "operand_a": 700.0,
        "operand_b": 0.05,
        "result": 35.0,
        "saved_as": "discount",
    },
)
```

The OTel handler attaches each `extra` key as an **attribute** on the OTel log record. When OpenObserve receives this, it parses each attribute into its own column. That's why you see dropdowns like `operation`, `operand_a`, `result` etc. — each one is a separately queryable field.

---

## 📍 Part 5 — What `__name__` Does

```python
# In nodes.py:
logger = logging.getLogger(__name__)
# __name__ = "arithmetic_agent.nodes"

# In main.py:
logging.getLogger(__name__)
# __name__ = "__main__"  (when run directly)
```

This means in OpenObserve you can filter:
- `logger_name = "arithmetic_agent.nodes"` → only tool/orchestrator logs
- `logger_name = "__main__"` → only the startup log

It's automatic namespacing — you get source identification for free just by using `__name__`.

---

## 🗺️ Summary Diagram

```
YOUR CODE                    PYTHON LOGGING              OPENTELEMETRY
─────────────────────────    ──────────────────────────  ──────────────────────────────

nodes.py                     Python Logger Tree          OTel Pipeline
  logger = getLogger(         root                       LoggerProvider
    "arithmetic_agent.nodes")   └─ arithmetic_agent          │
                                      └─ arithmetic_          └─ BatchLogRecordProcessor
  logger.info(                              agent.nodes            │
    "...",                   ↑                                     └─ OTLPLogExporter
    extra={...}              │ propagates up                               │
  )  ──────────────────────► root has                                      │ gRPC
                             OTelLoggingHandler ──────────────────────────►:4317
                             (installed by                    OTel Collector
                              LoggingInstrumentor)                 │
                                                                   │ HTTP
                                                                   ▼:5080
                                                              OpenObserve
                                                          (searchable logs UI)
```

> [!NOTE]
> You write **standard Python logging** (`import logging`, `logger.info()`). OpenTelemetry is an **invisible interceptor** that catches those calls and ships them to OpenObserve. Your business logic never directly touches OTel.
