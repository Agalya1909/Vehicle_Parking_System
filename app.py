from flask import Flask, render_template, request, redirect, session
import sqlite3
import os
from datetime import datetime
import math

app = Flask(__name__)
app.secret_key = 'super-secret-key'

def get_db_connection():
    conn = sqlite3.connect('database/users.db')
    conn.row_factory = sqlite3.Row
    return conn

# ---------------------- User Routes ----------------------

@app.route('/')
def home():
    return render_template('user/user_login.html')

@app.route('/user_register', methods=['GET', 'POST'])
def user_register():
    if request.method == 'POST':
        username = request.form['full_name']
        password = request.form['password']
        pincode = request.form['pincode']
        address = request.form['address']
        email = request.form['email']
        conn = get_db_connection()
        try:
            conn.execute(
                'INSERT INTO users (full_name, password, address, pincode, email) VALUES (?, ?, ?, ?, ?)',
                (username, password, address, pincode, email)
            )
            conn.commit()
            return redirect(url_for('user_login'))  # redirect to login after success
        except sqlite3.IntegrityError:
            return render_template('user/user_register.html', error="Username or email already exists.")
        finally:
            conn.close()
    return render_template('user/user_register.html')


@app.route('/user_login', methods=['GET', 'POST'])
def user_login():
    if request.method == 'GET':
        return render_template('user/user_login.html')

    username = request.form['username']
    password = request.form['password']
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE full_name=? AND password=?', (username, password)).fetchone()
    conn.close()
    if user:
        session['user_id'] = user['id']
        return redirect(url_for('user_dashboard'))
    return render_template('user/user_login.html', error="Invalid username or password.")



@app.route('/user_dashboard')
def user_dashboard():
    if 'user_id' not in session:
        return redirect('/')

    conn = get_db_connection()

    user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()

    parking_history = conn.execute('''
    SELECT b.id, p.prime_location_name AS location, b.vehicle_no, b.timestamp, b.active, p.price
    FROM bookings b
    JOIN parking_lots p ON b.parking_lot_id = p.id
    WHERE b.user_id = ?
    ORDER BY b.timestamp DESC
''', (user['id'],)).fetchall()



    conn.close()

    return render_template(
    'user/user_dashboard.html',
    user=dict(user),
    parking_history=[dict(row) for row in parking_history]
)


@app.route("/user_summary")
def user_summary():
    if "user_id" not in session:
        return redirect("/")

    user_id = session["user_id"]
    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch user data
    user = cursor.execute(
        "SELECT * FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()

    # Fetch booking count per parking lot
    rows = cursor.execute(
        """
        SELECT parking_lots.prime_location_name AS lot_name,
               COUNT(bookings.id) AS booking_count
        FROM bookings
        JOIN parking_lots ON bookings.parking_lot_id = parking_lots.id
        WHERE bookings.user_id = ?
        GROUP BY bookings.parking_lot_id
        ORDER BY booking_count DESC
        """,
        (user_id,)
    ).fetchall()

    conn.close()

    lot_labels = [row["lot_name"] for row in rows]
    lot_counts = [row["booking_count"] for row in rows]

    return render_template(
        "user/user_summary.html",
        lot_labels=lot_labels,
        lot_counts=lot_counts,
        user=user  # ✅ Pass user to the template
    )




@app.route('/search_parking', methods=['GET'])
def search_parking():
    if 'user_id' not in session:
        return redirect('/')

    search_query = request.args.get('query', '').strip()
    conn = get_db_connection()

    try:
        int_val = int(search_query)
        raw_results = conn.execute('''
            SELECT id, prime_location_name, price, address, availability 
            FROM parking_lots
            WHERE id = ? OR pin_code = ?
        ''', (int_val, int_val)).fetchall()
    except ValueError:
        raw_results = conn.execute('''
            SELECT id, prime_location_name, price, address, availability 
            FROM parking_lots
            WHERE pin_code = ? OR lower(prime_location_name) LIKE ?
        ''', (search_query, '%' + search_query.lower() + '%')).fetchall()

    # Add next_spot_id to each parking lot
    results = []
    for row in raw_results:
        lot = dict(row)
        # Fetch capacity and booked spots
        lot_data = conn.execute("SELECT maximum_number_of_spots FROM parking_lots WHERE id = ?", (lot['id'],)).fetchone()
        capacity = lot_data['maximum_number_of_spots']

        booked_spots = conn.execute("SELECT spot_id FROM bookings WHERE parking_lot_id = ? AND active = 1", (lot['id'],)).fetchall()
        booked_ids = {row['spot_id'] for row in booked_spots}

# Get list of available spot IDs
        lot['available_spots'] = [i for i in range(1, capacity + 1) if i not in booked_ids]

        results.append(lot)

    # Fetch logged-in user info
    user = conn.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],)).fetchone()

    # Fetch user's parking history
    parking_history = conn.execute('''
        SELECT b.id, p.prime_location_name AS location, b.vehicle_no, b.timestamp, b.active
        FROM bookings b
        JOIN parking_lots p ON b.parking_lot_id = p.id
        WHERE b.user_id = ?
        ORDER BY b.timestamp DESC
    ''', (user['id'],)).fetchall()

    conn.close()

    return render_template(
        'user/user_dashboard.html',
        user=dict(user),
        parking_history=[dict(row) for row in parking_history],
        search_results=results,
        query=search_query
    )



