# MLOps: Fraud Detection Pipeline with MLflow

## Architecture

This folder contains the machine learning pipeline for unsupervised fraud detection using:

- **Isolation Forest** (Scikit-Learn): Fast anomaly isolation based on feature space
- **Autoencoder** (Keras/TensorFlow): Deep neural network reconstruction-based anomaly detection
- **MLflow**: Experiment tracking, model registry, and lineage management

## Setup: Local ML Environment

The ML pipeline runs **locally in your .venv**, not in Docker, to keep the Airflow containers lightweight:

```bash
# 1. Install ML dependencies (one-time, inside .venv)
pip install -r mlops/requirements-mlops.txt

# 2. Verify installation
python -c "import tensorflow; import sklearn; print('✓ ML packages ready')"
```

The main `requirements.txt` (used by Docker) includes only `mlflow` (lightweight). Training and prediction scripts run in your local Python environment.

## Workflow

### Step 1: Start MLflow Server

MLflow is already configured in `docker-compose.yml`. Start the full stack:

```bash
docker compose up -d
```

MLflow UI will be available at **http://localhost:5050**

### Step 2: Run the Training Script (Local)

The training script reads the preprocessed features, trains both models, computes the anomaly threshold (99th percentile), and registers everything in MLflow:

```bash
# From the project root, inside activated .venv
python mlops/train.py
```

**What happens:**

- Loads `csv_denormalisation/ml_ready_transactions.csv` (features only, TransactionID as index)
- Trains Isolation Forest with 1% contamination estimate
- Trains Autoencoder with 20 epochs, 64 batch size
- Computes ensemble scores: 50% IF + 50% AE
- Calculates threshold at 99th percentile of normal data
- Logs all hyperparameters, metrics, and models to MLflow

**Output in MLflow:**

- Run name: `Unsupervised_Ensemble_Training`
- Models: `isolation_forest_model`, `autoencoder_model`
- Metric: `anomaly_threshold_99th_percentile`
- Artifacts: `threshold.txt`

### Step 3: Run the Prediction Script (Local)

Once training is complete, use the prediction script to score new transaction batches:

```bash
# From the project root, inside activated .venv
python mlops/predict.py
```

**What happens:**

- Loads the latest trained models from MLflow
- Reads new features from `csv_denormalisation/ml_ready_transactions.csv`
- Computes anomaly scores for each transaction
- Joins results back to metadata (AccountID, customer info, etc.)
- Saves scored output to `csv_denormalisation/silver_scored_output.csv`

**Output:**

- `silver_scored_output.csv` with columns:
  - `anomaly_score`: 0-1 continuous score
  - `is_anomaly`: 0 (normal) or 1 (anomaly)
  - `threshold_used`: The 99th percentile threshold applied
  - Original metadata (AccountID, TransactionDate, etc.)

## Integration with Airflow

To automate this daily, add a DAG in `dags/mlops_daily.py`. The Airflow container will trigger your local .venv scripts:

```python
from datetime import datetime
from airflow import DAG
from airflow.operators.bash import BashOperator

with DAG(
    dag_id='mlops_fraud_detection',
    start_date=datetime(2026, 5, 21),
    schedule_interval='0 2 * * *',  # 2 AM daily
) as dag:
    preprocess = BashOperator(
        task_id='train_models',
        bash_command='cd /home/aboubakr/Desktop/enterprise-data-observability-platform && source .venv/bin/activate && python mlops/train.py',
    )

    predict = BashOperator(
        task_id='predict_anomalies',
        bash_command='cd /home/aboubakr/Desktop/enterprise-data-observability-platform && source .venv/bin/activate && python mlops/predict.py',
    )

    preprocess >> predict
```

This design keeps Docker lean (only `mlflow` client) while running heavy ML workloads locally.

### Isolation Forest

- `if_n_estimators`: 100 (number of trees)
- `if_contamination`: 0.01 (expected % of anomalies in dataset)

### Autoencoder

- `ae_epochs`: 20 (training iterations)
- `ae_batch_size`: 64 (samples per gradient update)
- Architecture: 59 → 32 → 16 → 8 → 16 → 32 → 59 (sablier/hourglass)

### Threshold

- `anomaly_threshold`: 99th percentile of clean data scores
- Any score ≥ threshold → flagged as anomaly

## MLflow Model Registry

Once satisfied with a run's metrics, promote the model to Production:

```bash
# In MLflow UI:
# 1. Go to the Run details
# 2. Click "Register Model"
# 3. Create model name: "bank_fraud_detector"
# 4. Go to Model Registry
# 5. Transition to "Production" stage
```

In production inference, update `predict.py` to load from the registry:

```python
# Load from Model Registry (not from runs)
iso_forest = mlflow.sklearn.load_model("models:/bank_fraud_detector/Production")
autoencoder = mlflow.keras.load_model("models:/bank_fraud_detector/Production")
```

## Debugging

**Check if MLflow is running:**

```bash
curl http://localhost:5050
```

**View logs:**

```bash
docker compose logs mlflow
```

**Load a specific run manually:**

```python
import mlflow
mlflow.set_tracking_uri("http://localhost:5050")
run = mlflow.get_run("RUN_ID_HERE")
print(run.data.params)
print(run.data.metrics)
```

---

Next steps: Integrate with dbt to transform `silver_scored_output.csv` → `gold_anomaly_alerts` table for dashboard and alerting.
