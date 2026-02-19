import RPi.GPIO as GPIO
import time
import pymysql
from datetime import datetime

# --- 🔧 USER CONFIGURATION (CHANGE THESE) ---
BUCKET_HEIGHT_CM = 30.0  # The height of the bucket itself
SENSOR_OFFSET_CM = 5.0  # Distance from sensor to the top rim of the bucket
# --------------------------------------------

# --- DATABASE CONFIG ---
DB_CONFIG = {
    'host': 'tpalley.mooo.com',
    'user': 'labuser',
    'password': 'labuser123&',
    'database': 'EmbeddedLab'
}

# --- GPIO SETUP ---
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
TRIG, ECHO = 23, 24
GPIO.setup(TRIG, GPIO.OUT)
GPIO.setup(ECHO, GPIO.IN)


def get_connection():
    return pymysql.connect(**DB_CONFIG)


def get_distance():
    GPIO.output(TRIG, True)
    time.sleep(0.00001)
    GPIO.output(TRIG, False)

    start, stop = time.time(), time.time()
    while GPIO.input(ECHO) == 0: start = time.time()
    while GPIO.input(ECHO) == 1: stop = time.time()

    return ((stop - start) * 34300) / 2


def set_mode(seconds):
    """Updates the sleep interval in the database."""
    try:
        conn = get_connection()
        with conn.cursor() as cursor:
            # We update the setting so the dashboard also sees the change
            cursor.execute("UPDATE DeviceSettings SET interval_seconds = %s WHERE id = 1", (seconds,))
        conn.commit()
        conn.close()
        print(f"⚙️ Auto-Switch: Mode set to {seconds}s interval.")
    except Exception as e:
        print(f"Error setting mode: {e}")


def get_sleep_interval():
    """Reads the current sleep interval from the database."""
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


# --- MAIN LOOP ---
print(f"Starting Monitor. Bucket: {BUCKET_HEIGHT_CM}cm, Offset: {SENSOR_OFFSET_CM}cm")
last_fill_pct = 0.0

try:
    while True:
        # 1. Measure
        dist = get_distance()
        current_time = datetime.now()

        # 2. Calculate Water Logic
        # Total distance from sensor to bottom = Bucket Height + Offset
        total_depth = BUCKET_HEIGHT_CM + SENSOR_OFFSET_CM

        # Water Height = Total Depth - Measured Distance
        water_height = total_depth - dist

        # Calculate Percentage
        fill_pct = (water_height / BUCKET_HEIGHT_CM) * 100

        # 3. Automatic Mode Switching Logic
        current_interval = get_sleep_interval()

        # CASE A: Full or Overflowing (>= 100%)
        if fill_pct >= 100:
            print("🚨 Status: OVERFLOW/FULL")
            # If it was ALREADY full last time, we switch to Power Saving (1 hour)
            if last_fill_pct >= 100:
                if current_interval != 3600:
                    set_mode(3600)
                    # If it JUST became full, ensure we are in Intense mode to record this moment
            else:
                if current_interval != 60:
                    set_mode(60)

        # CASE B: Near Capacity (90% to 99%)
        elif fill_pct >= 90:
            print("⚠️ Status: >90% Warning")
            # Force Intense Mode
            if current_interval != 60:
                set_mode(60)

        # CASE C: Normal Operation (< 90%)
        # (We do nothing here, respecting whatever mode the user set manually)

        # 4. Save Data
        velocity = 0.0  # (Simplified for brevity, or add back your calc logic here)

        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                sql = "INSERT INTO WaterSensor (timestamp, distance, velocity) VALUES (%s, %s, %s)"
                cursor.execute(sql, (current_time, dist, velocity))
            conn.commit()
        finally:
            conn.close()

        print(f"Level: {fill_pct:.1f}% | Mode: {current_interval}s")

        last_fill_pct = fill_pct

        # 5. Sleep
        # Re-read interval in case we just changed it
        time.sleep(get_sleep_interval())

except KeyboardInterrupt:
    GPIO.cleanup()