@app.route('/user/user_edit_profile', methods=['GET', 'POST'])
def user_edit_profile():
    if 'user_id' not in session:
        return redirect('/')

    conn = get_db_connection()
    user_id = session['user_id']

    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    if request.method == 'POST':
        full_name = request.form['full_name']
        email = request.form['email']
        password = request.form['password']
        address = request.form['address']
        pincode = request.form['pincode']

        conn.execute("""
            UPDATE users
            SET full_name = ?, email = ?, password = ?, address = ?, pincode = ?
            WHERE id = ?
        """, (full_name, email, password, address, pincode, user_id))
        conn.commit()
        conn.close()
        return redirect(url_for('user_dashboard'))

    conn.close()
    return render_template('user/user_edit_profile.html', user=user)

@app.route('/book_lot/<int:lot_id>', methods=['POST'])
def book_lot(lot_id):
    if 'user_id' not in session:
        return redirect('/')
    conn = get_db_connection()
    vehicle_no = request.form['vehicle_no']
    user_id = session['user_id']
    cur = conn.cursor()
    cur.execute("SELECT availability FROM parking_lots WHERE id = ?", (lot_id,))
    lot = cur.fetchone()
    if lot and lot['availability'] > 0:
        spot_id = request.form['spot_id']
        cur.execute("SELECT price FROM parking_lots WHERE id = ?", (lot_id,))
        price = cur.fetchone()['price']
        cur.execute("""
            INSERT INTO bookings (spot_id, parking_lot_id, user_id, vehicle_no, timestamp, active, estimated_cost)
            VALUES (?, ?, ?, ?, datetime('now'), 1, 0)
        """, (spot_id, lot_id, user_id, vehicle_no))
        cur.execute("UPDATE parking_lots SET availability = availability - 1 WHERE id = ?", (lot_id,))
        conn.commit()
        flash("Booking successful!", "success")
    else:
        flash("No availability for this parking lot.", "error")
    conn.close()
    return redirect(url_for('user_dashboard'))

@app.route("/release_booking/<int:booking_id>", methods=["POST"])
def release_booking(booking_id):
    if "user_id" not in session:
        return redirect("/")
    conn = get_db_connection()
    booking = conn.execute(
        """
        SELECT b.parking_lot_id, b.timestamp, p.price
        FROM bookings b
        JOIN parking_lots p ON b.parking_lot_id = p.id
        WHERE b.id = ? AND b.user_id = ?
        """,
        (booking_id, session["user_id"]),
    ).fetchone()
    if booking:
        start_time = datetime.fromisoformat(booking["timestamp"])
        now = datetime.now()
        duration_hours = max(1, math.ceil((now - start_time).total_seconds() / 3600))
        estimated_cost = round(duration_hours * booking["price"], 2)
        conn.execute(
            """
            UPDATE bookings
            SET active = 0, estimated_cost = ?
            WHERE id = ? AND user_id = ?
            """,
            (estimated_cost, booking_id, session["user_id"]),
        )
        conn.execute(
            """
            UPDATE parking_lots
            SET availability = availability + 1
            WHERE id = ?
            """,
            (booking["parking_lot_id"],),
        )
        conn.commit()
    conn.close()
    return redirect(url_for("user_dashboard"))



