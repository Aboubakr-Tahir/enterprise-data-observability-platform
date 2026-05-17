# Enterprise Data Observability Platform - Deployment Status

## ✅ System Status: FULLY OPERATIONAL

All services are running and integrated successfully. The entire stack can be started with a single command:

```bash
docker compose up --build
```

---

## 📋 Service Status

| Service                    | Port       | Status     | Health  |
| -------------------------- | ---------- | ---------- | ------- |
| **Airflow Web UI**         | 8080       | ✅ Running | Healthy |
| **Airflow Scheduler**      | -          | ✅ Running | Healthy |
| **Superset BI Dashboard**  | 8088       | ✅ Running | Healthy |
| **Marquez Lineage Server** | 5000       | ✅ Running | Healthy |
| **Marquez Admin**          | 5001       | ✅ Running | Healthy |
| **PostgreSQL (Airflow)**   | 5432       | ✅ Running | Healthy |
| **PostgreSQL (Marquez)**   | (internal) | ✅ Running | Healthy |

---

## 🔧 Key Configuration Details

### Airflow

- **Base Image**: `apache/airflow:2.10.0-python3.9`
- **Executor**: LocalExecutor
- **OpenLineage Provider**: ✅ Installed (v1.10.0)
- **Key Dependencies**:
  - dbt-core 1.8.2
  - dbt-postgres 1.8.2
  - great-expectations 0.18.12
  - psycopg2-binary 2.9.9
  - protobuf < 5.0.0 (pinned to avoid dbt conflicts)

### Superset

- **Custom Dockerfile**: `Dockerfile.superset`
- **PostgreSQL Driver**: ✅ Installed in `/app/.venv/lib/python3.10/site-packages`
- **Secret Key**: Configured via `.env` file

### Marquez

- **Configuration**: Dropwizard properties via JAVA_OPTS
- **Database**: PostgreSQL 14 (separate instance)
- **JDBC URL**: `jdbc:postgresql://postgres-marquez:5432/marquez`
- **API Endpoints**:
  - Lineage: `http://marquez:5000/api/v1/lineage`
  - Namespaces: `http://marquez:5000/api/v1/namespaces`

---

## 🔄 Data Lineage Integration

### OpenLineage Flow

1. **Airflow DAGs** emit lineage events via HTTP transport
2. **OpenLineage Provider** (v1.10.0) captures task execution metadata
3. **Marquez API** receives events at `http://marquez:5000/api/v1/lineage`
4. **Marquez Database** stores lineage information

### Verification (Completed)

- ✅ Airflow exports OpenLineage events
- ✅ Marquez receives HTTP POST requests with code 201 (Created)
- ✅ Marquez API is accessible and operational
- ✅ Database connectivity verified

---

## 📊 Running the Example DAG

The repository includes `gx_validation_dag.py` which demonstrates the integration:

```bash
# Access Airflow UI
# http://localhost:8080

# Unpause the DAG
docker compose exec airflow-webserver airflow dags unpause data_quality_check

# Trigger the DAG
docker compose exec airflow-webserver airflow dags trigger data_quality_check

# Monitor execution
docker compose logs -f airflow-scheduler | grep -i openlineage
```

### DAG Execution Output

- Task executes Great Expectations validation
- OpenLineage events are emitted and sent to Marquez
- Marquez receives events with HTTP 201 status

---

## 🛠 Troubleshooting

### If Airflow Container Fails to Start

**Symptom**: `service "airflow-webserver" is not running`

**Solution**:

1. Check logs: `docker compose logs airflow-webserver`
2. Rebuild without cache: `docker compose build --no-cache`
3. Restart services: `docker compose up -d airflow-webserver airflow-scheduler`

### If Superset Connection Fails

**Symptom**: PostgreSQL driver errors in Superset

**Solution**:

- The custom `Dockerfile.superset` automatically installs psycopg2-binary in the correct venv location
- If still failing, verify: `docker compose exec superset pip list | grep psycopg2`

### If OpenLineage Events Don't Arrive

**Symptom**: No lineage events in Marquez logs

**Solution**:

1. Verify provider is installed: `docker compose exec airflow-webserver python -m pip list | grep openlineage`
2. Check configuration: `docker compose exec airflow-webserver airflow config get-value openlineage transport`
3. Review Airflow logs: `docker compose logs airflow-scheduler | grep -i openlineage`

---

## 📁 Important Files

| File                        | Purpose                                     |
| --------------------------- | ------------------------------------------- |
| `Dockerfile`                | Airflow image with dependencies             |
| `Dockerfile.superset`       | Superset image with PostgreSQL driver       |
| `requirements.txt`          | Python dependencies for Airflow             |
| `docker-compose.yml`        | Service orchestration                       |
| `.env`                      | Environment variables (Superset SECRET_KEY) |
| `dags/gx_validation_dag.py` | Example DAG with lineage                    |
| `great_expectations/`       | Data quality expectations                   |
| `dbt/my_dbt_project/`       | dbt models for data transformation          |

---

## 🔌 API Endpoints

### Airflow

- Web UI: `http://localhost:8080`
- REST API: `http://localhost:8080/api/v1/`

### Superset

- Web UI: `http://localhost:8088`
- Admin: `http://localhost:8088/admin`

### Marquez

- Web UI: `http://localhost:5000`
- API: `http://localhost:5000/api/v1/`
- Admin: `http://localhost:5001`

### Example API Calls

```bash
# List Airflow DAGs
curl http://localhost:8080/api/v1/dags

# Get Marquez namespaces
curl http://localhost:5000/api/v1/namespaces

# Get datasets in default namespace
curl http://localhost:5000/api/v1/namespaces/default/datasets

# List Superset databases
curl http://localhost:8088/api/v1/database/
```

---

## 📝 Next Steps

1. **Extend dbt Models**: Add more dbt models in `dbt/my_dbt_project/models/` for actual data transformation
2. **Create Airflow DAGs**: Build DAGs that use dbt models and create lineage
3. **Configure Superset**: Connect databases and create dashboards using transformed data
4. **Monitor Lineage**: Use Marquez UI to visualize data lineage and relationships

---

## 🎯 Success Criteria - All Met ✅

- [x] Single `docker compose up --build` command starts all services
- [x] No manual interventions required
- [x] All services achieve healthy state
- [x] Airflow can discover and execute DAGs
- [x] OpenLineage provider is installed and configured
- [x] Marquez receives lineage events via HTTP API
- [x] Superset can connect to PostgreSQL databases
- [x] API endpoints are accessible and operational

---

**Last Updated**: 2026-05-17T15:05:57+00:00
**Platform Version**: 1.0
**Status**: Production Ready ✅
