import sqlite3

# Connect to the database (will create it if it doesn't exist)
conn = sqlite3.connect('database/users.db')
cursor = conn.cursor()

# Users Table
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL
)
''')

# Admin Table
cursor.execute('''
CREATE TABLE IF NOT EXISTS admin (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    password TEXT NOT NULL
)
''')

# Insert default admin if not exists
cursor.execute("SELECT * FROM admin WHERE username = 'admin'")
if not cursor.fetchone():
    cursor.execute("INSERT INTO admin (username, password) VALUES (?, ?)", ('admin', 'admin123'))

# Parking Lots Table
cursor.execute('''
CREATE TABLE IF NOT EXISTS parking_lots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prime_location_name TEXT NOT NULL,
    price REAL NOT NULL,
    address TEXT,
    pin_code TEXT,
    maximum_number_of_spots INTEGER NOT NULL
)
''')

# Parking Spots Table
cursor.execute('''
CREATE TABLE IF NOT EXISTS parking_spots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lot_id INTEGER,
    status TEXT CHECK(status IN ('A', 'O')) DEFAULT 'A',
    FOREIGN KEY (lot_id) REFERENCES parking_lots(id)
)
''')

# Reservations Table
cursor.execute('''
CREATE TABLE IF NOT EXISTS reservations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spot_id INTEGER,
    user_id INTEGER,
    parking_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    leaving_timestamp DATETIME,
    parking_cost REAL,
    FOREIGN KEY (spot_id) REFERENCES parking_spots(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
)
''')

conn.commit()
conn.close()

print("Database initialized successfully.")
