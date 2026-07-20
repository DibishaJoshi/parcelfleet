import os
import random
import re
from datetime import datetime, timedelta
from io import BytesIO

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# Barcode & QR Code generators
import qrcode
import barcode
from barcode.writer import ImageWriter

# Models and Database
from models import db, User, Driver, Parcel, TrackingHistory, NotificationLog, Hub, HubAdmin

# Algorithms
from algorithms import HUBS, GRAPH, dijkstra, greedy_driver_assignment, get_route_coordinates, haversine_distance, get_closest_hub, get_route_segments, fetch_osrm_route, fetch_osrm_routes_with_alternatives, get_all_hubs_dict

def validate_phone(phone):
    if not phone:
        return False
    # Nepali mobile phone validation (e.g. 10 digits starting with 98/97/96)
    return bool(re.match(r"^9[678]\d{8}$", phone.strip()))

def validate_coords(lat, lng):
    # Bound to Kathmandu Valley coordinates box
    return 27.50 <= lat <= 27.90 and 85.10 <= lng <= 85.55

app = Flask(__name__)
app.config['SECRET_KEY'] = 'parcelfleet-secure-key-2026'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///parcelfleet.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Image Upload configurations
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB Max upload size

# Initialize Database
db.init_app(app)

# Initialize Login Manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- AUTHENTICATION ROUTES ---

