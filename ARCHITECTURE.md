# 🏗️ Architecture Diagram

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      ENTERPRISE DATA OBSERVABILITY PLATFORM                  │
│                         (Single Docker Compose Stack)                        │
└─────────────────────────────────────────────────────────────────────────────┘

                          docker compose up --build
                                      │
                    ┌───────────────────┼───────────────────┐
                    │                   │                   │
                    ▼                   ▼                   ▼

    ┌──────────────────────┐  ┌──────────────────┐  ┌──────────────────┐
    │  DATA ORCHESTRATION  │  │  DATA ANALYTICS  │  │  DATA LINEAGE    │
    │      (AIRFLOW)       │  │   (SUPERSET)     │  │   (MARQUEZ)      │
    ├──────────────────────┤  ├──────────────────┤  ├──────────────────┤
    │ Port: 8080           │  │ Port: 8088       │  │ Port: 5000/5001  │
    │ Status: Healthy      │  │ Status: Healthy  │  │ Status: Up       │
    │                      │  │                  │  │                  │
    │ • DAG Scheduler      │  │ • Dashboards     │  │ • Lineage Graph  │
    │ • Task Executor      │  │ • SQL Analytics  │  │ • Metadata Store │
    │ • Monitoring         │  │ • User Admin     │  │ • Job History    │
    │                      │  │                  │  │                  │
    │ Data Tools:          │  │ Connected to:    │  │ Receives from:   │
    │ • dbt (transform)    │  │ • PostgreSQL DB  │  │ • Airflow Events │
    │ • Great Expectations │  │                  │  │ (OpenLineage)    │
    │ • OpenLineage        │  │                  │  │                  │
    └──────────┬───────────┘  └────────┬─────────┘  └────────┬─────────┘
               │                       │                    │
               └─────────────┬─────────┴────────────┬───────┘
                             │                      │
                             ▼                      ▼
            ┌─────────────────────────────────────────┐
            │       PERSISTENT DATA LAYER             │
            │         (PostgreSQL x2)                 │
            ├─────────────────────────────────────────┤
            │                                         │
            │ Instance 1: airflow@localhost:5432      │
            │ • Airflow metadata database             │
            │ • DAG runs & task history               │
            │ • Connections & variables               │
            │                                         │
            │ Instance 2: marquez@internal:5432       │
            │ • Marquez lineage data                  │
            │ • Dataset metadata                      │
            │ • Job execution records                 │
            │                                         │
            └─────────────────────────────────────────┘
```

---

## Data Flow - Lineage Collection

```
┌──────────────┐
│  Airflow DAG │
│  Execution   │
└────────┬─────┘
         │
         │ [Task events: start, end, input, output]
         │
         ▼
┌──────────────────────────────────┐
│   OpenLineage Provider 1.10.0    │
│  (apache-airflow-providers-      │
│   openlineage)                   │
└────────┬─────────────────────────┘
         │
         │ [HTTP POST events]
         │ [JSON LineageEvent format]
         │ [Namespace: my_data_stack]
         │
         ▼
    ━━━━━━━━━━━━━━━━━ NETWORK ━━━━━━━━━━━━━━━━━━
         │
         │ http://marquez:5000/api/v1/lineage
         │
         ▼
┌──────────────────────────────────┐
│       MARQUEZ API                │
│  (Lineage Server)                │
│  Status: HTTP 201 Created ✅      │
└────────┬─────────────────────────┘
         │
         │ [Parse & validate events]
         │ [Extract dataset & job info]
         │
         ▼
┌──────────────────────────────────┐
│   Marquez PostgreSQL Database    │
│   (postgres-marquez:5432)        │
│                                  │
│ • lineage_events (raw)           │
│ • datasets (parsed)              │
│ • jobs (parsed)                  │
│ • lineage (relationships)        │
└──────────────────────────────────┘
         │
         ▼
    ┌─────────────────┐
    │ MARQUEZ UI      │
    │ (localhost:5000)│
    │ Visualize:      │
    │ • Data lineage  │
    │ • Dataset graph │
    │ • Job history   │
    └─────────────────┘
```

---

## Container Network

```
docker-compose network: "data_stack" (bridge)

