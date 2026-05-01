import os

# Database configuration
SQLALCHEMY_DATABASE_URI = os.getenv(
    "SUPERSET_SQLALCHEMY_DATABASE_URI",
    "postgresql+psycopg2://airflow:airflow@postgres/airflow"
)

SECRET_KEY = os.getenv("SUPERSET_SECRET_KEY", "db_secret_key_12345")

# Flask-WTF flag for CSRF
WTF_CSRF_ENABLED = True

# Set this API key to enable Mapbox visualizations
MAPBOX_API_KEY = ''

# Path to the directory where the database is stored (for SQLite, not used here)
DATA_DIR = "/app/superset_home"

# Superset logs
# LOG_LEVEL = "DEBUG"