@app.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.role == 'admin' or current_user.role == 'hub_admin':
            return redirect(url_for('admin_dashboard'))
        elif current_user.role == 'driver':
            return redirect(url_for('driver_dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = True if request.form.get('remember') else False
        
        user = User.query.filter_by(username=username).first()
        
        if not user or not check_password_hash(user.password_hash, password):
            flash('Invalid username or password. Please try again.', 'error')
            return redirect(url_for('login'))
            
        login_user(user, remember=remember)
        if user.role == 'admin' or user.role == 'hub_admin':
            return redirect(url_for('admin_dashboard'))
        elif user.role == 'driver':
            return redirect(url_for('driver_dashboard'))
            
    return render_template('login.html', no_layout=True)

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        phone = request.form.get('phone', '').strip()
        
        if not username or not phone:
            flash("Please enter both username and registered mobile phone number.", "error")
            return redirect(url_for('forgot_password'))
            
        user = User.query.filter_by(username=username).first()
        if not user:
            flash("Invalid username or phone number. Please try again.", "error")
            return redirect(url_for('forgot_password'))
            
        match = False
        if user.role == 'driver':
            driver = Driver.query.filter_by(user_id=user.id).first()
            if driver and driver.phone.strip() == phone:
                match = True
        elif user.role == 'hub_admin':
            hub_admin = HubAdmin.query.filter_by(user_id=user.id).first()
            if hub_admin and hub_admin.phone.strip() == phone:
                match = True
        elif user.role == 'admin':
            if phone == '9841111111':
                match = True
                
        if not match:
            flash("Invalid username or phone number. Please try again.", "error")
            return redirect(url_for('forgot_password'))
            
        session['reset_user_id'] = user.id
        session['reset_verified'] = True
        
        flash("Identity successfully verified! Please choose your new password.", "success")
        return redirect(url_for('reset_password'))
        
    return render_template('forgot_password.html', no_layout=True)

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if 'reset_user_id' not in session or not session.get('reset_verified'):
        flash("Unauthorized reset attempt. Please verify your credentials first.", "error")
        return redirect(url_for('forgot_password'))
        
    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if not password or not confirm_password:
            flash("All fields are required.", "error")
            return redirect(url_for('reset_password'))
            
        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return redirect(url_for('reset_password'))
            
        user = User.query.get(session['reset_user_id'])
        if user:
            user.password_hash = generate_password_hash(password)
            db.session.commit()
            
            session.pop('reset_user_id', None)
            session.pop('reset_verified', None)
            
            flash("Your password has been successfully reset! Please sign in with your new password.", "success")
            return redirect(url_for('login'))
        else:
            flash("User profile not found. Please try again.", "error")
            return redirect(url_for('forgot_password'))
            
    return render_template('reset_password.html', no_layout=True)

@app.route('/driver/register', methods=['GET', 'POST'])
def driver_register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        identifier = request.form.get('identifier', '').strip()
        username = request.form.get('username', '').strip()
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if not identifier or not username or not password or not confirm_password:
            flash("All fields are required.", "error")
            return redirect(url_for('driver_register'))
            
        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return redirect(url_for('driver_register'))
            
        # Find driver with matching phone or email
        driver = Driver.query.filter((Driver.phone == identifier) | (Driver.email == identifier)).first()
        if not driver:
            flash("The provided phone number or email is not registered in our system. Please contact the administrator.", "error")
            return redirect(url_for('driver_register'))
            
        if driver.user_id is not None:
            flash("This driver profile already has a registered account. Please sign in.", "error")
            return redirect(url_for('login'))
            
        # Check if username is taken
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash("Username is already taken. Please choose another.", "error")
            return redirect(url_for('driver_register'))
            
        # Create User
        user = User(
            username=username,
            password_hash=generate_password_hash(password),
            role='driver'
        )
        db.session.add(user)
        db.session.commit()
        
        # Link to Driver
        driver.user_id = user.id
        db.session.commit()
        
        flash("Registration successful! You can now sign in with your username.", "success")
        return redirect(url_for('login'))
        
    return render_template('driver_register.html', no_layout=True)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Successfully logged out.', 'success')
    return redirect(url_for('login'))

@app.route('/profile/settings', methods=['GET', 'POST'])
@login_required
def profile_settings():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if not username:
            flash("Username cannot be empty.", "error")
            return redirect(url_for('profile_settings'))
            
        existing_user = User.query.filter(User.username == username, User.id != current_user.id).first()
        if existing_user:
            flash("Username is already taken by another user.", "error")
            return redirect(url_for('profile_settings'))
            
        current_user.username = username
        
        if current_password or new_password or confirm_password:
            if not current_password or not new_password or not confirm_password:
                flash("To change your password, fill in all password fields.", "error")
                return redirect(url_for('profile_settings'))
                
            if not check_password_hash(current_user.password_hash, current_password):
                flash("Incorrect current password.", "error")
                return redirect(url_for('profile_settings'))
                
            if new_password != confirm_password:
                flash("New passwords do not match.", "error")
                return redirect(url_for('profile_settings'))
                
            current_user.password_hash = generate_password_hash(new_password)
            
        if current_user.role == 'driver' and current_user.driver_profile:
            driver = current_user.driver_profile
            driver_name = request.form.get('driver_name', '').strip()
            vehicle_number = request.form.get('vehicle_number', '').strip()
            driver_phone = request.form.get('driver_phone', '').strip()
            driver_email = request.form.get('driver_email', '').strip()
            
            if not driver_name or not vehicle_number or not driver_phone:
                flash("Courier Name, Vehicle Number, and Phone Number are required.", "error")
                return redirect(url_for('profile_settings'))
                
            if not validate_phone(driver_phone):
                flash("Invalid phone number format. Must be a 10-digit Nepali mobile number starting with 98, 97, or 96.", "error")
                return redirect(url_for('profile_settings'))
                
            dup_phone = Driver.query.filter(Driver.phone == driver_phone, Driver.id != driver.id).first()
            if dup_phone:
                flash("A driver with this phone number already exists.", "error")
                return redirect(url_for('profile_settings'))
                
            if driver_email:
                dup_email = Driver.query.filter(Driver.email == driver_email, Driver.id != driver.id).first()
                if dup_email:
                    flash("A driver with this email already exists.", "error")
                    return redirect(url_for('profile_settings'))
                    
            driver.name = driver_name
            driver.phone = driver_phone
            driver.email = driver_email if driver_email else None
            driver.vehicle_number = vehicle_number
            
        db.session.commit()
        flash("Profile settings saved successfully!", "success")
        
        if current_user.role == 'admin':
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('driver_dashboard'))
            
    return render_template('profile_settings.html')

# --- ADMIN ROUTES ---

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if current_user.role not in ['admin', 'hub_admin']:
        return redirect(url_for('index'))
        
    # Get hub name if hub admin
    hub_name = None
    if current_user.role == 'hub_admin':
        hub_admin_profile = HubAdmin.query.filter_by(user_id=current_user.id).first()
        if hub_admin_profile:
            hub_name = hub_admin_profile.hub.name
            
    # Calculate operational metrics
    if hub_name:
        parcels = Parcel.query.filter((Parcel.pickup_hub == hub_name) | (Parcel.delivery_hub == hub_name)).all()
    else:
        parcels = Parcel.query.all()
        
    drivers = Driver.query.all()
    
    total_revenue = sum(p.delivery_charge for p in parcels if p.status == 'Delivered' or p.payment_status == 'Paid')
    today_bookings = sum(1 for p in parcels if p.created_at.date() == datetime.utcnow().date())
    active_drivers = sum(1 for d in drivers if d.availability in ['Available', 'On Delivery', 'On Break'])
    failed_attempts = sum(p.delivery_attempts for p in parcels)
    cod_pending = sum(p.delivery_charge for p in parcels if p.payment_status == 'COD' and p.status != 'Delivered')
    
    # Calculate average delivery time
    delivered_parcels = [p for p in parcels if p.status == 'Delivered' and p.delivered_at]
    avg_time = 22.4 # default base fallback in mins
    if delivered_parcels:
        durations = []
        for p in delivered_parcels:
            diff = (p.delivered_at - p.created_at).total_seconds() / 60.0
            durations.append(diff)
        avg_time = sum(durations) / len(durations) if durations else 22.4
        
    stats = {
        'total_revenue': round(total_revenue),
        'today_bookings': today_bookings,
        'active_drivers': active_drivers,
        'failed_attempts': failed_attempts,
        'cod_pending': round(cod_pending),
        'avg_time': round(avg_time, 1)
    }
    
    # Fetch recent parcels and driver rankings
    if hub_name:
        recent_parcels = Parcel.query.filter((Parcel.pickup_hub == hub_name) | (Parcel.delivery_hub == hub_name)).order_by(Parcel.created_at.desc()).limit(8).all()
    else:
        recent_parcels = Parcel.query.order_by(Parcel.created_at.desc()).limit(8).all()
        
    driver_rankings = Driver.query.order_by(Driver.completed_deliveries.desc()).all()
    
    return render_template('admin_dashboard.html', active_page='dashboard', stats=stats, recent_parcels=recent_parcels, driver_rankings=driver_rankings, hub_name=hub_name)

@app.route('/admin/parcels')
@login_required
def manage_parcels():
    if current_user.role not in ['admin', 'hub_admin']:
        return redirect(url_for('index'))
        
    hub_name = None
    if current_user.role == 'hub_admin':
        hub_admin_profile = HubAdmin.query.filter_by(user_id=current_user.id).first()
        if hub_admin_profile:
            hub_name = hub_admin_profile.hub.name
            
    if hub_name:
        parcels = Parcel.query.filter((Parcel.pickup_hub == hub_name) | (Parcel.delivery_hub == hub_name)).order_by(Parcel.created_at.desc()).all()
    else:
        parcels = Parcel.query.order_by(Parcel.created_at.desc()).all()
        
    drivers = Driver.query.all()
    hubs = Hub.query.all()
    return render_template('parcels.html', active_page='parcels', parcels=parcels, drivers=drivers, hubs=hubs, hub_name=hub_name)

@app.route('/admin/parcel/<int:id>/details')
@login_required
def parcel_details(id):
    if current_user.role not in ['admin', 'hub_admin']:
        return redirect(url_for('index'))
        
    parcel = Parcel.query.get_or_404(id)
    
    # Hub Admin check: verify if the parcel belongs to their hub
    hub_name = None
    if current_user.role == 'hub_admin':
        hub_admin_profile = HubAdmin.query.filter_by(user_id=current_user.id).first()
        if hub_admin_profile:
            hub_name = hub_admin_profile.hub.name
            
    if hub_name and parcel.pickup_hub != hub_name and parcel.delivery_hub != hub_name:
        flash("Access Denied: This parcel does not belong to your hub.", "error")
        return redirect(url_for('manage_parcels'))
        
    drivers = Driver.query.all()
    hubs = Hub.query.all()
    
    return render_template('parcel_details.html', active_page='parcels', parcel=parcel, drivers=drivers, hubs=hubs, hub_name=hub_name)

@app.route('/admin/book-parcel', methods=['POST'])
@login_required
def book_parcel():
    if current_user.role not in ['admin', 'hub_admin']:
        return redirect(url_for('index'))
        
    sender_name = request.form.get('sender_name', '').strip()
    sender_phone = request.form.get('sender_phone', '').strip()
    receiver_name = request.form.get('receiver_name', '').strip()
    receiver_phone = request.form.get('receiver_phone', '').strip()
    pickup_address = request.form.get('pickup_address', '').strip()
    delivery_address = request.form.get('delivery_address', '').strip()

    
    try:
        pickup_latitude = float(request.form.get('pickup_latitude', 0.0))
        pickup_longitude = float(request.form.get('pickup_longitude', 0.0))
        delivery_latitude = float(request.form.get('delivery_latitude', 0.0))
        delivery_longitude = float(request.form.get('delivery_longitude', 0.0))
        
        weight = float(request.form.get('weight', 0.0))
        length = float(request.form.get('length', 0.0))
        width = float(request.form.get('width', 0.0))
        height = float(request.form.get('height', 0.0))
        delivery_charge = float(request.form.get('delivery_charge', 0.0))
    except ValueError:
        flash("Validation Error: Invalid numerical values provided.", "error")
        return redirect(url_for('manage_parcels'))
        
    parcel_type = request.form.get('parcel_type')
    payment_status = request.form.get('payment_status')
    
    # Required Backend Validations
    if not sender_name or not receiver_name or not pickup_address or not delivery_address:
        flash("Validation Error: Sender name, Receiver name, Pickup Address, and Delivery Address cannot be empty.", "error")
        return redirect(url_for('manage_parcels'))

        
    if not validate_phone(sender_phone) or not validate_phone(receiver_phone):
        flash("Validation Error: Invalid phone format. Must be a 10-digit Nepali number starting with 98, 97, or 96.", "error")
        return redirect(url_for('manage_parcels'))
        
    if weight <= 0 or length <= 0 or width <= 0 or height <= 0 or delivery_charge <= 0:
        flash("Validation Error: Weight, dimensions, and charges must be positive non-zero numbers.", "error")
        return redirect(url_for('manage_parcels'))
        
    if not validate_coords(pickup_latitude, pickup_longitude) or not validate_coords(delivery_latitude, delivery_longitude):
        flash("Validation Error: Coordinates must reside within Kathmandu Valley boundary box (Lat: 27.5-27.9, Lng: 85.1-85.5).", "error")
        return redirect(url_for('manage_parcels'))
        
    # Note: Hub nodes are dynamically resolved from coordinates for routing

    
    tags = request.form.getlist('special_tags')
    special_tags = ', '.join(tags) if tags else None
    
    # Generate unique Tracking ID
    while True:
        tracking_id = f"PF2026{random.randint(1000, 9999)}"
        existing = Parcel.query.filter_by(tracking_id=tracking_id).first()
        if not existing:
            break
            
    from algorithms import get_closest_hub
    pickup_hub_name = get_closest_hub(pickup_latitude, pickup_longitude)
    delivery_hub_name = get_closest_hub(delivery_latitude, delivery_longitude)
    
    if current_user.role == 'hub_admin':
        hub_admin_profile = HubAdmin.query.filter_by(user_id=current_user.id).first()
        if hub_admin_profile:
            pickup_hub_name = hub_admin_profile.hub.name
    
    parcel = Parcel(
        tracking_id=tracking_id,
        sender_name=sender_name,
        sender_phone=sender_phone,
        receiver_name=receiver_name,
        receiver_phone=receiver_phone,
        pickup_address=pickup_address,
        delivery_address=delivery_address,
        pickup_latitude=pickup_latitude,
        pickup_longitude=pickup_longitude,
        delivery_latitude=delivery_latitude,
        delivery_longitude=delivery_longitude,
        pickup_hub=pickup_hub_name,
        delivery_hub=delivery_hub_name,
        parcel_type=parcel_type,
        weight=weight,
        length=length,
        width=width,
        height=height,
        status='Pending',
        delivery_charge=delivery_charge,
        payment_status=payment_status,
        special_tags=special_tags,
        created_at=datetime.utcnow()
    )
    db.session.add(parcel)
    db.session.commit()
    
    # Write history and notifications
    hist = TrackingHistory(parcel_id=parcel.id, status='Pending', location=f"Home pickup: {pickup_address}")
    notif = NotificationLog(
        parcel_id=parcel.id,
        message=f"Order {tracking_id} booked for Home Delivery. Billing: Rs. {delivery_charge}.",
        type='Created'
    )
    db.session.add(hist)
    db.session.add(notif)
    db.session.commit()
    
    flash(f"Parcel order {tracking_id} successfully booked for Home Delivery!", "success")
    return redirect(url_for('manage_parcels'))

@app.route('/admin/edit-parcel/<int:id>', methods=['POST'])
@login_required
def edit_parcel(id):
    if current_user.role not in ['admin', 'hub_admin']:
        return redirect(url_for('index'))
        
    parcel = Parcel.query.get_or_404(id)
    old_status = parcel.status
    old_driver_id = parcel.assigned_driver_id
    
    sender_name = request.form.get('sender_name', '').strip()
    sender_phone = request.form.get('sender_phone', '').strip()
    receiver_name = request.form.get('receiver_name', '').strip()
    receiver_phone = request.form.get('receiver_phone', '').strip()
    pickup_address = request.form.get('pickup_address', '').strip()
    delivery_address = request.form.get('delivery_address', '').strip()

    
    try:
        pickup_latitude = float(request.form.get('pickup_latitude', 0.0))
        pickup_longitude = float(request.form.get('pickup_longitude', 0.0))
        delivery_latitude = float(request.form.get('delivery_latitude', 0.0))
        delivery_longitude = float(request.form.get('delivery_longitude', 0.0))
        
        weight = float(request.form.get('weight', 0.0))
        length = float(request.form.get('length', 0.0))
        width = float(request.form.get('width', 0.0))
        height = float(request.form.get('height', 0.0))
        delivery_charge = float(request.form.get('delivery_charge', 0.0))
    except ValueError:
        flash("Validation Error: Invalid numerical values provided.", "error")
        return redirect(url_for('manage_parcels'))
        
    parcel_type = request.form.get('parcel_type')
    payment_status = request.form.get('payment_status')
    
    # Backend Validations
    if not sender_name or not receiver_name or not pickup_address or not delivery_address:
        flash("Validation Error: Sender name, Receiver name, Pickup Address, and Delivery Address cannot be empty.", "error")
        return redirect(url_for('manage_parcels'))

        
    if not validate_phone(sender_phone) or not validate_phone(receiver_phone):
        flash("Validation Error: Invalid phone format. Must be a 10-digit Nepali number starting with 98, 97, or 96.", "error")
        return redirect(url_for('manage_parcels'))
        
    if weight <= 0 or length <= 0 or width <= 0 or height <= 0 or delivery_charge <= 0:
        flash("Validation Error: Weight, dimensions, and charges must be positive non-zero numbers.", "error")
        return redirect(url_for('manage_parcels'))
        
    if not validate_coords(pickup_latitude, pickup_longitude) or not validate_coords(delivery_latitude, delivery_longitude):
        flash("Validation Error: Coordinates must reside within Kathmandu Valley boundary box (Lat: 27.5-27.9, Lng: 85.1-85.5).", "error")
        return redirect(url_for('manage_parcels'))
        
    # Note: Closest hubs are resolved dynamically from coords in telemetry

    
    # Apply edits
    from algorithms import get_closest_hub
    parcel.sender_name = sender_name
    parcel.sender_phone = sender_phone
    parcel.receiver_name = receiver_name
    parcel.receiver_phone = receiver_phone
    parcel.pickup_address = pickup_address
    parcel.delivery_address = delivery_address
    parcel.pickup_latitude = pickup_latitude
    parcel.pickup_longitude = pickup_longitude
    parcel.delivery_latitude = delivery_latitude
    parcel.delivery_longitude = delivery_longitude
    pickup_hub_name = get_closest_hub(pickup_latitude, pickup_longitude)
    delivery_hub_name = get_closest_hub(delivery_latitude, delivery_longitude)
    
    if current_user.role == 'hub_admin':
        hub_admin_profile = HubAdmin.query.filter_by(user_id=current_user.id).first()
        if hub_admin_profile:
            pickup_hub_name = hub_admin_profile.hub.name
            
    parcel.pickup_hub = pickup_hub_name
    parcel.delivery_hub = delivery_hub_name
    parcel.parcel_type = parcel_type
    parcel.weight = weight
    parcel.length = length
    parcel.width = width
    parcel.height = height
    parcel.payment_status = payment_status
    parcel.delivery_charge = delivery_charge
    
    tags = request.form.getlist('special_tags')
    parcel.special_tags = ', '.join(tags) if tags else None
    
    new_status = request.form.get('status')
    new_driver_id = request.form.get('assigned_driver_id')
    
    # Update Status
    if new_status and new_status != old_status:
        parcel.status = new_status
        loc = f"Home Delivery: {delivery_address}" if new_status in ['Delivered', 'Out For Delivery', 'Failed Attempt'] else f"Home Pickup: {pickup_address}"
        hist = TrackingHistory(parcel_id=parcel.id, status=new_status, location=loc)
        notif = NotificationLog(parcel_id=parcel.id, message=f"Status updated to {new_status} by admin.", type='Created')
        db.session.add(hist)
        db.session.add(notif)
        
        if new_status in ['Delivered', 'Cancelled'] and parcel.assigned_driver:
            parcel.assigned_driver.availability = 'Available'
            if new_status == 'Delivered':
                parcel.assigned_driver.completed_deliveries += 1
                parcel.delivered_at = datetime.utcnow()
                
    # Update Driver
    if new_driver_id is not None and new_driver_id != '':
        new_driver_id = int(new_driver_id)
        if new_driver_id != old_driver_id:
            if parcel.assigned_driver:
                parcel.assigned_driver.availability = 'Available'
                
            driver = Driver.query.get(new_driver_id)
            if driver:
                parcel.assigned_driver_id = driver.id
                driver.availability = 'On Delivery'
                
                if parcel.status == 'Pending':
                    parcel.status = 'Assigned'
                    
                hist = TrackingHistory(parcel_id=parcel.id, status=parcel.status, location=pickup_address)
                notif = NotificationLog(parcel_id=parcel.id, message=f"Driver {driver.name} assigned by admin.", type='Assigned')
                db.session.add(hist)
                db.session.add(notif)
    elif new_driver_id == '':
        if parcel.assigned_driver:
            parcel.assigned_driver.availability = 'Available'
        parcel.assigned_driver_id = None
        if parcel.status == 'Assigned':
            parcel.status = 'Pending'
            
    db.session.commit()
    flash(f"Parcel {parcel.tracking_id} details updated successfully!", "success")
    return redirect(url_for('parcel_details', id=parcel.id))

@app.route('/admin/assign-driver-manual/<int:id>', methods=['POST'])
@login_required
def assign_driver_manual(id):
    if current_user.role not in ['admin', 'hub_admin']:
        return redirect(url_for('index'))
        
    parcel = Parcel.query.get_or_404(id)
    driver_id = request.form.get('driver_id')
    
    if driver_id:
        driver = Driver.query.get(int(driver_id))
        if driver:
            # Update parcel
            parcel.assigned_driver_id = driver.id
            parcel.status = 'Assigned'
            
            # Update driver state to On Delivery
            driver.availability = 'On Delivery'
            
            # Save logs
            hist = TrackingHistory(parcel_id=parcel.id, status='Assigned', location=parcel.pickup_address)
            notif = NotificationLog(
                parcel_id=parcel.id,
                message=f"Driver {driver.name} assigned to shipment.",
                type='Assigned'
            )
            db.session.add(hist)
            db.session.add(notif)
            db.session.commit()
            
            flash(f"Driver {driver.name} successfully assigned to order {parcel.tracking_id}!", "success")
            
    return redirect(url_for('parcel_details', id=parcel.id))

@app.route('/admin/run-fcfs-dispatch', methods=['POST'])
@login_required
def run_fcfs_dispatch():
    if current_user.role not in ['admin', 'hub_admin']:
        return redirect(url_for('index'))
        
    hub_name = None
    if current_user.role == 'hub_admin':
        hub_admin_profile = HubAdmin.query.filter_by(user_id=current_user.id).first()
        if hub_admin_profile:
            hub_name = hub_admin_profile.hub.name

    # Fetch Pending parcels, FCFS ordered by creation date ascending
    if hub_name:
        pending_parcels = Parcel.query.filter_by(status='Pending').filter((Parcel.pickup_hub == hub_name) | (Parcel.delivery_hub == hub_name)).order_by(Parcel.created_at.asc()).all()
    else:
        pending_parcels = Parcel.query.filter_by(status='Pending').order_by(Parcel.created_at.asc()).all()
        
    if not pending_parcels:
        flash("No pending parcel orders found in dispatch queue.", "info")
        return redirect(url_for('admin_dashboard'))
        
    dispatched_count = 0
    
    for parcel in pending_parcels:
        # Fetch available drivers
        available_drivers = Driver.query.filter_by(availability='Available').all()
        if not available_drivers:
            flash(f"Dispatch queue halted: No available fleet drivers. Dispatched {dispatched_count} orders.", "warning")
            return redirect(url_for('admin_dashboard'))
            
        # Greedy Match: Closest driver to parcel pickup address coordinates
        driver, distance = greedy_driver_assignment(parcel, available_drivers)
        
        if driver:
            parcel.assigned_driver_id = driver.id
            parcel.status = 'Assigned'
            driver.availability = 'On Delivery'
            
            # Save logs
            hist = TrackingHistory(parcel_id=parcel.id, status='Assigned', location=parcel.pickup_address)
            notif = NotificationLog(
                parcel_id=parcel.id,
                message=f"Auto-Dispatched FCFS: Courier {driver.name} matched (Distance: {distance:.2f} km).",
                type='Assigned'
            )
            db.session.add(hist)
            db.session.add(notif)
            db.session.commit()
            
            dispatched_count += 1
            flash(f"FCFS Dispatch: Match found! Order {parcel.tracking_id} assigned to {driver.name} (Nearest).", "success")
            
    if dispatched_count > 0:
        flash(f"FCFS processing complete. Successfully auto-assigned {dispatched_count} orders!", "success")
    else:
        flash("Dispatched queue processed. No available drivers matched.", "info")
        
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/drivers')
@login_required
def manage_drivers():
    if current_user.role != 'admin':
        return redirect(url_for('index'))
        
    drivers = Driver.query.all()
    return render_template('drivers.html', active_page='drivers', drivers=drivers)

@app.route('/admin/update-driver-state/<int:id>', methods=['POST'])
@login_required
def update_driver_state_admin(id):
    if current_user.role != 'admin':
        return redirect(url_for('index'))
        
    driver = Driver.query.get_or_404(id)
    state = request.form.get('state')
    
    if state:
        driver.availability = state
        db.session.commit()
        flash(f"Driver {driver.name} availability override saved: {state}", "success")
        
    return redirect(url_for('manage_drivers'))

@app.route('/admin/add-driver', methods=['POST'])
@login_required
def add_driver():
    if current_user.role != 'admin':
        return redirect(url_for('index'))
        
    name = request.form.get('name', '').strip()
    phone = request.form.get('phone', '').strip()
    email = request.form.get('email', '').strip()
    vehicle_number = request.form.get('vehicle_number', '').strip()
    availability = request.form.get('availability', 'Available')
    
    if not name or not phone or not vehicle_number:
        flash("Validation Error: Name, Phone, and Vehicle Number are required.", "error")
        return redirect(url_for('manage_drivers'))
        
    if not validate_phone(phone):
        flash("Validation Error: Invalid phone format. Must be a 10-digit Nepali mobile number starting with 98, 97, or 96.", "error")
        return redirect(url_for('manage_drivers'))
        
    dup_phone = Driver.query.filter_by(phone=phone).first()
    if dup_phone:
        flash("Validation Error: A driver with this phone number already exists.", "error")
        return redirect(url_for('manage_drivers'))
        
    if email:
        dup_email = Driver.query.filter_by(email=email).first()
        if dup_email:
            flash("Validation Error: A driver with this email already exists.", "error")
            return redirect(url_for('manage_drivers'))
            
    driver = Driver(
        user_id=None,  # No user account initially; created upon driver sign up
        name=name,
        phone=phone,
        email=email if email else None,
        vehicle_number=vehicle_number,
        availability=availability,
        latitude=27.7172,
        longitude=85.3240
    )
    db.session.add(driver)
    db.session.commit()
    
    flash(f"Driver profile for {name} successfully added! The driver can now register their user login using their phone number or email.", "success")
    return redirect(url_for('manage_drivers'))

@app.route('/admin/edit-driver/<int:id>', methods=['POST'])
@login_required
def edit_driver(id):
    if current_user.role != 'admin':
        return redirect(url_for('index'))
        
    driver = Driver.query.get_or_404(id)
    name = request.form.get('name', '').strip()
    phone = request.form.get('phone', '').strip()
    email = request.form.get('email', '').strip()
    vehicle_number = request.form.get('vehicle_number', '').strip()
    availability = request.form.get('availability')
    
    if not name or not phone or not vehicle_number:
        flash("Validation Error: Name, Phone, and Vehicle Number are required.", "error")
        return redirect(url_for('manage_drivers'))
        
    if not validate_phone(phone):
        flash("Validation Error: Invalid phone format. Must be a 10-digit Nepali mobile number starting with 98, 97, or 96.", "error")
        return redirect(url_for('manage_drivers'))
        
    dup_phone = Driver.query.filter(Driver.phone == phone, Driver.id != id).first()
    if dup_phone:
        flash("Validation Error: Another driver with this phone number already exists.", "error")
        return redirect(url_for('manage_drivers'))
        
    if email:
        dup_email = Driver.query.filter(Driver.email == email, Driver.id != id).first()
        if dup_email:
            flash("Validation Error: Another driver with this email already exists.", "error")
            return redirect(url_for('manage_drivers'))
            
    driver.name = name
    driver.phone = phone
    driver.email = email if email else None
    driver.vehicle_number = vehicle_number
    driver.availability = availability
    
    password = request.form.get('password')
    if password and driver.user:
        driver.user.password_hash = generate_password_hash(password)
        
    db.session.commit()
    flash(f"Driver {driver.name} details updated successfully!", "success")
    return redirect(url_for('manage_drivers'))

@app.route('/admin/delete-driver/<int:id>', methods=['POST'])
@login_required
def delete_driver(id):
    if current_user.role != 'admin':
        return redirect(url_for('index'))
        
    driver = Driver.query.get_or_404(id)
    name = driver.name
    
    user = User.query.get(driver.user_id)
    if user:
        db.session.delete(user)
        
    db.session.commit()
    flash(f"Driver {name} successfully deleted!", "success")
    return redirect(url_for('manage_drivers'))

# --- HUB & HUB ADMIN MANAGEMENT ROUTES ---

@app.route('/admin/hubs')
@login_required
def manage_hubs():
    if current_user.role != 'admin':
        return redirect(url_for('index'))
        
    hubs = Hub.query.all()
    hub_admins = HubAdmin.query.all()
    return render_template('hubs.html', active_page='hubs', hubs=hubs, hub_admins=hub_admins)

@app.route('/admin/create-hub', methods=['POST'])
@login_required
def create_hub():
    if current_user.role != 'admin':
        return redirect(url_for('index'))
        
    name = request.form.get('name', '').strip()
    try:
        latitude = float(request.form.get('latitude', 0.0))
        longitude = float(request.form.get('longitude', 0.0))
    except ValueError:
        flash("Validation Error: Invalid coordinates.", "error")
        return redirect(url_for('manage_hubs'))
        
    if not name:
        flash("Validation Error: Hub name cannot be empty.", "error")
        return redirect(url_for('manage_hubs'))
        
    if not validate_coords(latitude, longitude):
        flash("Validation Error: Coordinates must reside within Kathmandu Valley boundary box (Lat: 27.5-27.9, Lng: 85.1-85.5).", "error")
        return redirect(url_for('manage_hubs'))
        
    existing = Hub.query.filter_by(name=name).first()
    if existing:
        flash(f"Hub with name '{name}' already exists.", "error")
        return redirect(url_for('manage_hubs'))
        
    hub = Hub(name=name, latitude=latitude, longitude=longitude)
    db.session.add(hub)
    db.session.commit()
    
    flash(f"Hub '{name}' created successfully!", "success")
    return redirect(url_for('manage_hubs'))

@app.route('/admin/create-hub-admin', methods=['POST'])
@login_required
def create_hub_admin():
    if current_user.role != 'admin':
        return redirect(url_for('index'))
        
    name = request.form.get('name', '').strip()
    phone = request.form.get('phone', '').strip()
    email = request.form.get('email', '').strip()
    hub_id = request.form.get('hub_id')
    
    create_login = request.form.get('create_login') == 'yes'
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    
    if not name or not phone or not hub_id:
        flash("Validation Error: Name, phone, and hub assignment are required.", "error")
        return redirect(url_for('manage_hubs'))
        
    if not validate_phone(phone):
        flash("Validation Error: Phone format invalid. Must be 10-digit Nepali number starting with 98, 97, or 96.", "error")
        return redirect(url_for('manage_hubs'))
        
    existing_phone = HubAdmin.query.filter_by(phone=phone).first()
    if existing_phone:
        flash("Validation Error: A Hub Admin profile with this phone number already exists.", "error")
        return redirect(url_for('manage_hubs'))
        
    user = None
    if create_login:
        if not username or not password:
            flash("Validation Error: Username and password are required if creating a login account.", "error")
            return redirect(url_for('manage_hubs'))
            
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash(f"Validation Error: Username '{username}' is already taken.", "error")
            return redirect(url_for('manage_hubs'))
            
        user = User(
            username=username,
            password_hash=generate_password_hash(password),
            role='hub_admin'
        )
        db.session.add(user)
        db.session.commit()
        
    hub_admin = HubAdmin(
        user_id=user.id if user else None,
        name=name,
        phone=phone,
        email=email if email else None,
        hub_id=int(hub_id)
    )
    db.session.add(hub_admin)
    db.session.commit()
    
    if user:
        flash(f"Hub Admin profile and login account '{username}' created successfully!", "success")
    else:
        flash(f"Hub Admin profile for '{name}' created! They can now register their user login using their phone or email.", "success")
        
    return redirect(url_for('manage_hubs'))

@app.route('/admin/edit-hub/<int:id>', methods=['POST'])
@login_required
def edit_hub(id):
    if current_user.role != 'admin':
        return redirect(url_for('index'))
        
    hub = Hub.query.get_or_404(id)
    name = request.form.get('name', '').strip()
    try:
        latitude = float(request.form.get('latitude', 0.0))
        longitude = float(request.form.get('longitude', 0.0))
    except ValueError:
        flash("Validation Error: Invalid coordinates.", "error")
        return redirect(url_for('manage_hubs'))
        
    if not name:
        flash("Validation Error: Hub name cannot be empty.", "error")
        return redirect(url_for('manage_hubs'))
        
    if not validate_coords(latitude, longitude):
        flash("Validation Error: Coordinates must reside within Kathmandu Valley boundary box (Lat: 27.5-27.9, Lng: 85.1-85.5).", "error")
        return redirect(url_for('manage_hubs'))
        
    if name != hub.name:
        existing = Hub.query.filter_by(name=name).first()
        if existing:
            flash(f"Hub with name '{name}' already exists.", "error")
            return redirect(url_for('manage_hubs'))
            
    hub.name = name
    hub.latitude = latitude
    hub.longitude = longitude
    db.session.commit()
    
    flash(f"Hub '{name}' updated successfully!", "success")
    return redirect(url_for('manage_hubs'))

@app.route('/admin/edit-hub-admin/<int:id>', methods=['POST'])
@login_required
def edit_hub_admin(id):
    if current_user.role != 'admin':
        return redirect(url_for('index'))
        
    hub_admin = HubAdmin.query.get_or_404(id)
    name = request.form.get('name', '').strip()
    phone = request.form.get('phone', '').strip()
    email = request.form.get('email', '').strip()
    hub_id = request.form.get('hub_id')
    
    if not name or not phone or not hub_id:
        flash("Validation Error: Name, phone, and hub assignment are required.", "error")
        return redirect(url_for('manage_hubs'))
        
    if not validate_phone(phone):
        flash("Validation Error: Phone format invalid. Must be 10-digit Nepali number starting with 98, 97, or 96.", "error")
        return redirect(url_for('manage_hubs'))
        
    if phone != hub_admin.phone:
        existing = HubAdmin.query.filter_by(phone=phone).first()
        if existing:
            flash("Validation Error: A Hub Admin with this phone number already exists.", "error")
            return redirect(url_for('manage_hubs'))
            
    hub_admin.name = name
    hub_admin.phone = phone
    hub_admin.email = email if email else None
    hub_admin.hub_id = int(hub_id)
    db.session.commit()
    
    flash(f"Hub Admin profile for '{name}' updated successfully!", "success")
    return redirect(url_for('manage_hubs'))

@app.route('/admin/delete-hub/<int:id>')
@login_required
def delete_hub(id):
    if current_user.role != 'admin':
        return redirect(url_for('index'))
        
    hub = Hub.query.get_or_404(id)
    db.session.delete(hub)
    db.session.commit()
    flash("Hub successfully deleted.", "success")
    return redirect(url_for('manage_hubs'))

@app.route('/admin/delete-hub-admin/<int:id>')
@login_required
def delete_hub_admin(id):
    if current_user.role != 'admin':
        return redirect(url_for('index'))
        
    hub_admin = HubAdmin.query.get_or_404(id)
    user = hub_admin.user
    if user:
        db.session.delete(user)
    db.session.delete(hub_admin)
    db.session.commit()
    flash("Hub Admin profile successfully deleted.", "success")
    return redirect(url_for('manage_hubs'))

@app.route('/hub-admin/register', methods=['GET', 'POST'])
def hub_admin_register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        identifier = request.form.get('identifier', '').strip()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        
        if not identifier or not username or not password:
            flash("All fields are required.", "error")
            return redirect(url_for('hub_admin_register'))
            
        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return redirect(url_for('hub_admin_register'))
            
        # Search by phone or email
        profile = HubAdmin.query.filter((HubAdmin.phone == identifier) | (HubAdmin.email == identifier)).first()
        if not profile:
            flash("The provided phone number or email is not registered in our system. Please contact the administrator.", "error")
            return redirect(url_for('hub_admin_register'))
            
        if profile.user_id is not None:
            flash("This hub admin profile already has a registered account. Please sign in.", "error")
            return redirect(url_for('hub_admin_register'))
            
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash(f"Username '{username}' is already taken.", "error")
            return redirect(url_for('hub_admin_register'))
            
        user = User(
            username=username,
            password_hash=generate_password_hash(password),
            role='hub_admin'
        )
        db.session.add(user)
        db.session.commit()
        
        profile.user_id = user.id
        db.session.commit()
        
        flash("Your Hub Admin account has been registered successfully! Please sign in.", "success")
        return redirect(url_for('login'))
        
    return render_template('hub_admin_register.html', no_layout=True)

@app.route('/admin/cancel-parcel/<int:id>')
@login_required
def cancel_parcel(id):
    if current_user.role != 'admin':
        return redirect(url_for('index'))
        
    parcel = Parcel.query.get_or_404(id)
    if parcel.status == 'Pending':
        parcel.status = 'Cancelled'
        
        hist = TrackingHistory(parcel_id=parcel.id, status='Cancelled', location=parcel.pickup_address)
        notif = NotificationLog(parcel_id=parcel.id, message="Order cancelled by administrative control.", type='Failed')
        
        db.session.add(hist)
        db.session.add(notif)
        db.session.commit()
        flash(f"Parcel order {parcel.tracking_id} successfully cancelled.", "success")
    else:
        flash("Only pending orders can be cancelled.", "error")
        
    return redirect(url_for('manage_parcels'))

@app.route('/admin/track/<string:tracking_id>')
@login_required
def live_tracking_view(tracking_id):
    if current_user.role != 'admin' and current_user.role != 'driver':
        return redirect(url_for('index'))
        
    parcel = Parcel.query.filter_by(tracking_id=tracking_id).first_or_404()
    return render_template('live_tracking.html', active_page='parcels', parcel=parcel)

# --- DRIVER ROUTES ---

@app.route('/driver/dashboard')
@login_required
def driver_dashboard():
    if current_user.role != 'driver':
        return redirect(url_for('index'))
        
    driver = Driver.query.filter_by(user_id=current_user.id).first_or_404()
    
    # Active deliveries: status is not Delivered and not Cancelled
    active_deliveries = Parcel.query.filter_by(assigned_driver_id=driver.id).filter(Parcel.status.notin_(['Delivered', 'Cancelled'])).order_by(Parcel.created_at.desc()).all()
    
    # Completed/History deliveries: status is Delivered or Cancelled
    history_deliveries = Parcel.query.filter_by(assigned_driver_id=driver.id).filter(Parcel.status.in_(['Delivered', 'Cancelled'])).order_by(Parcel.created_at.desc()).all()
    
    drivers = Driver.query.all() # needed for base select
    
    return render_template(
        'driver_dashboard.html', 
        active_page='driver_dashboard', 
        driver=driver, 
        active_deliveries=active_deliveries, 
        history_deliveries=history_deliveries, 
        drivers=drivers
    )

@app.route('/driver/update-status/<int:id>', methods=['POST'])
@login_required
def update_parcel_status_driver(id):
    if current_user.role != 'driver':
        return redirect(url_for('index'))
        
    parcel = Parcel.query.get_or_404(id)
    driver = Driver.query.filter_by(user_id=current_user.id).first_or_404()
    
    status = request.form.get('status')
    
    if status == 'Picked Up':
        # Upload condition image
        file = request.files.get('pickup_image')
        if file:
            filename = secure_filename(f"pickup_{parcel.tracking_id}_{file.filename}")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            parcel.pickup_image = filename
            
        parcel.status = 'Picked Up'
        hist = TrackingHistory(parcel_id=parcel.id, status='Picked Up', location=parcel.pickup_address)
        notif = NotificationLog(parcel_id=parcel.id, message="Package checked and picked up by driver.", type='Picked Up')
        db.session.add(hist)
        db.session.add(notif)
        
    elif status == 'In Transit':
        parcel.status = 'In Transit'
        hist = TrackingHistory(parcel_id=parcel.id, status='In Transit', location=parcel.pickup_address)
        notif = NotificationLog(parcel_id=parcel.id, message="Shipment in transit on highway routes.", type='In Transit')
        db.session.add(hist)
        db.session.add(notif)
        
    elif status == 'Out For Delivery':
        parcel.status = 'Out For Delivery'
        hist = TrackingHistory(parcel_id=parcel.id, status='Out For Delivery', location=parcel.delivery_address)
        notif = NotificationLog(parcel_id=parcel.id, message="Shipment arrived at destination hub, out for delivery.", type='Out For Delivery')
        db.session.add(hist)
        db.session.add(notif)
        
    elif status == 'Delivered':
        # Upload handoff photo, save notes, save signature canvas
        file = request.files.get('delivery_image')
        if file:
            filename = secure_filename(f"delivery_{parcel.tracking_id}_{file.filename}")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            parcel.delivery_image = filename
            
        delivery_notes = request.form.get('delivery_notes')
        customer_signature = request.form.get('customer_signature')
        
        parcel.delivery_notes = delivery_notes
        parcel.customer_signature = customer_signature
        parcel.delivered_at = datetime.utcnow()
        parcel.status = 'Delivered'
        parcel.payment_status = 'Paid' # Mark as paid since delivered
        
        # Increase driver completed count and return state to Available
        driver.completed_deliveries += 1
        driver.availability = 'Available'
        
        hist = TrackingHistory(parcel_id=parcel.id, status='Delivered', location=parcel.delivery_address)
        notif = NotificationLog(parcel_id=parcel.id, message="Shipment delivered successfully. Signature pad secured.", type='Delivered')
        db.session.add(hist)
        db.session.add(notif)
        
    elif status == 'Failed Attempt':
        failed_reason = request.form.get('failed_reason')
        parcel.delivery_attempts += 1
        parcel.failed_reason = failed_reason
        
        # Return status to Assigned so it can be attempted again or returned
        parcel.status = 'Assigned'
        
        hist = TrackingHistory(parcel_id=parcel.id, status='Failed Attempt', location=parcel.delivery_address)
        notif = NotificationLog(
            parcel_id=parcel.id, 
            message=f"Delivery attempt failed. Reason: {failed_reason} (Attempt: {parcel.delivery_attempts}).", 
            type='Failed'
        )
        db.session.add(hist)
        db.session.add(notif)
        
    db.session.commit()
    flash(f"Shipment {parcel.tracking_id} successfully updated to {status}!", "success")
    return redirect(url_for('driver_dashboard'))

# --- CUSTOMER PUBLIC TRACKING ROUTE ---

@app.route('/track')
def customer_tracking_view():
    tracking_id = request.args.get('tracking_id')
    parcel = None
    error = False
    
    if tracking_id:
        parcel = Parcel.query.filter_by(tracking_id=tracking_id.strip()).first()
        if not parcel:
            error = True
            
    return render_template('customer_tracking.html', tracking_id=tracking_id, parcel=parcel, error=error, no_layout=True)

# --- HELPER SHIPPING LABEL & POD PRINT ROUTING ---

@app.route('/parcel/<int:id>/label')
@login_required
def print_shipping_label(id):
    parcel = Parcel.query.get_or_404(id)
    return render_template('shipping_label.html', parcel=parcel, no_layout=True)

@app.route('/parcel/<int:id>/proof')
def view_proof_of_delivery(id):
    parcel = Parcel.query.get_or_404(id)
    return render_template('proof_of_delivery.html', parcel=parcel, no_layout=True)

@app.route('/static/uploads/<filename>')
def uploaded_file(filename):
    return send_file(os.path.join(app.config['UPLOAD_FOLDER'], filename))

# --- API REAL-TIME TELEMETRY ENDPOINTS ---

@app.route('/api/admin/analytics')
@login_required
def api_admin_analytics():
    parcels = Parcel.query.all()
    drivers = Driver.query.all()
    
    # 1. Status counts mapping
    status_counts = {
        'Pending': 0, 'Assigned': 0, 'Picked Up': 0, 'In Transit': 0,
        'Out For Delivery': 0, 'Delivered': 0, 'Cancelled': 0
    }
    for p in parcels:
        if p.status in status_counts:
            status_counts[p.status] += 1
            
    # 2. Monthly Trend logic (past 5 months)
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]
    counts = [12, 18, 25, 34, 42, 54] # Seed trends
    counts[-1] = status_counts['Delivered'] + status_counts['In Transit'] # match current month
    
    monthly_trends = {
        'labels': months,
        'counts': counts
    }
    
    return jsonify({
        'status_counts': status_counts,
        'monthly_trends': monthly_trends
    })

