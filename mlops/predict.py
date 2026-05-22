import pandas as pd
import numpy as np
import mlflow
import mlflow.sklearn
import mlflow.keras
import os
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

def main():
    # MLflow tracking server
    mlflow.set_tracking_uri("http://localhost:5050")
    
    # 1. Chargement du nouveau batch de features à analyser
    features_path = '/home/aboubakr/Desktop/enterprise-data-observability-platform/csv_denormalisation/ml_ready_transactions.csv'
    metadata_path = '/home/aboubakr/Desktop/enterprise-data-observability-platform/csv_denormalisation/ml_metadata.csv'
    
    if not os.path.exists(features_path):
        raise FileNotFoundError(f"Features CSV not found: {features_path}")
    if not os.path.exists(metadata_path):
        raise FileNotFoundError(f"Metadata CSV not found: {metadata_path}")
    
    print("Chargement des features et métadonnées...")
    df_features = pd.read_csv(features_path, index_col='TransactionID')
    df_metadata = pd.read_csv(metadata_path, index_col='TransactionID')
    
    X = df_features.values

    # 2. Récupération des modèles et du seuil depuis MLflow
    # Pour trouver le run_id, regarde l'UI MLflow ou utilise la dernière expérience
    print("Récupération des modèles depuis MLflow...")
    
    experiment = mlflow.get_experiment_by_name("Bank_Fraud_Anomaly_Detection")
    if experiment is None:
        raise ValueError("L'expérience 'Bank_Fraud_Anomaly_Detection' n'existe pas. Exécute d'abord train.py")
    
    # Récupérer le dernier run réussi
    runs = mlflow.search_runs(
        experiment_ids=[experiment.experiment_id],
        order_by=["start_time DESC"],
        max_results=1,
    )
    if len(runs) == 0:
        raise ValueError("Aucun run trouvé dans l'expérience MLflow. Exécute d'abord train.py")
    
    run_id = runs.iloc[0]['run_id']
    print(f"Utilisation du Run ID: {run_id}")
    
    try:
        iso_forest = mlflow.sklearn.load_model(f"runs:/{run_id}/isolation_forest_model")
        autoencoder = mlflow.keras.load_model(f"runs:/{run_id}/autoencoder_model")
        
        # Charger le seuil (récupéré manuellement depuis le run)
        client = mlflow.tracking.MlflowClient()
        artifacts = client.list_artifacts(run_id)
        
        threshold = None
        for artifact in artifacts:
            if artifact.path == 'threshold.txt':
                threshold_path = client.download_artifacts(run_id, 'threshold.txt')
                with open(threshold_path, 'r') as f:
                    threshold = float(f.read().strip())
                break
        
        if threshold is None:
            # Fallback: récupérer de la métrique
            threshold = runs.iloc[0]['metrics.anomaly_threshold_99th_percentile']
        
        print(f"Seuil utilisé: {threshold:.4f}")
        
    except Exception as e:
        print(f"Erreur lors du chargement des modèles: {e}")
        raise

    # 3. Calcul de l'inférence
    print("Calcul des scores d'anomalie...")
    
    if_scores = -iso_forest.decision_function(X)
    if_scores_norm = (if_scores - if_scores.min()) / (if_scores.max() - if_scores.min() + 1e-6)
    
    X_pred = autoencoder.predict(X, verbose=0)
    ae_mse = np.mean(np.power(X - X_pred, 2), axis=1)
    ae_scores_norm = (ae_mse - ae_mse.min()) / (ae_mse.max() - ae_mse.min() + 1e-6)
    
    final_scores = (0.5 * if_scores_norm) + (0.5 * ae_scores_norm)

    # 4. Construction de la table finale scorée (Rattachement par Index)
    print("Construction du rapport final...")
    
    results_df = pd.DataFrame(index=df_features.index)
    results_df['anomaly_score'] = final_scores
    results_df['is_anomaly'] = (results_df['anomaly_score'] >= threshold).astype(int)
    results_df['threshold_used'] = threshold
    
    # Jointure avec les métadonnées (L'identité du client réapparaît !)
    final_output = results_df.join(df_metadata, how='inner')
    
    # Sauvegarde pour la couche Silver Scored
    output_path = '/home/aboubakr/Desktop/enterprise-data-observability-platform/csv_denormalisation/silver_scored_output.csv'
    final_output.to_csv(output_path, index=True)
    
    # Statistiques
    n_anomalies = (final_output['is_anomaly'] == 1).sum()
    print(f"✓ Inférence terminée !")
    print(f"  - Total transactions: {len(final_output)}")
    print(f"  - Anomalies détectées: {n_anomalies} ({100*n_anomalies/len(final_output):.2f}%)")
    print(f"  - Fichier de sortie: {output_path}")

if __name__ == "__main__":
    main()
