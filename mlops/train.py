import pandas as pd
import numpy as np
import os
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import MinMaxScaler
import tensorflow as tf
from tensorflow.keras import layers, models
import mlflow
import mlflow.sklearn
import mlflow.keras
import warnings
warnings.filterwarnings('ignore')

# 1. Configuration de MLflow
mlflow.set_tracking_uri("http://localhost:5050")
# Ensure the experiment uses the mounted artifact root inside the mlflow container
from mlflow.tracking import MlflowClient
import time
client = MlflowClient()
_base_exp_name = "Bank_Fraud_Anomaly_Detection"
# Use the repository absolute path so host and container refer to the same location
_artifact_root = f"file://{os.path.join(os.getcwd(), 'mlruns')}"

try:
    existing_exp = client.get_experiment_by_name(_base_exp_name)
    
    # Check if experiment exists and is deleted
    if existing_exp is not None and existing_exp.lifecycle_stage == 'deleted':
        print(f"Restoring deleted experiment: {_base_exp_name}")
        # Restore the deleted experiment
        client.restore_experiment(existing_exp.experiment_id)
        mlflow.set_experiment(_base_exp_name)
    elif existing_exp is None:
        print(f"Creating new experiment: {_base_exp_name}")
        client.create_experiment(_base_exp_name, artifact_location=_artifact_root)
        mlflow.set_experiment(_base_exp_name)
    else:
        # Experiment exists and is active
        if existing_exp.artifact_location.startswith("file:///app") or existing_exp.artifact_location.startswith("/app"):
            # Old non-writable path; create a new experiment with timestamp suffix
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
        # Last resort: use a simple default
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
    data_path = '/home/aboubakr/Desktop/enterprise-data-observability-platform/csv_denormalisation/ml_ready_transactions.csv'
    
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
        # decision_function renvoie des valeurs négatives pour les anomalies, on inverse.
        if_scores = -iso_forest.decision_function(X)
        if_scores_norm = (if_scores - if_scores.min()) / (if_scores.max() - if_scores.min() + 1e-6)

        print("Entraînement de l'Autoencoder (Réseau de Neurones)...")
        # Hyperparamètres de l'Autoencoder
        ae_epochs = 20
        ae_batch_size = 64
        
        mlflow.log_param("ae_epochs", ae_epochs)
        mlflow.log_param("ae_batch_size", ae_batch_size)
        
        autoencoder = build_autoencoder(input_dim)
        autoencoder.fit(
            X, X,  # L'Autoencoder apprend à reconstruire sa propre entrée (X)
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
        # Équation d'ensemble pondérée (50% IF / 50% Autoencoder)
        final_scores = (0.5 * if_scores_norm) + (0.5 * ae_scores_norm)
        
        # Définition métier du seuil critique (99ème percentile du dataset propre)
        threshold_99 = np.percentile(final_scores, 99)
        mlflow.log_metric("anomaly_threshold_99th_percentile", threshold_99)
        print(f"Seuil critique d'anomalie: {threshold_99:.4f}")

        # 4. Enregistrement des modèles dans le Feature Store MLflow
        print("Logging des artefacts dans MLflow...")
        mlflow.sklearn.log_model(iso_forest, "isolation_forest_model")
        mlflow.keras.log_model(autoencoder, "autoencoder_model")
        
        # Sauvegarder aussi le seuil comme artefact texte
        with open('/tmp/threshold.txt', 'w') as f:
            f.write(str(threshold_99))
        mlflow.log_artifact('/tmp/threshold.txt')
        
        print(f"✓ Entraînement MLOps terminé ! Vérifiez http://localhost:5050")
        print(f"  - Run ID: {mlflow.active_run().info.run_id}")

if __name__ == "__main__":
    main()