@app.route('/api/admin/drivers-location')
@login_required
def api_drivers_location():
    drivers = Driver.query.all()
    data = []
    for d in drivers:
        data.append({
            'id': d.id,
            'name': d.name,
            'vehicle': d.vehicle_number,
            'availability': d.availability,
            'latitude': d.latitude,
            'longitude': d.longitude,
            'phone': d.phone
        })
    return jsonify(data)


        
@app.route('/api/parcel/<tracking_id>/route')
def api_parcel_route(tracking_id):
    parcel = Parcel.query.filter_by(tracking_id=tracking_id).first_or_404()
    
    # Check if driver is assigned and has active location coordinates
    driver_coords = None
    if parcel.assigned_driver and parcel.assigned_driver.latitude and parcel.assigned_driver.longitude:
        driver_coords = {'lat': parcel.assigned_driver.latitude, 'lng': parcel.assigned_driver.longitude}
        
    hubs_dict = get_all_hubs_dict()
    pickup_hub = hubs_dict.get(parcel.pickup_hub)
    delivery_hub = hubs_dict.get(parcel.delivery_hub)
    
    if not pickup_hub or not delivery_hub:
        return jsonify({'error': 'Invalid hubs'}), 400

    # Determine start and end coordinates based on live status
    routing_from_driver = False
    if driver_coords and parcel.status in ['Assigned', 'Picked Up', 'In Transit', 'Out For Delivery']:
        routing_from_driver = True
        start_lat = driver_coords['lat']
        start_lng = driver_coords['lng']
        start_name = 'Driver Location'
        
        if parcel.status == 'Assigned':
            end_lat = pickup_hub['lat']
            end_lng = pickup_hub['lng']
            end_name = f"{parcel.pickup_hub} Hub"
        elif parcel.status in ['Picked Up', 'In Transit']:
            end_lat = delivery_hub['lat']
            end_lng = delivery_hub['lng']
            end_name = f"{parcel.delivery_hub} Hub"
        else: # Out For Delivery
            end_lat = parcel.delivery_latitude
            end_lng = parcel.delivery_longitude
            end_name = 'Home Delivery'
    else:
        start_lat = pickup_hub['lat']
        start_lng = pickup_hub['lng']
        start_name = f"{parcel.pickup_hub} Hub"
        end_lat = parcel.delivery_latitude
        end_lng = parcel.delivery_longitude
        end_name = 'Home Delivery'
        
    driver_data = None
    if parcel.assigned_driver:
        driver_data = {
            'name': parcel.assigned_driver.name,
            'vehicle': parcel.assigned_driver.vehicle_number,
            'lat': parcel.assigned_driver.latitude,
            'lng': parcel.assigned_driver.longitude
        }

    # Fetch all possible routes (with duration, distance, coordinates)
    routes = fetch_osrm_routes_with_alternatives(start_lat, start_lng, end_lat, end_lng)
    recommended_route_pts = routes[0]['coordinates'] if routes else []

    # If routing directly from active driver to destination
    if routing_from_driver:
        segments = [{
            'from': start_name,
            'to': end_name,
            'coordinates': recommended_route_pts,
            'traffic': 'Moderate',
            'condition': 'Active courier delivery routing',
            'color': '#2563EB',  # Google Maps Blue color
            'speed_limit': 45
        }]
        
        return jsonify({
            'pickup': {'name': f"{parcel.pickup_hub} Hub", 'lat': pickup_hub['lat'], 'lng': pickup_hub['lng']},
            'delivery': {'name': 'Home Delivery', 'lat': parcel.delivery_latitude, 'lng': parcel.delivery_longitude},
            'path': recommended_route_pts,
            'segments': segments,
            'routes': routes,
            'driver': driver_data
        })
        
    # Fallback to standard hub-to-home Dijkstra route when driver is offline or parcel is pending
    path, distance = dijkstra(parcel.pickup_hub, parcel.delivery_hub)
    hub_coords = get_route_coordinates(path)
    
    path_coords = []
    path_coords.extend(hub_coords)
    path_coords.append({'name': 'Home Delivery', 'lat': parcel.delivery_latitude, 'lng': parcel.delivery_longitude})
    
    to_coords = {'lat': parcel.delivery_latitude, 'lng': parcel.delivery_longitude}
    segments = get_route_segments(path, pickup_coords=None, delivery_coords=to_coords)
    
    return jsonify({
        'pickup': {'name': f"{parcel.pickup_hub} Hub", 'lat': pickup_hub['lat'], 'lng': pickup_hub['lng']},
        'delivery': {'name': 'Home Delivery', 'lat': parcel.delivery_latitude, 'lng': parcel.delivery_longitude},
        'path': path_coords,
        'segments': segments,
        'routes': routes,
        'driver': driver_data
    })

