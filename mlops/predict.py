"""
ML Inference Pipeline — reads from BigQuery Silver, scores transactions.

This script:
  1. Reads `analytics.silver_enriched_transactions` from BigQuery
  2. Separates metadata (identity columns) from feature columns
  3. Applies one-hot encoding at inference time (same categories as training)
  4. Aligns columns to the training feature set (handles new/missing categories)
  5. Applies MinMaxScaler
  6. Scores with Isolation Forest + Autoencoder ensemble
  7. Writes scored output to silver_scored_output.csv
"""

import pandas as pd
import numpy as np
import mlflow
import mlflow.sklearn
import mlflow.keras
import os
import json
import joblib
from pathlib import Path
from google.cloud import bigquery
import warnings
warnings.filterwarnings('ignore')

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
import os

REPO_ROOT = Path(__file__).resolve().parent.parent
GCP_KEYFILE = REPO_ROOT / "gcp-key.json"
BQ_PROJECT = os.environ.get("GCP_PROJECT_ID", "gen-lang-client-0635762262")
BQ_SILVER_TABLE = f"{BQ_PROJECT}.silver.silver_enriched_transactions"
BQ_SCORED_TABLE = f"{BQ_PROJECT}.silver.silver_scored_transactions"
OUTPUT_PATH = REPO_ROOT / "csv_denormalisation" / "silver_scored_output.csv"

# Detect if running in Docker container or locally on host
IS_DOCKER = os.path.exists('/.dockerenv')
MLFLOW_URI = "http://mlflow:5050" if IS_DOCKER else "http://localhost:5050"
EXPERIMENT_NAME = "Bank_Fraud_Anomaly_Detection"

# Columns that are metadata (identity) — not features for the model
METADATA_COLS = [
    'transaction_id', 'account_id', 'device_id', 'merchant_id',
    'ip_address', 'transaction_date'
]

# Categorical columns to one-hot encode (same as notebook preprocessing)
CATEGORICAL_COLS = ['transaction_type', 'channel', 'location', 'customer_occupation']

# Numeric feature columns from the Silver table (before encoding)
NUMERIC_FEATURE_COLS = [
    'transaction_amount', 'customer_age', 'transaction_duration',
    'login_attempts', 'account_balance',
    'tx_hour', 'tx_day_of_week',
    'account_tx_count_24h', 'account_avg_amount_7d',
    'merchant_tx_count_1h', 'amount_vs_avg_ratio'
]


def read_silver_from_bigquery():
    """Read the Silver enriched transactions table from BigQuery."""
    # Use mounted environment keyfile in Docker container, otherwise fallback to local keyfile
    if 'GOOGLE_APPLICATION_CREDENTIALS' not in os.environ or not os.path.exists(os.environ['GOOGLE_APPLICATION_CREDENTIALS']):
        if GCP_KEYFILE.exists():
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = str(GCP_KEYFILE)
    client = bigquery.Client(project=BQ_PROJECT)
    query = f"SELECT * FROM `{BQ_SILVER_TABLE}`"
    df = client.query(query).to_dataframe()
    print(f"Loaded {len(df)} rows from BigQuery Silver table")
    return df


def write_scored_to_bigquery(df):
    """Write the scored anomaly output table back to BigQuery.
    
    Uses WRITE_TRUNCATE (a load-job disposition, NOT a DML query) which is
    fully compatible with BigQuery Free Tier.  Since predict.py always
    re-scores the entire Silver table, TRUNCATE+LOAD is the correct semantic.
    """
    # Use mounted environment keyfile in Docker container, otherwise fallback to local keyfile
    if 'GOOGLE_APPLICATION_CREDENTIALS' not in os.environ or not os.path.exists(os.environ['GOOGLE_APPLICATION_CREDENTIALS']):
        if GCP_KEYFILE.exists():
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = str(GCP_KEYFILE)
    
    client = bigquery.Client(project=BQ_PROJECT)
    
    # Reset index so transaction_id becomes a standard column in the destination table
    df_to_upload = df.reset_index()
    
    # WRITE_TRUNCATE is a load-job disposition — allowed on Free Tier
    # (unlike DELETE which is a DML query and is forbidden)
    job_config = bigquery.LoadJobConfig(
        write_disposition="WRITE_TRUNCATE",
    )
    
    print(f"[TRUNCATE+LOAD] Saving scored transactions to BigQuery: {BQ_SCORED_TABLE}...")
    job = client.load_table_from_dataframe(df_to_upload, BQ_SCORED_TABLE, job_config=job_config)
    job.result()  # Wait for the loading job to complete
    print(f"✓ Successfully pushed scored transactions to BigQuery!")


