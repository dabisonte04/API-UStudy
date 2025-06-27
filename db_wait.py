import time
import pymysql
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # If dotenv is not available, continue without it
    pass

DB_HOST = os.getenv("MYSQL_HOST", "db")
DB_USER = os.getenv("MYSQL_USER", "")
DB_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
DB_NAME = os.getenv("MYSQL_DATABASE", "")
DB_PORT = int(os.getenv("MYSQL_PORT", 3306))

def wait_for_mysql():
    while True:
        try:
            conn = pymysql.connect(
                host=DB_HOST,
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME,
                port=DB_PORT
            )
            conn.close()
            print("✅ MySQL is up and running!")
            break
        except pymysql.MySQLError as e:
            print("⏳ Waiting for MySQL to be ready...")
            time.sleep(2)

if __name__ == "__main__":
    wait_for_mysql()