@app.route('/api/parcel/<tracking_id>/telemetry')
def api_parcel_telemetry(tracking_id):
    parcel = Parcel.query.filter_by(tracking_id=tracking_id).first_or_404()
    
    # Destination is the home delivery coordinate rather than delivery hub
    dest_lat = parcel.delivery_latitude
    dest_lng = parcel.delivery_longitude
    
    distance_remaining_km = 0.0
    eta_minutes = 0
    speed_kmh = 0.0
    progress_percent = 0.0
    
    # Resolve closest hubs dynamically
    pickup_hub_name = get_closest_hub(parcel.pickup_latitude, parcel.pickup_longitude)
    delivery_hub_name = get_closest_hub(parcel.delivery_latitude, parcel.delivery_longitude)
    
    # Haversine metrics based on status
    if parcel.status == 'Delivered':
        progress_percent = 100.0
    elif parcel.status == 'Cancelled':
        progress_percent = 0.0
    elif parcel.assigned_driver:
        driver = parcel.assigned_driver
        distance_remaining_km = haversine_distance(driver.latitude, driver.longitude, dest_lat, dest_lng)
        
        # Total route distance for progress percentage (Home-to-Home)
        path, total_dist = dijkstra(pickup_hub_name, delivery_hub_name)
        hubs_dict = get_all_hubs_dict()
        pickup_hub_coords = hubs_dict.get(pickup_hub_name)
        delivery_hub_coords = hubs_dict.get(delivery_hub_name)
        
        dist_pickup_to_hub = haversine_distance(parcel.pickup_latitude, parcel.pickup_longitude, pickup_hub_coords['lat'], pickup_hub_coords['lng'])
        dist_hub_to_delivery = haversine_distance(delivery_hub_coords['lat'], delivery_hub_coords['lng'], parcel.delivery_latitude, parcel.delivery_longitude)
        
        total_dist_home_to_home = dist_pickup_to_hub + total_dist + dist_hub_to_delivery
        
        if parcel.status == 'Assigned':
            progress_percent = 10.0
            speed_kmh = 0.0
            eta_minutes = int((total_dist_home_to_home / 25.0) * 60) + 10 # add buffer
        elif parcel.status == 'Picked Up':
            progress_percent = 20.0
            speed_kmh = 0.0
            eta_minutes = int((total_dist_home_to_home / 25.0) * 60)
        elif parcel.status == 'In Transit':
            progress_percent = 45.0
            speed_kmh = 32.0 # simulated active motorcycle traversal
            eta_minutes = int((distance_remaining_km / 25.0) * 60)
        elif parcel.status == 'Out For Delivery':
            progress_percent = 85.0
            speed_kmh = 18.0
            eta_minutes = int((distance_remaining_km / 15.0) * 60)
            
        if eta_minutes < 1 and parcel.status != 'Delivered':
            eta_minutes = 3 # fallback ETA
    else:
        # Unassigned / Pending
        path, total_dist = dijkstra(pickup_hub_name, delivery_hub_name)
        hubs_dict = get_all_hubs_dict()
        pickup_hub_coords = hubs_dict.get(pickup_hub_name)
        delivery_hub_coords = hubs_dict.get(delivery_hub_name)
        
        dist_pickup_to_hub = haversine_distance(parcel.pickup_latitude, parcel.pickup_longitude, pickup_hub_coords['lat'], pickup_hub_coords['lng'])
        dist_hub_to_delivery = haversine_distance(delivery_hub_coords['lat'], delivery_hub_coords['lng'], parcel.delivery_latitude, parcel.delivery_longitude)
        
        total_dist_home_to_home = dist_pickup_to_hub + total_dist + dist_hub_to_delivery
        
        distance_remaining_km = total_dist_home_to_home
        eta_minutes = int((total_dist_home_to_home / 25.0) * 60) + 15
        progress_percent = 0.0
        
    # Fetch Notification history
    notifications = []
    for log in parcel.notifications:
        notifications.append({
            'message': log.message,
            'type': log.type,
            'timestamp': log.timestamp.isoformat()
        })
        
    return jsonify({
        'tracking_id': parcel.tracking_id,
        'status': parcel.status,
        'progress_percent': progress_percent,
        'distance_remaining_km': distance_remaining_km,
        'eta_minutes': eta_minutes,
        'speed_kmh': speed_kmh,
        'driver_latitude': parcel.assigned_driver.latitude if parcel.assigned_driver else None,
        'driver_longitude': parcel.assigned_driver.longitude if parcel.assigned_driver else None,
        'notifications': notifications
    })