# ---------------------- Admin Routes ----------------------

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection()
        admin = conn.execute('SELECT * FROM admin WHERE username=? AND password=?', (username, password)).fetchone()
        conn.close()
        if admin:
            session['admin_id'] = admin['id']
            return redirect('/admin_dashboard')
        return "Invalid admin credentials."
    return render_template('admin/admin_login.html')

from flask import render_template, request, redirect, session, flash, url_for

@app.route('/admin/edit_profile', methods=['GET', 'POST'])
def edit_profile():
    if 'admin_id' not in session:
        flash("Login required", "warning")
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    admin_id = session['admin_id']

    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        conn.execute("""
            UPDATE admin
            SET username = ?, email = ?, password = ?
            WHERE id = ?
        """, (username, email, password, admin_id))
        conn.commit()
        flash('Profile updated successfully!', 'success')
        conn.close()
        return redirect(url_for('admin_dashboard'))

    # Do not render edit_profile.html anymore
    return redirect(url_for('admin_dashboard'))


@app.route('/admin_dashboard')
def admin_dashboard():
    if 'admin_id' not in session:
        return redirect('/')

    conn = get_db_connection()
    admin_id = session['admin_id']

    # ✅ Fetch current admin details for edit_profile modal
    admin = conn.execute("SELECT * FROM admin WHERE id = ?", (admin_id,)).fetchone()

    search_query = request.args.get('search_query')

    if search_query:
        try:
            int_val = int(search_query)
            lots = conn.execute('''
                SELECT * FROM parking_lots
                WHERE id = ? OR pin_code = ?
            ''', (int_val, int_val)).fetchall()
        except ValueError:
            lots = conn.execute('''
                SELECT * FROM parking_lots
                WHERE prime_location_name LIKE ?
            ''', ('%' + search_query + '%',)).fetchall()
    else:
        lots = conn.execute('SELECT * FROM parking_lots').fetchall()

    enriched_lots = []
    for lot in lots:
        capacity = lot['maximum_number_of_spots'] if lot['maximum_number_of_spots'] is not None else 0
        availability = lot['availability'] if lot['availability'] is not None else 0
        occupied = capacity - availability

        bookings = conn.execute('SELECT * FROM bookings WHERE parking_lot_id=?', (lot['id'],)).fetchall()

        slots = []
        for booking in bookings:
            if booking['active'] == 1:
                slots.append({
            'id': booking['id'],  # Booking ID
            'slot_id': booking['spot_id'],  # Actual slot ID
            'occupied': True,
            'user_id': booking['user_id'],
            'vehicle_no': booking['vehicle_no'],
            'timestamp': booking['timestamp'],
            'cost': booking['estimated_cost'] if booking['estimated_cost'] is not None else lot['price']
        })




        for _ in range(capacity - len(slots)):
            slots.append({
                'id': None,
                'occupied': False
            })

        enriched_lots.append({
            'id': lot['id'],
            'prime_location_name': lot['prime_location_name'],
            'address': lot['address'],
            'pin_code': lot['pin_code'],
            'price': lot['price'],
            'capacity': capacity,
            'occupied': occupied,
            'slots': slots
        })

    users = conn.execute('SELECT * FROM users').fetchall()
    conn.close()

    return render_template(
    'admin/admin_dashboard.html',
    parking_lots=enriched_lots,
    users=users,
    admin=admin,
    current_time=datetime.now()  # ✅ Include current timestamp
)




@app.route('/delete_available_slot', methods=['POST'])
def delete_available_slot():
    if 'admin_id' not in session:
        return redirect('/')

    lot_id = int(request.form['lot_id'])
    slot_index = int(request.form['slot_index'])

    conn = get_db_connection()

    # Get current availability and capacity
    lot = conn.execute("SELECT availability, maximum_number_of_spots FROM parking_lots WHERE id = ?", (lot_id,)).fetchone()

    if lot and lot['availability'] > 0:
        # Decrement both availability and capacity (we simulate "slot removal")
        conn.execute('''
            UPDATE parking_lots
            SET availability = availability - 1,
                maximum_number_of_spots = maximum_number_of_spots - 1
            WHERE id = ? AND availability > 0
        ''', (lot_id,))
        conn.commit()

    conn.close()
    return redirect(url_for('admin_dashboard'))


