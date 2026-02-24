import RPi.GPIO as GPIO
import time
import pymysql
from datetime import datetime

# --- CONFIGURATION ---
BUCKET_HEIGHT_CM = 10.0
SENSOR_OFFSET_CM = 5.0

DB_CONFIG = {
    'host': '127.0.0.1',
    'user': 'user1234',
    'password': 'yesuser',
    'database': 'mybucket'
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
    GPIO.output(TRIG, False)
    time.sleep(0.05)
    
    GPIO.output(TRIG, True)
    time.sleep(0.00001)
    GPIO.output(TRIG, False)

    start_time, stop_time = time.time(), time.time()
    timeout = start_time + 0.1

    while GPIO.input(ECHO) == 0:
        start_time = time.time()
        if start_time > timeout: return 0.0

    while GPIO.input(ECHO) == 1:
        stop_time = time.time()
        if stop_time > timeout: return 0.0

    return ((stop_time - start_time) * 34300) / 2

def set_mode(seconds):
    try:
        conn = get_connection()
        with conn.cursor() as cursor:
            cursor.execute("UPDATE DeviceSettings SET interval_seconds = %s WHERE id = 1", (seconds,))
        conn.commit()
        conn.close()
        print(f"Auto-Switch: Mode set to {seconds}s interval.")
    except Exception as e:
        pass

def get_sleep_interval():
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
last_water_height = None
last_time = None

try:
    while True:
        dist = get_distance()
        current_time = datetime.now()

        total_depth = BUCKET_HEIGHT_CM + SENSOR_OFFSET_CM
        water_height = total_depth - dist
        fill_pct = (water_height / BUCKET_HEIGHT_CM) * 100

        # Calculate Velocity
        if last_time is not None:
            time_diff = (current_time - last_time).total_seconds()
            velocity = (water_height - last_water_height) / time_diff if time_diff > 0 else 0.0
        else:
            velocity = 0.0
            
        last_water_height = water_height
        last_time = current_time

        current_interval = get_sleep_interval()

        # Auto-Mode Logic
        if fill_pct >= 100:
            if last_fill_pct >= 100 and current_interval != 3600:
                set_mode(3600)
            elif last_fill_pct < 100 and current_interval != 60:
                set_mode(60)
        elif fill_pct >= 90 and current_interval != 60:
            set_mode(60)

        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                sql = "INSERT INTO WaterSensor (timestamp, distance, velocity) VALUES (%s, %s, %s)"
                cursor.execute(sql, (current_time, dist, velocity))
            conn.commit()
        finally:
            conn.close()

        print(f"[{current_time.strftime('%H:%M:%S')}] Dist: {dist:.1f}cm | Height: {water_height:.1f}cm | Fill: {fill_pct:.1f}% | Vel: {velocity:.2f}cm/s | Mode: {current_interval}s")
        last_fill_pct = fill_pct

        # Smart Sleep: Wake up every 5 seconds to check if mode changed
        target_sleep = get_sleep_interval()
        checks = max(1, int(target_sleep / 5))
        
        for _ in range(checks):
            time.sleep(5)
            if get_sleep_interval() != target_sleep:
                print("Interrupt: New mode detected in database!")
                break

except KeyboardInterrupt:
    GPIO.cleanup()
