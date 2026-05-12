# Guide de Configuration Superset

Ce guide explique comment connecter Apache Superset à l'entrepôt de données Postgres et visualiser les résultats de Great Expectations.

## 1. Connexion à la Base de Données

1.  Accédez à Superset : `http://localhost:8088` (admin/admin).
2.  Allez dans **Settings** -> **Database Connections**.
3.  Cliquez sur **+ DATABASE**.
4.  Sélectionnez **PostgreSQL**.
5.  Utilisez l'URL SQLAlchemy suivante :
    ```text
    postgresql://airflow:airflow@postgres:5432/warehouse
    ```
6.  Testez la connexion et enregistrez.

## 2. Création du Dataset de Qualité de Données

1.  Allez dans le menu **Datasets**.
2.  Cliquez sur **+ DATASET**.
3.  Sélectionnez la base connectée, le schéma `public`, et la table `ge_metadata.ge_validations_store`.
4.  Cliquez sur **ADD**.

## 3. Analyse des Résultats (SQL Lab)

Les résultats de Great Expectations sont stockés au format JSON dans la colonne `value`. Pour faciliter la visualisation, il est recommandé de créer un **Virtual Dataset** via le **SQL Lab** avec la requête suivante :

```sql
SELECT 
    key_name as suite_name,
    CASE 
        WHEN (value::json->'success')::text = 'true' THEN 'Succès' 
        ELSE 'Échec' 
    END as status,
    (value::json->'statistics'->>'success_percent')::float as success_rate,
    (value::json->'run_id'->>'run_time')::timestamp as validation_time
FROM "ge_metadata.ge_validations_store"
```

## 4. Dépannage : Pilote Postgres manquant

Si vous recevez l'erreur `Could not load database driver: PostgresEngineSpec`, exécutez la commande suivante sur votre machine hôte pour réinstaller le pilote dans l'environnement virtuel du container :

```bash
docker exec -u root prjt_bi_hrimech-superset-1 pip install --target=/app/.venv/lib/python3.10/site-packages psycopg2-binary
docker restart prjt_bi_hrimech-superset-1
```