@app.route('/create_parking_lot', methods=['POST'])
def create_parking_lot():
    if 'admin_id' not in session:
        return redirect('/')
    data = request.form
    spots = int(data['spots'])
    conn = get_db_connection()
    conn.execute('''
        INSERT INTO parking_lots (prime_location_name, price, address, pin_code, maximum_number_of_spots, availability)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (data['location'], data['price'], data['address'], data['pin_code'], spots, spots))
    conn.commit()
    conn.close()
    return redirect('/admin_dashboard')


@app.route('/edit_lot', methods=['POST'])
def edit_lot():
    if 'admin_id' not in session:
        return redirect('/')

    lot_id = request.form['lot_id']
    location = request.form['location']
    address = request.form['address']
    pin_code = request.form['pin_code']
    price = request.form['price']
    spots = request.form['spots']

    conn = get_db_connection()
    conn.execute('''
        UPDATE parking_lots
        SET prime_location_name=?, address=?, pin_code=?, price=?, maximum_number_of_spots=?
        WHERE id=?
    ''', (location, address, pin_code, price, spots, lot_id))
    conn.commit()
    conn.close()
    return redirect('/admin_dashboard')

@app.route('/view_users')
def view_users():
    if 'admin_id' not in session:
        return redirect('/')
    conn = get_db_connection()
    users = conn.execute('SELECT * FROM users').fetchall()
    conn.close()
    return render_template('admin/view_users.html', users=users)

@app.route('/admin/search', methods=['GET','POST'])
def search_parking_lots():
    if 'admin_id' not in session:
        return redirect('/')

    search_query = request.form.get('search_query', '').strip()
    conn = get_db_connection()

    try:
        # If the query is numeric, search ID and pin_code
        int_val = int(search_query)
        results = conn.execute('''
            SELECT * FROM parking_lots
            WHERE id = ? OR pin_code = ?
        ''', (int_val, int_val)).fetchall()
    except ValueError:
        # Otherwise, search by location
        results = conn.execute('''
            SELECT * FROM parking_lots
            WHERE lower(prime_location_name) LIKE ?
        ''', ('%' + search_query.lower() + '%',)).fetchall()

    conn.close()
    return render_template('admin/search.html', parking_lots=results)

import matplotlib.pyplot as plt
import io
import base64
from flask import render_template

@app.route("/admin/summary")
def summary_page():
    if "admin_id" not in session:
        return redirect("/")

    conn = get_db_connection()

    revenues = conn.execute("""
        SELECT p.prime_location_name, 
               IFNULL(SUM(b.estimated_cost), 0) as revenue
        FROM parking_lots p
        LEFT JOIN bookings b ON p.id = b.parking_lot_id
        GROUP BY p.id
    """).fetchall()

    occupancy = conn.execute("""
        SELECT prime_location_name,
               maximum_number_of_spots AS total,
               availability,
               (maximum_number_of_spots - availability) AS occupied
        FROM parking_lots
    """).fetchall()

    admin = conn.execute(
        "SELECT * FROM admin WHERE id = ?", (session["admin_id"],)
    ).fetchone()
    conn.close()

    revenue_labels = [row["prime_location_name"] for row in revenues]
    revenue_values = [row["revenue"] for row in revenues]

    occupancy_labels = [row["prime_location_name"] for row in occupancy]
    available_values = [row["availability"] for row in occupancy]
    occupied_values = [row["occupied"] for row in occupancy]

    return render_template(
        "admin/summary.html",
        revenue_labels=revenue_labels,
        revenue_values=revenue_values,
        occupancy_labels=occupancy_labels,
        available_values=available_values,
        occupied_values=occupied_values,
        admin=admin,
    )


@app.route('/delete_user/<int:user_id>')
def delete_user(user_id):
    if 'admin_id' not in session:
        return redirect('/')
    conn = get_db_connection()
    conn.execute('DELETE FROM users WHERE id=?', (user_id,))
    conn.commit()
    conn.close()
    return redirect('/admin_dashboard')

@app.route('/delete_lot/<int:lot_id>')
def delete_lot(lot_id):
    if 'admin_id' not in session:
        return redirect('/')
    conn = get_db_connection()
    conn.execute('DELETE FROM parking_lots WHERE id=?', (lot_id,))
    conn.commit()
    conn.close()
    return redirect('/admin_dashboard')

# ---------------------- Logout ----------------------

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# ---------------------- Main ----------------------

if __name__ == '__main__':
    if not os.path.exists('database/users.db'):
        print("Please run database_setup.py first to initialize the database.")
    else:
        app.run(debug=True)