┌─────────────────────────────────────────────────────────────────┐
│                     Docker Compose Network                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Container Name          │ Internal IP  │ External Port        │
│  ─────────────────────────────────────────────────────────────   │
│  postgres                │ 172.18.0.x   │ 5432 → localhost:5432│
│  postgres-marquez        │ 172.18.0.x   │ (internal only)      │
│  marquez                 │ 172.18.0.x   │ 5000 → localhost:5000│
│                          │              │ 5001 → localhost:5001│
│  airflow-webserver       │ 172.18.0.x   │ 8080 → localhost:8080│
│  airflow-scheduler       │ 172.18.0.x   │ (internal only)      │
│  airflow-init            │ 172.18.0.x   │ (internal only)      │
│  superset                │ 172.18.0.x   │ 8088 → localhost:8088│
│  superset-init           │ 172.18.0.x   │ (internal only)      │
│                                                                 │
│  Volume Mounts:                                                 │
│  • postgres_data  → /var/lib/postgresql/data                  │
│  • marquez_data   → /var/lib/marquez                           │
│  • superset_home  → /app/superset_home                         │
│  • ./dags         → /opt/airflow/dags (read-only)             │
│  • ./dbt          → /opt/airflow/dbt (read-only)              │
│  • ./great_expectations → /opt/airflow/great_expectations     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Configuration Flow

```
User Action: docker compose up --build
       │
       ▼
┌─────────────────────────────────┐
│ Docker Compose Reads:           │
│ • docker-compose.yml            │
│ • .env (secrets)                │
└────┬────────────────────────────┘
     │
     ├─► Dockerfile ──build──► airflow-base image
     │       • libpq-dev
     │       • requirements.txt
     │
     ├─► Dockerfile.superset ──build──► superset image
     │       • psycopg2-binary auto-install
     │
     └─► Service Definitions ──initialize──► Services
             • postgres (2x)
             • marquez
             • airflow (3x: init, scheduler, webserver)
             • superset (2x: init, main)

                              ▼

         ┌──────────────────────────────────┐
         │  Services Auto-Configuration     │
         ├──────────────────────────────────┤
         │                                  │
         │  PostgreSQL:                     │
         │  • Migrations run automatically  │
         │  • Schemas created              │
         │  • Users configured             │
         │                                  │
         │  Airflow:                        │
         │  • DB initialized               │
         │  • OpenLineage configured       │
         │  • DAGs auto-discovered         │
         │                                  │
         │  Superset:                       │
         │  • SECRET_KEY set (.env)        │
         │  • DB initialized               │
         │  • Admin user created           │
         │                                  │
         │  Marquez:                        │
         │  • DB migrations run            │
         │  • API endpoints ready          │
         │  • Lineage API listening        │
         │                                  │
         └──────────────────────────────────┘
                       ▼
         ┌──────────────────────────────────┐
         │    ALL SERVICES HEALTHY ✅        │
         │    Ready for Use                 │
         └──────────────────────────────────┘
```

---

## Dependency Tree

```
docker-compose.yml
  │
  ├─ services:
  │   │
  │   ├─ postgres (PostgreSQL 14)
  │   │   └─ health check: SELECT 1
  │   │
  │   ├─ postgres-marquez (PostgreSQL 14)
  │   │   └─ health check: SELECT 1
  │   │   └─ depends_on: [init]
  │   │
  │   ├─ marquez (marquezproject/marquez:latest)
  │   │   ├─ depends_on: [postgres-marquez]
  │   │   ├─ environment: JAVA_OPTS (DB config)
  │   │   └─ wait_for: postgres-marquez:5432
  │   │
  │   ├─ airflow-init
  │   │   ├─ depends_on: [postgres]
  │   │   ├─ build: Dockerfile (custom Airflow)
  │   │   ├─ volumes: dags/, dbt/, great_expectations/
  │   │   └─ environment: AIRFLOW_HOME, etc.
  │   │
  │   ├─ airflow-scheduler
  │   │   ├─ depends_on: [airflow-init]
  │   │   ├─ environment: OpenLineage config
  │   │   └─ volumes: shared with webserver
  │   │
  │   ├─ airflow-webserver
  │   │   ├─ depends_on: [airflow-init]
  │   │   ├─ ports: 8080:8080
  │   │   ├─ environment: OpenLineage config
  │   │   └─ health check: curl /health
  │   │
  │   ├─ superset-init
  │   │   ├─ build: Dockerfile.superset (custom)
  │   │   └─ depends_on: [postgres]
  │   │
  │   └─ superset
  │       ├─ build: Dockerfile.superset
  │       ├─ depends_on: [superset-init]
  │       ├─ ports: 8088:8088
  │       ├─ environment: SUPERSET_SECRET_KEY (.env)
  │       └─ health check: curl /health
  │
  ├─ networks:
  │   └─ data_stack (bridge)
  │       └─ All services connected
  │
  └─ volumes:
      ├─ postgres_data → /var/lib/postgresql/data
      ├─ marquez_data → /var/lib/marquez
      └─ superset_home → /app/superset_home
```

---

## OpenLineage Integration Detail

