import streamlit as st
import pymysql
import pandas as pd
import altair as alt
import time
from datetime import datetime, timedelta
import warnings

warnings.filterwarnings('ignore')

# --- CONFIGURATION ---
BUCKET_HEIGHT_CM = 10.0
SENSOR_OFFSET_CM = 5.0

DB_CONFIG = {
    'host': '127.0.0.1',
    'user': 'user1234',
    'password': 'yesuser',
    'database': 'mybucket'
}

def get_connection():
    return pymysql.connect(**DB_CONFIG)

def fetch_data():
    conn = get_connection()
    try:
        df = pd.read_sql("SELECT timestamp, distance, velocity FROM WaterSensor ORDER BY timestamp ASC", conn)
        if not df.empty:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df['water_height'] = (BUCKET_HEIGHT_CM + SENSOR_OFFSET_CM) - df['distance']
            df['fill_pct'] = (df['water_height'] / BUCKET_HEIGHT_CM) * 100
            
            df['water_height'] = df['water_height'].clip(lower=0)
            df['fill_pct'] = df['fill_pct'].clip(lower=0)
        return df
    finally:
        conn.close()

def get_current_interval():
    try:
        conn = get_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT interval_seconds FROM DeviceSettings WHERE id = 1")
            result = cursor.fetchone()
            return result[0] if result else 60
    except:
        return 60
    finally:
        if 'conn' in locals() and conn.open: conn.close()

def update_interval(seconds):
    try:
        conn = get_connection()
        with conn.cursor() as cursor:
            cursor.execute("UPDATE DeviceSettings SET interval_seconds = %s WHERE id = 1", (seconds,))
        conn.commit()
        conn.close()
        return True
    except:
        return False

st.set_page_config(page_title="Bucket Monitor", layout="wide")
st.title("Smart Bucket Monitor")

# Initialize session state for the 10s cooldown buffer
if 'last_mode_change' not in st.session_state:
    st.session_state.last_mode_change = datetime.min

# Fetch data first so we can check if the system is verifying an overflow
df = fetch_data()
fill_pct = df.iloc[-1]['fill_pct'] if not df.empty else 0.0
current_db_interval = get_current_interval()

# --- SIDEBAR CONTROLS ---
st.sidebar.header("Device Settings")

mode_options = {
    "Super Intense (Every 10 sec)": 10,
    "Intense (Every 1 min)": 60,
    "Power Saving (Every 1 hour)": 3600
}

labels = list(mode_options.keys())
default_index = 1 
for i, label in enumerate(labels):
    if mode_options[label] == current_db_interval:
        default_index = i

selected_label = st.sidebar.radio("Select Mode:", labels, index=default_index)

# Locking Logic
is_verifying_overflow = (fill_pct >= 100 and current_db_interval == 10)
time_since_change = (datetime.now() - st.session_state.last_mode_change).total_seconds()

if is_verifying_overflow:
    st.sidebar.error("🔒 **AUTOMATIC MODE**\n\nVerifying overflow. Manual controls are temporarily locked.")
elif time_since_change < 10:
    st.sidebar.warning(f"⏳ **Cooldown Active**\n\nPlease wait {int(10 - time_since_change)}s before changing modes again.")
else:
    if st.sidebar.button("Apply Settings"):
        sleep_time = mode_options[selected_label]
        if update_interval(sleep_time):
            st.session_state.last_mode_change = datetime.now()
            st.sidebar.success(f"Mode saved: {sleep_time} seconds!")
            time.sleep(1.5)  
            st.rerun()
        else:
            st.sidebar.error("Failed to update database.")

# --- MAIN DASHBOARD ---
if not df.empty:
    latest = df.iloc[-1]
    water_height = latest['water_height']

    tab1, tab2 = st.tabs(["Dashboard", "Raw Data Export"])

    with tab1:
        if fill_pct >= 100:
            st.error(f"CRITICAL WARNING: OVERFLOW DETECTED! (Level: {fill_pct:.1f}%)")
        elif fill_pct >= 90:
            st.warning(f"HIGH LEVEL WARNING: Capacity is at {fill_pct:.1f}%")
        else:
            st.success(f"Status Normal: {fill_pct:.1f}% Full")

        col1, col2, col3 = st.columns(3)
        col1.metric("Water Level", f"{water_height:.1f} cm")
        col2.metric("Fill Percentage", f"{fill_pct:.1f} %")
        col3.metric("Space Remaining", f"{(BUCKET_HEIGHT_CM - water_height):.1f} cm")

        st.divider()
        st.subheader("History Logs")
        time_filter = st.selectbox("Select Time Range:", ["Last 1 Hour", "Last 24 Hours", "All Time"])

        now = datetime.now()
        filtered_df = df.copy()
        
        if time_filter == "Last 1 Hour":
            domain_start = now - timedelta(hours=1)
            filtered_df = df[df['timestamp'] >= domain_start]
        elif time_filter == "Last 24 Hours":
            domain_start = now - timedelta(hours=24)
            filtered_df = df[df['timestamp'] >= domain_start]
        else:
            domain_start = df['timestamp'].min()

        if not filtered_df.empty:
            st.write("**Fill Percentage History**")
            fill_chart = alt.Chart(filtered_df).mark_line().encode(
                x=alt.X('timestamp:T', scale=alt.Scale(domain=[domain_start, now]), title="Time"),
                y=alt.Y('fill_pct:Q', title="Fill %")
            )
            st.altair_chart(fill_chart, use_container_width=True)
            
            st.write("**Water Velocity over Time**")
            vel_chart = alt.Chart(filtered_df).mark_line(color="#FF4B4B").encode(
                x=alt.X('timestamp:T', scale=alt.Scale(domain=[domain_start, now]), title="Time"),
                y=alt.Y('velocity:Q', title="Velocity (cm/s)")
            )
            st.altair_chart(vel_chart, use_container_width=True)
        else:
            st.info("No data recorded in the selected timeframe.")

        if st.button("Refresh Status"):
            st.rerun()

    with tab2:
        st.subheader("Sensor Database Export")
        export_df = df.copy()
        filter_mode = st.radio("Filter data by:", ["Time", "Number of Points"])
        
        if filter_mode == "Time":
            t_sel = st.selectbox("Select Time:", ["1 Hour", "24 Hours", "1 Week", "All Time"])
            if t_sel == "1 Hour":
                export_df = df[df['timestamp'] >= (datetime.now() - timedelta(hours=1))]
            elif t_sel == "24 Hours":
                export_df = df[df['timestamp'] >= (datetime.now() - timedelta(hours=24))]
            elif t_sel == "1 Week":
                export_df = df[df['timestamp'] >= (datetime.now() - timedelta(days=7))]
        else:
            p_sel = st.selectbox("Select Points:", ["Last 50", "Last 100", "Last 250", "Last 500"])
            num_pts = int(p_sel.split()[1])
            export_df = df.tail(num_pts)

        st.dataframe(export_df)
        csv = export_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Download data as CSV",
            data=csv,
            file_name='water_sensor_data.csv',
            mime='text/csv',
        )

else:
    st.info("No data available yet.")
    if st.button("Refresh Status"):
        st.rerun()
