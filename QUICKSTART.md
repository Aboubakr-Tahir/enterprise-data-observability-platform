# Quick Start Guide - Enterprise Data Observability Platform

## 🚀 One-Command Startup

```bash
docker compose up --build
```

Wait for all services to show as "healthy" or "running":

```
✔ postgres                    ...  Healthy
✔ postgres-marquez           ...  Healthy
✔ marquez                    ...  Up
✔ airflow-webserver          ...  Healthy
✔ airflow-scheduler          ...  Running
✔ superset                   ...  Healthy
```

---

## 📂 Service Access

| Service      | URL                   | Default Credentials |
| ------------ | --------------------- | ------------------- |
| **Airflow**  | http://localhost:8080 | admin / admin       |
| **Superset** | http://localhost:8088 | admin / admin       |
| **Marquez**  | http://localhost:5000 | -                   |

---

## 🔄 Test Data Lineage Integration

### Step 1: Unpause and Trigger the Demo DAG

```bash
docker compose exec airflow-webserver airflow dags unpause data_quality_check
docker compose exec airflow-webserver airflow dags trigger data_quality_check
```

### Step 2: Monitor Execution

```bash
# Watch Airflow scheduler
docker compose logs -f airflow-scheduler

# In another terminal, watch Marquez receive lineage events
docker compose logs -f marquez | grep "POST /api/v1/lineage"
```

### Step 3: Verify in Marquez

```bash
# Check namespaces
curl http://localhost:5000/api/v1/namespaces

# View datasets (if DAG creates data transformations)
curl http://localhost:5000/api/v1/namespaces/default/datasets
```

---

## 📊 Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                     Docker Compose Stack                 │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  ┌──────────────┐    ┌──────────────┐   ┌────────────┐ │
│  │   Airflow    │───→│   Marquez    │──→│ Marquez DB │ │
│  │ (Scheduler)  │    │ (Lineage)    │   │(PostgreSQL)│ │
│  └──────────────┘    └──────────────┘   └────────────┘ │
│       │                                                   │
│       ├─ dbt (transformations)                           │
│       ├─ Great Expectations (validation)                 │
│       └─ OpenLineage (event emission)                    │
│                                                           │
│  ┌──────────────┐    ┌──────────────┐                   │
│  │   Superset   │───→│ PostgreSQL DB │                  │
│  │     (BI)     │    │  (Airflow)    │                  │
│  └──────────────┘    └──────────────┘                   │
│                                                           │
└─────────────────────────────────────────────────────────┘
```

---

## 🔧 Key Components

### Airflow Configuration

- **OpenLineage Transport**: HTTP to `http://marquez:5000/api/v1/lineage`
- **OpenLineage Namespace**: `my_data_stack`
- **DAGs Location**: `dags/` directory

### Superset Setup

- **Dockerfile**: Custom `Dockerfile.superset` with PostgreSQL driver
- **Connection**: Auto-configured to Airflow PostgreSQL

### Marquez Integration

- **Database**: PostgreSQL 14 instance (postgres-marquez)
- **Credentials**: marquez/marquez
- **Port**: 5000 (API) + 5001 (Admin)

### Dependencies Installed

```
✓ dbt-core 1.8.2 (data transformation)
✓ dbt-postgres 1.8.2 (PostgreSQL adapter)
✓ great-expectations 0.18.12 (data validation)
✓ apache-airflow-providers-openlineage 1.10.0 (lineage)
✓ psycopg2-binary 2.9.9 (PostgreSQL driver)
```

---

## 📝 Example DAG

File: `dags/gx_validation_dag.py`

The included DAG demonstrates:

- Running Great Expectations validation checks
- Emitting OpenLineage events
- Integration with Marquez

To expand with data transformation:

1. Add dbt models in `dbt/my_dbt_project/models/`
2. Create Airflow DAG that runs `dbt` commands
3. OpenLineage automatically captures data lineage

---

## 🐛 Common Issues & Solutions

| Issue                     | Solution                                                       |
| ------------------------- | -------------------------------------------------------------- |
| Airflow won't start       | `docker compose logs airflow-webserver` → rebuild if needed    |
| Superset PostgreSQL error | Check `docker compose exec superset pip list \| grep psycopg2` |
| Marquez shows no datasets | Check if DAG transforms data (lineage needs read/write ops)    |
| Slow build                | Use `--no-cache`: `docker compose build --no-cache`            |

---

## 📚 Documentation Files

- `DEPLOYMENT_STATUS.md` - Full system status and troubleshooting
- `SUPERSET_GUIDE.md` - Superset-specific setup
- `Dockerfile` - Airflow image definition
- `Dockerfile.superset` - Superset image definition
- `docker-compose.yml` - Complete service configuration

---

## 🎯 What's Next?

1. **Explore Airflow**: Create custom DAGs in `dags/`
2. **Build with dbt**: Add data transformations in `dbt/my_dbt_project/models/`
3. **Add Validation**: Extend `great_expectations/expectations/`
4. **Visualize in Superset**: Connect databases and create dashboards
5. **Monitor Lineage**: Use Marquez UI to track data flow

---

**Ready to go!** 🚀

Your data observability platform is now fully operational and integrated. All services communicate seamlessly via Docker Compose networking.