@app.route('/api/driver/active-route')
@login_required
def api_driver_active_route():
    if current_user.role != 'driver':
        return jsonify({'error': 'Unauthorized'}), 401
        
    driver = Driver.query.filter_by(user_id=current_user.id).first_or_404()
    
    # Active transit parcel
    parcel = Parcel.query.filter_by(assigned_driver_id=driver.id).filter(Parcel.status.in_(['In Transit', 'Out For Delivery'])).first()
    
    if not parcel:
        return jsonify({'coordinates': []})
        
    # Calculate path resolving hubs dynamically
    pickup_hub_name = get_closest_hub(parcel.pickup_latitude, parcel.pickup_longitude)
    delivery_hub_name = get_closest_hub(parcel.delivery_latitude, parcel.delivery_longitude)
    path, cost = dijkstra(pickup_hub_name, delivery_hub_name)
    
    pickup_coords = {'lat': parcel.pickup_latitude, 'lng': parcel.pickup_longitude}
    delivery_coords = {'lat': parcel.delivery_latitude, 'lng': parcel.delivery_longitude}
    segments = get_route_segments(path, pickup_coords, delivery_coords)
    
    # Compile all coordinates along the real OSRM road paths
    smooth_coords = []
    for seg in segments:
        for pt in seg['coordinates']:
            smooth_coords.append({'lat': pt['lat'], 'lng': pt['lng']})
            
    return jsonify({'coordinates': smooth_coords})

