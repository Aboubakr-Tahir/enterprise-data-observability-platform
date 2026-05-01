FROM apache/airflow:2.10.0-python3.9

USER root
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
         build-essential \
  && apt-get autoremove -yqq --purge \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

USER airflow
# Pin exact versions to skip the complex resolution tree
RUN pip install --no-cache-dir \
    "dbt-core==1.8.2" \
    "dbt-postgres==1.8.2" \
    "great-expectations==0.18.12" \
    "apache-airflow-providers-openlineage==1.10.0"