```
┌──────────────────────────────────────────────────────────────┐
│              OPENLINEAGE INTEGRATION FLOW                    │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│ 1. AIRFLOW CONFIGURATION (Environment Variables)            │
│    ─────────────────────────────────────────────────         │
│    AIRFLOW__OPENLINEAGE__TRANSPORT:                         │
│      type: http                                              │
│      url: http://marquez:5000                                │
│      endpoint: api/v1/lineage                                │
│                                                              │
│    AIRFLOW__OPENLINEAGE__NAMESPACE: my_data_stack           │
│    AIRFLOW__OPENLINEAGE__DISABLED: False                    │
│                                                              │
│ 2. PROVIDER INSTALLATION (requirements.txt)                 │
│    ─────────────────────────────────────────────────         │
│    apache-airflow-providers-openlineage==1.10.0             │
│                                                              │
│    Dependencies:                                            │
│    • openlineage-integration-common==1.19.0                 │
│    • openlineage-python==1.19.0                              │
│    • openlineage_sql==1.19.0                                │
│                                                              │
│ 3. TASK EXECUTION (Automatic)                               │
│    ─────────────────────────────────────────────────         │
│    When Airflow task executes:                              │
│    • Task start event captured                              │
│    • Input datasets identified                              │
│    • Output datasets identified                             │
│    • Task end event captured                                │
│                                                              │
│ 4. EVENT EMISSION (HTTP)                                    │
│    ─────────────────────────────────────────────────         │
│    OpenLineage client prepares JSON event:                  │
│    {                                                         │
│      "eventType": "START|COMPLETE|FAIL|ABORT",             │
│      "eventTime": "2026-05-17T15:05:45.000000Z",           │
│      "run": {                                                │
│        "runId": "...",                                      │
│        "facets": { ... }                                    │
│      },                                                      │
│      "job": {                                                │
│        "namespace": "my_data_stack",                        │
│        "name": "data_quality_check.run_gx_validation"      │
│      },                                                      │
│      "inputs": [ ... ],                                     │
│      "outputs": [ ... ]                                     │
│    }                                                         │
│                                                              │
│    POST http://marquez:5000/api/v1/lineage                 │
│    Content-Type: application/json                           │
│                                                              │
│ 5. MARQUEZ RECEPTION & PROCESSING                           │
│    ─────────────────────────────────────────────────         │
│    HTTP 201 Created ✅                                       │
│    • Event validated                                        │
│    • Datasets extracted                                     │
│    • Jobs registered                                        │
│    • Lineage stored in PostgreSQL                           │
│                                                              │
│ 6. MARQUEZ EXPOSURE (UI & API)                              │
│    ─────────────────────────────────────────────────         │
│    Web UI: http://localhost:5000                            │
│    • Visualize lineage graph                                │
│    • Browse datasets                                        │
│    • Track job history                                      │
│                                                              │
│    REST API: http://localhost:5000/api/v1/                 │
│    • GET /namespaces                                        │
│    • GET /datasets                                          │
│    • GET /jobs                                              │
│    • GET /runs                                              │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## Technology Stack

```
┌─────────────────────────────────────────────────┐
│         ENTERPRISE DATA STACK                    │
├─────────────────────────────────────────────────┤
│                                                 │
│  Orchestration       │  Airflow 2.10.0         │
│  Executor            │  LocalExecutor          │
│  Python Version      │  3.9                    │
│                      │                         │
│  Transformation      │  dbt-core 1.8.2         │
│  DB Adapter          │  dbt-postgres 1.8.2     │
│                      │                         │
│  Data Quality        │  Great Expectations     │
│                      │  0.18.12                │
│                      │                         │
│  Lineage Capture     │  OpenLineage 1.19.0     │
│  Lineage Provider    │  airflow-providers-     │
│                      │  openlineage 1.10.0     │
│                      │                         │
│  Lineage Server      │  Marquez (latest)       │
│  Lineage Backend     │  PostgreSQL 14          │
│  Lineage UI          │  Web UI + Admin         │
│                      │                         │
│  Analytics/BI        │  Superset (latest)      │
│  Superset Backend    │  PostgreSQL 14          │
│                      │                         │
│  Database Layer      │  PostgreSQL 14 (x2)    │
│  Persistence         │  Named volumes          │
│                      │                         │
│  Containerization    │  Docker + Docker       │
│                      │  Compose               │
│                      │                         │
└─────────────────────────────────────────────────┘
```

---

**This architecture ensures:**

- ✅ Complete data observability
- ✅ Automated data orchestration
- ✅ Captured lineage metadata
- ✅ Business intelligence dashboards
- ✅ Scalable, containerized deployment