@app.route('/api/driver/location', methods=['POST'])
@login_required
def api_driver_location_update():
    if current_user.role != 'driver':
        return jsonify({'error': 'Unauthorized'}), 401
        
    driver = Driver.query.filter_by(user_id=current_user.id).first_or_404()
    data = request.get_json()
    
    if data:
        lat = data.get('latitude')
        lng = data.get('longitude')
        availability = data.get('availability')
        
        if lat and lng:
            # Enforce validation: coordinates must reside within Kathmandu Valley bounds
            if validate_coords(lat, lng):
                driver.latitude = lat
                driver.longitude = lng
            else:
                # Log warning in telemetry response but preserve database integrity
                pass
            
        if availability:
            driver.availability = availability
            
        db.session.commit()
        return jsonify({'status': 'Location telemetry synchronized', 'lat': driver.latitude, 'lng': driver.longitude, 'state': driver.availability})
        
    return jsonify({'error': 'Invalid payload'}), 400


# --- DYNAMIC BARCODE & QR GENERATORS ---

@app.route('/api/qrcode/<tracking_id>')
def generate_qrcode_api(tracking_id):
    qr = qrcode.QRCode(version=1, box_size=8, border=1)
    tracking_url = f"{request.url_root}track?tracking_id={tracking_id}"
    qr.add_data(tracking_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")

@app.route('/api/barcode/<tracking_id>')
def generate_barcode_api(tracking_id):
    Code128 = barcode.get_barcode_class('code128')
    rv = BytesIO()
    barcode_obj = Code128(tracking_id, writer=ImageWriter())
    # Module height and width configured for compact thermal printing fit
    barcode_obj.write(rv, options={"module_width": 0.22, "module_height": 6.8, "font_size": 1, "text_distance": 1, "quiet_zone": 1})
    rv.seek(0)
    return send_file(rv, mimetype="image/png")

if __name__ == '__main__':
    app.run(debug=True)
