import streamlit as st
import pymysql
import pandas as pd

# --- 🔧 USER CONFIGURATION (MUST MATCH SENSOR SCRIPT) ---
BUCKET_HEIGHT_CM = 30.0
SENSOR_OFFSET_CM = 5.0
# --------------------------------------------------------

DB_CONFIG = {
    'host': 'tpalley.mooo.com',
    'user': 'labuser',
    'password': 'labuser123&',
    'database': 'EmbeddedLab'
}


def get_connection():
    return pymysql.connect(**DB_CONFIG)


def fetch_data():
    conn = get_connection()
    try:
        # Fetch latest data
        return pd.read_sql("SELECT timestamp, distance FROM WaterSensor ORDER BY timestamp ASC", conn)
    finally:
        conn.close()


st.set_page_config(page_title="Bucket Monitor", layout="wide")
st.title("🪣 Smart Bucket Monitor")

# --- DATA PROCESSING ---
df = fetch_data()

if not df.empty:
    latest = df.iloc[-1]
    curr_dist = latest['distance']

    # Calculate Water Height & Percentage
    # Formula: Water = (Bucket + Offset) - Sensor_Reading
    water_height = (BUCKET_HEIGHT_CM + SENSOR_OFFSET_CM) - curr_dist
    fill_pct = (water_height / BUCKET_HEIGHT_CM) * 100

    # --- 🚨 WARNING LOGIC 🚨 ---

    # 1. RED WARNING (Overflow)
    if fill_pct >= 100:
        st.error(f"🚨 CRITICAL WARNING: OVERFLOW DETECTED! (Level: {fill_pct:.1f}%)")
        st.toast("Bucket is Overflowing!", icon="🚨")

    # 2. ORANGE WARNING (Almost Full)
    elif fill_pct >= 90:
        st.warning(f"⚠️ HIGH LEVEL WARNING: Capacity is at {fill_pct:.1f}%")
        st.toast("Bucket is reaching capacity.", icon="⚠️")

    else:
        st.success(f"Status Normal: {fill_pct:.1f}% Full")

    # --- METRICS & CHARTS ---
    col1, col2, col3 = st.columns(3)
    col1.metric("Water Level", f"{water_height:.1f} cm")
    col2.metric("Fill Percentage", f"{fill_pct:.1f} %")
    col3.metric("Space Remaining", f"{(BUCKET_HEIGHT_CM - water_height):.1f} cm")

    # Visualization
    st.divider()

    # Create a computed 'fill_percentage' column for the graph
    df['water_height'] = (BUCKET_HEIGHT_CM + SENSOR_OFFSET_CM) - df['distance']
    df['fill_pct'] = (df['water_height'] / BUCKET_HEIGHT_CM) * 100

    st.subheader("Fill Percentage History")

    # Add reference lines for 90% and 100%
    chart_data = df.set_index('timestamp')['fill_pct']
    st.line_chart(chart_data)

else:
    st.info("No data available yet.")

# Manual Refresh
if st.button("Refresh Status"):
    st.rerun()