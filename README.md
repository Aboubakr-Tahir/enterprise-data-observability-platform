# Data Quality Monitoring Framework

## 📌 Project Context

### The Problem
A company's Data & Analytics department (DSI) manages a data warehouse that feeds critical business decisions (reporting, customer dashboards, ML models). Without automated quality controls, data issues propagate silently:
- **Missing values** → incorrect KPIs
- **Duplicate records** → inflated metrics
- **Stale data** → outdated decisions
- **Format violations** → broken downstream applications

### The Solution
Build a **Data Observability framework** that continuously monitors data health, computes quality scores, traces data lineage, and provides real-time dashboards with alerts and basic self-healing capabilities.

---

## 🎯 Project Objectives

1. **Automated Testing** – Execute quality checks (nulls, uniqueness, patterns, freshness) using Great Expectations
2. **Quality Scoring** – Compute a daily health score (0–100%) per table/dataset
3. **Lineage Tracking** – Trace data origins and transformations using OpenLineage + Marquez
4. **Real-time Visualization** – Dashboard (Superset) with live metrics and alerts
5. **Advanced Features** – Anomaly detection on quality metrics + simple auto-remediation

---

## 🧱 Technology Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| Orchestration | Apache Airflow | Schedule & coordinate data pipelines |
| Data Transformation | dbt (Data Build Tool) | Transform raw data into analytics-ready models |
| Data Quality | Great Expectations (GX) | Define & execute data quality expectations |
| Lineage | OpenLineage + Marquez | Capture & visualize data lineage |
| Visualization | Apache Superset | Dashboard + real-time alerts |
| Metadata Storage | PostgreSQL | Store quality scores & lineage metadata |
| Anomaly Detection | Python (scipy/pandas) | Statistical detection of quality drops |
| Auto-remediation | Airflow branching | Simple corrective actions (reject batch, retry) |

---

## 🏗️ Architecture Overview
┌─────────────────────────────────────────────────────────────────┐
│ DATA SOURCES │
│ (PostgreSQL, Snowflake, BigQuery, S3, APIs...) │
└─────────────────────────┬───────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────────┐
│ AIRFLOW DAG │
│ ┌──────────┐ ┌──────────┐ ┌──────────────┐ │
│ │ dbt run │ -> │ GX tests │ -> │ Score calc │ │
│ └──────────┘ └──────────┘ └──────────────┘ │
│ │ │ │ │
│ ▼ ▼ ▼ │
│ OpenLineage Quality quality_scores │
│ events results (PostgreSQL) │
│ │ │ │ │
│ └──────────────┼──────────────────┘ │
│ ▼ │
│ [Marquez] │
│ (Lineage UI) │
└─────────────────────────────────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────────┐
│ DATA WAREHOUSE │
│ ┌────────────┐ ┌────────────┐ ┌──────────────┐ │
│ │ raw tables │→│ staging │→│ mart tables │ │
│ └────────────┘ └────────────┘ └──────────────┘ │
└─────────────────────────────────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────────┐
│ SUPERSET DASHBOARD │
│ - Quality score trends - Lineage graph (from Marquez) │
│ - Failed tests heatmap - Slack/email alerts │
│ - Freshness monitoring │
└─────────────────────────────────────────────────────────────────┘


---

## 📊 Quality Checks Definition

### 1. Null Checks
- **Expectation**: `expect_column_values_to_not_be_null`
- **Example**: Customer email should never be NULL
- **Threshold**: < 1% nulls for critical columns

### 2. Uniqueness Checks
- **Expectation**: `expect_column_values_to_be_unique`
- **Example**: Order ID must be unique
- **Threshold**: 100% uniqueness for primary keys

### 3. Pattern Checks (Regex)
- **Expectation**: `expect_column_values_to_match_regex`
- **Example**: Email format → `^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$`
- **Threshold**: > 99% compliance

### 4. Freshness Checks
- **Expectation**: `expect_column_max_to_be_between`
- **Example**: Last order date should be within last 24 hours
- **Threshold**: Max date >= CURRENT_DATE - 1 day

---

## 📈 Quality Score Formula

**Example weights**:
- Critical tables (Customer, Order): weight = 3
- Important tables (Product, Inventory): weight = 2
- Secondary tables (Logs, History): weight = 1

---

## 🔍 Anomaly Detection Strategy

### Method: Moving Average + Standard Deviation

```python
# 30-day rolling window
rolling_mean = score_history.rolling(30).mean()
rolling_std = score_history.rolling(30).std()

# Anomaly if score < mean - 2*std
if current_score < rolling_mean - 2 * rolling_std:
    trigger_alert()
    trigger_remediation()