import sqlite3

conn = sqlite3.connect(r"D:\ParcelFleet\instance\parcelfleet.db")
cursor = conn.cursor()

# Show all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
print("\n" +str(cursor.fetchall())+ "\n")

# Read data from a table
cursor.execute("SELECT * FROM drivers;")
rows = cursor.fetchall()
# Read data from a table
cursor.execute("SELECT * FROM users;")
rows = cursor.fetchall()
# Read data from a table
cursor.execute("SELECT * FROM parcels;")
rows = cursor.fetchall()
for row in rows:
    print(row)

conn.close()