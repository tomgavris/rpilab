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
