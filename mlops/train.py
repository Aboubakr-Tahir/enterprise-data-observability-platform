import pandas as pd
import numpy as np
import os
import json
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import MinMaxScaler
import tensorflow as tf
from tensorflow.keras import layers, models
import mlflow
import mlflow.sklearn
import mlflow.keras
import joblib
import warnings
warnings.filterwarnings('ignore')

# ---------------------------------------------------------------------------
# MLflow Configuration
# ---------------------------------------------------------------------------
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parent.parent
IS_DOCKER = os.path.exists('/.dockerenv')
MLFLOW_URI = "http://mlflow:5050" if IS_DOCKER else "http://localhost:5050"

mlflow.set_tracking_uri(MLFLOW_URI)
from mlflow.tracking import MlflowClient
import time
client = MlflowClient()
_base_exp_name = "Bank_Fraud_Anomaly_Detection"
_artifact_root = f"file://{os.path.join(REPO_ROOT, 'mlruns')}"

try:
    existing_exp = client.get_experiment_by_name(_base_exp_name)

    if existing_exp is not None and existing_exp.lifecycle_stage == 'deleted':
        print(f"Restoring deleted experiment: {_base_exp_name}")
        client.restore_experiment(existing_exp.experiment_id)
        mlflow.set_experiment(_base_exp_name)
    elif existing_exp is None:
        print(f"Creating new experiment: {_base_exp_name}")
        client.create_experiment(_base_exp_name, artifact_location=_artifact_root)
        mlflow.set_experiment(_base_exp_name)
    else:
        if existing_exp.artifact_location.startswith("file:///app") or existing_exp.artifact_location.startswith("/app"):
            _new_name = f"{_base_exp_name}_migrated_{int(time.time())}"
            client.create_experiment(_new_name, artifact_location=_artifact_root)
            mlflow.set_experiment(_new_name)
        else:
            mlflow.set_experiment(_base_exp_name)
except Exception as e:
    print(f"Error managing experiment: {e}. Creating fallback experiment.")
    _new_name = f"{_base_exp_name}_run_{int(time.time())}"
    try:
        client.create_experiment(_new_name, artifact_location=_artifact_root)
        mlflow.set_experiment(_new_name)
    except:
        mlflow.set_experiment(_base_exp_name)


def build_autoencoder(input_dim):
    """Définition de l'architecture Sablier de l'Autoencoder (MLP)"""
    model = models.Sequential([
        # Encoder
        layers.Input(shape=(input_dim,)),
        layers.Dense(32, activation='relu'),
        layers.Dense(16, activation='relu'),
        layers.Dense(8, activation='relu'),  # Espace latent (Compression)

        # Decoder
        layers.Dense(16, activation='relu'),
        layers.Dense(32, activation='relu'),
        layers.Dense(input_dim, activation='sigmoid')  # Sortie normalisée (MinMax)
    ])
    model.compile(optimizer='adam', loss='mse')
    return model


def main():
    # 2. Lecture du dataset de Features créé par le script précédent
    data_path = os.path.join(REPO_ROOT, 'csv_denormalisation', 'ml_ready_transactions.csv')

    if not os.path.exists(data_path):
        raise FileNotFoundError(f"Le fichier {data_path} est introuvable. Exécute d'abord le préprocessing.")

    df = pd.read_csv(data_path, index_col='TransactionID')

    X = df.values  # Matrice numérique pure pour l'IA
    input_dim = X.shape[1]

    # 3. Démarrage du Run MLOps avec MLflow
    with mlflow.start_run(run_name="Unsupervised_Ensemble_Training"):
        print("Entraînement de l'Isolation Forest...")
        # Hyperparamètres de l'Isolation Forest
        if_contamination = 0.01  # On estime à priori 1% d'anomalies globales
        if_estimators = 100

        mlflow.log_param("if_contamination", if_contamination)
        mlflow.log_param("if_n_estimators", if_estimators)

        iso_forest = IsolationForest(n_estimators=if_estimators, contamination=if_contamination, random_state=42)
        iso_forest.fit(X)

        # Calcul du score d'anomalie de l'IF (on le normalise pour qu'un score haut = anomalie)
        if_scores = -iso_forest.decision_function(X)
        if_scores_norm = (if_scores - if_scores.min()) / (if_scores.max() - if_scores.min() + 1e-6)

        print("Entraînement de l'Autoencoder (Réseau de Neurones)...")
        ae_epochs = 20
        ae_batch_size = 64

        mlflow.log_param("ae_epochs", ae_epochs)
        mlflow.log_param("ae_batch_size", ae_batch_size)

        autoencoder = build_autoencoder(input_dim)
        autoencoder.fit(
            X, X,
            epochs=ae_epochs,
            batch_size=ae_batch_size,
            shuffle=True,
            verbose=0
        )

        # Calcul de l'erreur de reconstruction (MSE) pour chaque ligne
        X_pred = autoencoder.predict(X, verbose=0)
        ae_mse = np.mean(np.power(X - X_pred, 2), axis=1)
        ae_scores_norm = (ae_mse - ae_mse.min()) / (ae_mse.max() - ae_mse.min() + 1e-6)

        print("Calcul de la fusion des scores d'ensemble...")
        final_scores = (0.5 * if_scores_norm) + (0.5 * ae_scores_norm)

        # Définition métier du seuil critique (99ème percentile du dataset propre)
        threshold_99 = np.percentile(final_scores, 99)
        mlflow.log_metric("anomaly_threshold_99th_percentile", threshold_99)
        print(f"Seuil critique d'anomalie: {threshold_99:.4f}")

        # 4. Enregistrement des modèles dans le Feature Store MLflow
        print("Logging des artefacts dans MLflow...")
        mlflow.sklearn.log_model(iso_forest, "isolation_forest_model")
        mlflow.keras.log_model(autoencoder, "autoencoder_model")

        # Sauvegarder le seuil
        with open('/tmp/threshold.txt', 'w') as f:
            f.write(str(threshold_99))
        mlflow.log_artifact('/tmp/threshold.txt')

        # -----------------------------------------------------------------
        # NEW: Persist the MinMaxScaler and training column order
        # so that predict.py can replicate the exact same encoding.
        # -----------------------------------------------------------------

        # Save the training column order (needed by predict.py to align
        # one-hot encoded columns to the same order the models were trained on)
        training_columns = list(df.columns)
        columns_path = '/tmp/training_columns.json'
        with open(columns_path, 'w') as f:
            json.dump(training_columns, f)
        mlflow.log_artifact(columns_path)
        print(f"  - Saved training_columns.json ({len(training_columns)} features)")

        # Save a fitted MinMaxScaler built from the raw (pre-scaled) feature
        # distributions.  Since ml_ready_transactions.csv is already scaled to
        # [0,1], we record an identity scaler here.  predict.py will fit a new
        # scaler on its own raw features and only uses the column list from
        # training_columns.json to guarantee alignment.
        # For a production pipeline where the scaler must be reused exactly,
        # persist the scaler fitted on the original (unscaled) data instead.
        scaler = MinMaxScaler()
        scaler.fit(X)  # fit on the training matrix so the object is valid
        scaler_path = '/tmp/training_scaler.joblib'
        joblib.dump(scaler, scaler_path)
        mlflow.log_artifact(scaler_path)
        print("  - Saved training_scaler.joblib")

        print(f"✓ Entraînement MLOps terminé ! Vérifiez http://localhost:5050")
        print(f"  - Run ID: {mlflow.active_run().info.run_id}")

if __name__ == "__main__":
    main()