def load_mlflow_artifacts():
    """Load the latest trained models, threshold, training columns from MLflow."""
    mlflow.set_tracking_uri(MLFLOW_URI)

    experiment = mlflow.get_experiment_by_name(EXPERIMENT_NAME)
    if experiment is None:
        raise ValueError(
            f"L'expérience '{EXPERIMENT_NAME}' n'existe pas. "
            "Exécute d'abord train.py"
        )

    runs = mlflow.search_runs(
        experiment_ids=[experiment.experiment_id],
        order_by=["start_time DESC"],
        max_results=1,
    )
    if len(runs) == 0:
        raise ValueError("Aucun run trouvé dans l'expérience MLflow.")

    run_id = runs.iloc[0]['run_id']
    print(f"Utilisation du Run ID: {run_id}")

    # Load models
    iso_forest = mlflow.sklearn.load_model(f"runs:/{run_id}/isolation_forest_model")
    autoencoder = mlflow.keras.load_model(f"runs:/{run_id}/autoencoder_model")

    # Load threshold
    client = mlflow.tracking.MlflowClient()
    threshold = None
    for artifact in client.list_artifacts(run_id):
        if artifact.path == 'threshold.txt':
            path = client.download_artifacts(run_id, 'threshold.txt')
            with open(path, 'r') as f:
                threshold = float(f.read().strip())
            break
    if threshold is None:
        threshold = runs.iloc[0]['metrics.anomaly_threshold_99th_percentile']

    # Load training column order
    training_columns = None
    for artifact in client.list_artifacts(run_id):
        if artifact.path == 'training_columns.json':
            path = client.download_artifacts(run_id, 'training_columns.json')
            with open(path, 'r') as f:
                training_columns = json.load(f)
            break

    print(f"Seuil utilisé: {threshold:.4f}")
    if training_columns:
        print(f"Training columns loaded: {len(training_columns)} features")

    return iso_forest, autoencoder, threshold, training_columns, run_id


def prepare_features(df, training_columns):
    """
    Transform Silver table into a feature matrix matching training format.

    Steps:
      1. Extract metadata (for rejoining after scoring)
      2. Select numeric + categorical columns
      3. One-hot encode categoricals
      4. Align to training column order (fill missing cols with 0, drop extra)
      5. MinMaxScale to [0, 1]
    """
    # 1. Separate metadata
    metadata_df = df[METADATA_COLS].copy()
    metadata_df = metadata_df.set_index('transaction_id')

    # 2. Build feature dataframe
    feature_df = df[NUMERIC_FEATURE_COLS + CATEGORICAL_COLS].copy()
    feature_df.index = df['transaction_id']

    # 3. One-hot encode categoricals (same drop_first=True as notebook)
    feature_df = pd.get_dummies(feature_df, columns=CATEGORICAL_COLS, drop_first=True)

    # Ensure all values are numeric (fill any NaN from velocity calcs)
    feature_df = feature_df.fillna(0).astype(float)

    # 4. Align to training columns
    if training_columns is not None:
        # Add missing columns (new cities etc. in training that aren't in inference)
        for col in training_columns:
            if col not in feature_df.columns:
                feature_df[col] = 0.0

        # Reorder to match training and drop any extra columns
        feature_df = feature_df[training_columns]

    # 5. MinMaxScale
    from sklearn.preprocessing import MinMaxScaler
    scaler = MinMaxScaler()
    X_scaled = scaler.fit_transform(feature_df.values)
    feature_df_scaled = pd.DataFrame(
        X_scaled, columns=feature_df.columns, index=feature_df.index
    )

    return feature_df_scaled, metadata_df


def main():
    # 1. Read from BigQuery Silver
    print("Lecture de la table BigQuery Silver...")
    df = read_silver_from_bigquery()

    if df.empty:
        print("⚠ No data in Silver table. Exiting.")
        return

    # 2. Load models and artifacts from MLflow
    print("Récupération des modèles depuis MLflow...")
    iso_forest, autoencoder, threshold, training_columns, run_id = load_mlflow_artifacts()

    # 3. Prepare features
    print("Préparation des features (encoding + scaling)...")
    feature_df, metadata_df = prepare_features(df, training_columns)
    X = feature_df.values

    # 4. Score with ensemble
    print("Calcul des scores d'anomalie...")
    if_scores = -iso_forest.decision_function(X)
    if_scores_norm = (if_scores - if_scores.min()) / (if_scores.max() - if_scores.min() + 1e-6)

    X_pred = autoencoder.predict(X, verbose=0)
    ae_mse = np.mean(np.power(X - X_pred, 2), axis=1)
    ae_scores_norm = (ae_mse - ae_mse.min()) / (ae_mse.max() - ae_mse.min() + 1e-6)

    final_scores = (0.5 * if_scores_norm) + (0.5 * ae_scores_norm)

    # 5. Build results
    print("Construction du rapport final...")
    results_df = pd.DataFrame(index=feature_df.index)
    results_df['anomaly_score'] = final_scores
    results_df['is_anomaly'] = (results_df['anomaly_score'] >= threshold).astype(int)
    results_df['threshold_used'] = threshold

    # Rejoin with metadata
    final_output = results_df.join(metadata_df, how='inner')

    # 6. Save
    final_output.to_csv(OUTPUT_PATH, index=True)
    write_scored_to_bigquery(final_output)

    n_anomalies = (final_output['is_anomaly'] == 1).sum()
    print(f"✓ Inférence terminée !")
    print(f"  - Total transactions: {len(final_output)}")
    print(f"  - Anomalies détectées: {n_anomalies} ({100*n_anomalies/len(final_output):.2f}%)")
    print(f"  - Fichier de sortie: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
