
import sqlite3  # Built-in SQLite module

DB_PATH = "traffic_sim.db"  # Database file name

def get_connection():
	"""Create and return a SQLite connection with WAL and foreign keys enabled."""
	conn = sqlite3.connect(DB_PATH)
	# Enable WAL journal mode for better read performance
	conn.execute("PRAGMA journal_mode=WAL;")
	# Enable foreign key support
	conn.execute("PRAGMA foreign_keys=ON;")
	return conn
