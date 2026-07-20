import sqlite3

conn = sqlite3.connect(r"D:\ParcelFleet\instance\parcelfleet.db")
cursor = conn.cursor()

# Show all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
print("\n" +str(cursor.fetchall())+ "\n")
print("Delivery image updated successfully.")
# Read data from a table

# Read data from a table
cursor.execute("SELECT * FROM parcels;")
rows = cursor.fetchall()
print("\n" + str(rows) + "\n")

conn.close()