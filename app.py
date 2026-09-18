import os
import random
import re
import csv
from datetime import datetime, timedelta
from io import BytesIO, StringIO

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, session, Response
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# Barcode & QR Code generators
import qrcode
import barcode
from barcode.writer import ImageWriter

# Models and Database
from models import (
    db, User, Driver, Parcel, TrackingHistory, NotificationLog, Hub, HubAdmin,
    Vehicle, VehicleMaintenance, Assignment, Manifest, ManifestItem, Merchandise,
    CustomerProfile, CustomerAddress, PricingRule, DeliverySheet, DeliverySheetItem,
    SupportTicket, TicketReply, CompanySetting
)

# Algorithms
from algorithms import (
    HUBS, GRAPH, dijkstra, greedy_driver_assignment, get_route_coordinates,
    haversine_distance, get_closest_hub, get_route_segments, fetch_osrm_route,
    fetch_osrm_routes_with_alternatives, get_all_hubs_dict,
    multi_courier_optimization, solve_tsp, calculate_location_distance, COURIER_PALETTE
)

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

# --- HELPER FUNCTIONS FOR MULTI-HUB & PERMISSIONS ---

def get_current_hub_name():
    if not current_user.is_authenticated:
        return None
    if current_user.role in ['hub_admin', 'branch_manager', 'booking_staff', 'warehouse_staff', 'dispatcher', 'branch_staff']:
        profile = HubAdmin.query.filter_by(user_id=current_user.id).first()
        if profile and profile.hub:
            return profile.hub.name
    return None

def get_current_hub_id():
    if not current_user.is_authenticated:
        return None
    if current_user.role in ['hub_admin', 'branch_manager', 'booking_staff', 'warehouse_staff', 'dispatcher', 'delivery_staff', 'branch_staff']:
        profile = HubAdmin.query.filter_by(user_id=current_user.id).first()
        if profile:
            return profile.hub_id
    return None

# --- AUTHENTICATION & PORTAL LANDING ROUTES ---

@app.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect(url_for('admin_dashboard'))
        elif current_user.role in ['hub_admin', 'branch_manager', 'booking_staff', 'warehouse_staff', 'dispatcher', 'branch_staff']:
            return redirect(url_for('branch_dashboard'))
        elif current_user.role == 'customer':
            return redirect(url_for('customer_dashboard'))
        elif current_user.role == 'driver':
            return redirect(url_for('driver_dashboard'))
    
    # Public portal home
    hubs = Hub.query.all()
    company = CompanySetting.query.first()
    return render_template('public_home.html', hubs=hubs, company=company, no_layout=True)

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
        if user.role == 'admin':
            return redirect(url_for('admin_dashboard'))
        elif user.role in ['hub_admin', 'branch_manager', 'booking_staff', 'warehouse_staff', 'dispatcher', 'branch_staff']:
            return redirect(url_for('branch_dashboard'))
        elif user.role == 'customer':
            return redirect(url_for('customer_dashboard'))
        elif user.role == 'driver':
            return redirect(url_for('driver_dashboard'))
            
    return render_template('login.html', no_layout=True)

@app.route('/customer/register', methods=['GET', 'POST'])
def customer_register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        contact_person = request.form.get('contact_person', '').strip()
        company_name = request.form.get('company_name', '').strip()
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip()
        address = request.form.get('address', '').strip()
        city = request.form.get('city', 'Kathmandu').strip()
        account_type = request.form.get('account_type', 'individual')
        
        if not username or not password or not contact_person or not phone:
            flash("Username, password, contact name, and phone are required.", "error")
            return redirect(url_for('customer_register'))
            
        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return redirect(url_for('customer_register'))
            
        if not validate_phone(phone):
            flash("Invalid phone number format.", "error")
            return redirect(url_for('customer_register'))
            
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash(f"Username '{username}' is already taken.", "error")
            return redirect(url_for('customer_register'))
            
        user = User(
            username=username,
            password_hash=generate_password_hash(password),
            role='customer',
            permissions='view,create,reports'
        )
        db.session.add(user)
        db.session.commit()
        
        profile = CustomerProfile(
            user_id=user.id,
            company_name=company_name or None,
            contact_person=contact_person,
            phone=phone,
            email=email or None,
            address=address or None,
            city=city,
            account_type=account_type,
            credit_limit=10000.0 if account_type == 'business' else 0.0,
            balance=0.0
        )
        db.session.add(profile)
        db.session.flush()
        
        if address:
            cust_addr = CustomerAddress(
                customer_id=profile.id,
                label='Default Pickup',
                recipient_name=contact_person,
                phone=phone,
                address=address,
                city=city,
                is_default=True
            )
            db.session.add(cust_addr)
            
        db.session.commit()
        login_user(user)
        flash("Welcome to ParcelFleet! Your customer portal account is ready.", "success")
        return redirect(url_for('customer_dashboard'))
        
    return render_template('customer_register.html', no_layout=True)

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
        elif user.role in ['hub_admin', 'booking_staff', 'warehouse_staff', 'dispatcher', 'delivery_staff', 'branch_staff']:
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
            
        driver = Driver.query.filter((Driver.phone == identifier) | (Driver.email == identifier)).first()
        if not driver:
            flash("The provided phone number or email is not registered in our system. Please contact administrator.", "error")
            return redirect(url_for('driver_register'))
            
        if driver.user_id is not None:
            flash("This driver profile already has a registered account. Please sign in.", "error")
            return redirect(url_for('login'))
            
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash("Username is already taken. Please choose another.", "error")
            return redirect(url_for('driver_register'))
            
        user = User(
            username=username,
            password_hash=generate_password_hash(password),
            role='driver',
            permissions='view,edit'
        )
        db.session.add(user)
        db.session.commit()
        
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
                flash("Invalid phone number format.", "error")
                return redirect(url_for('profile_settings'))
                
            driver.name = driver_name
            driver.phone = driver_phone
            driver.email = driver_email if driver_email else None
            driver.vehicle_number = vehicle_number
            
        db.session.commit()
        flash("Profile settings saved successfully!", "success")
        
        if current_user.role == 'driver':
            return redirect(url_for('driver_dashboard'))
        else:
            return redirect(url_for('admin_dashboard'))
            
    return render_template('profile_settings.html')

# --- MAIN DASHBOARD & HUB SCOPING ---

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if current_user.role not in ['admin', 'hub_admin', 'booking_staff', 'warehouse_staff', 'dispatcher', 'delivery_staff', 'branch_staff']:
        return redirect(url_for('index'))
        
    hub_name = get_current_hub_name()
    hub_filter_query = request.args.get('hub_filter')
    if current_user.role == 'admin' and hub_filter_query:
        hub_name = hub_filter_query

    all_hubs = Hub.query.all()

    # Calculate operational metrics
    if hub_name:
        parcels = Parcel.query.filter((Parcel.pickup_hub == hub_name) | (Parcel.delivery_hub == hub_name)).all()
        drivers = Driver.query.join(Hub, Driver.hub_id == Hub.id, isouter=True).filter((Hub.name == hub_name) | (Driver.hub_id == None)).all()
        vehicles = Vehicle.query.join(Hub, Vehicle.hub_id == Hub.id, isouter=True).filter((Hub.name == hub_name) | (Vehicle.hub_id == None)).all()
    else:
        parcels = Parcel.query.all()
        drivers = Driver.query.all()
        vehicles = Vehicle.query.all()
        
    total_revenue = sum(p.delivery_charge for p in parcels if p.status == 'Delivered' or p.payment_status == 'Paid')
    today_bookings = sum(1 for p in parcels if p.created_at.date() == datetime.utcnow().date())
    active_drivers = sum(1 for d in drivers if d.availability in ['Available', 'On Delivery', 'On Break'])
    total_vehicles = len(vehicles)
    failed_attempts = sum(p.delivery_attempts for p in parcels)
    cod_pending = sum(p.delivery_charge for p in parcels if p.payment_status == 'COD' and p.status != 'Delivered')
    
    delivered_parcels = [p for p in parcels if p.status == 'Delivered' and p.delivered_at]
    avg_time = 22.4
    if delivered_parcels:
        durations = [(p.delivered_at - p.created_at).total_seconds() / 60.0 for p in delivered_parcels]
        avg_time = sum(durations) / len(durations) if durations else 22.4
        
    stats = {
        'total_revenue': round(total_revenue),
        'today_bookings': today_bookings,
        'active_drivers': active_drivers,
        'total_vehicles': total_vehicles,
        'failed_attempts': failed_attempts,
        'cod_pending': round(cod_pending),
        'avg_time': round(avg_time, 1)
    }
    
    if hub_name:
        recent_parcels = Parcel.query.filter((Parcel.pickup_hub == hub_name) | (Parcel.delivery_hub == hub_name)).order_by(Parcel.created_at.desc()).limit(8).all()
    else:
        recent_parcels = Parcel.query.order_by(Parcel.created_at.desc()).limit(8).all()
        
    driver_rankings = Driver.query.order_by(Driver.completed_deliveries.desc()).all()
    
    return render_template(
        'admin_dashboard.html',
        active_page='dashboard',
        stats=stats,
        recent_parcels=recent_parcels,
        driver_rankings=driver_rankings,
        hub_name=hub_name,
        all_hubs=all_hubs
    )

# --- VEHICLE MANAGEMENT MODULE ---

@app.route('/admin/vehicles')
@login_required
def manage_vehicles():
    if current_user.role not in ['admin', 'hub_admin', 'dispatcher', 'warehouse_staff']:
        return redirect(url_for('index'))
        
    hub_id = get_current_hub_id()
    if hub_id:
        vehicles = Vehicle.query.filter((Vehicle.hub_id == hub_id) | (Vehicle.hub_id == None)).all()
    else:
        vehicles = Vehicle.query.all()
        
    hubs = Hub.query.all()
    return render_template('vehicles.html', active_page='vehicles', vehicles=vehicles, hubs=hubs, now=datetime.utcnow())

@app.route('/admin/add-vehicle', methods=['POST'])
@login_required
def add_vehicle():
    if current_user.role not in ['admin', 'hub_admin', 'dispatcher']:
        return redirect(url_for('index'))
        
    vehicle_code = request.form.get('vehicle_code', '').strip().upper()
    license_plate = request.form.get('license_plate', '').strip()
    vehicle_type = request.form.get('vehicle_type', 'Bike')
    capacity_weight = float(request.form.get('capacity_weight', 100.0))
    capacity_volume = float(request.form.get('capacity_volume', 1.0))
    fuel_type = request.form.get('fuel_type', 'Petrol')
    hub_id = request.form.get('hub_id')
    remarks = request.form.get('remarks', '').strip()
    
    if not vehicle_code or not license_plate:
        flash("Validation Error: Vehicle Code and License Plate are required.", "error")
        return redirect(url_for('manage_vehicles'))
        
    dup_code = Vehicle.query.filter_by(vehicle_code=vehicle_code).first()
    if dup_code:
        flash(f"Vehicle Code '{vehicle_code}' already exists.", "error")
        return redirect(url_for('manage_vehicles'))
        
    dup_plate = Vehicle.query.filter_by(license_plate=license_plate).first()
    if dup_plate:
        flash(f"License Plate '{license_plate}' already exists.", "error")
        return redirect(url_for('manage_vehicles'))
        
    vehicle = Vehicle(
        vehicle_code=vehicle_code,
        license_plate=license_plate,
        vehicle_type=vehicle_type,
        capacity_weight=capacity_weight,
        capacity_volume=capacity_volume,
        fuel_type=fuel_type,
        current_status='Available',
        hub_id=int(hub_id) if hub_id else None,
        remarks=remarks
    )
    db.session.add(vehicle)
    db.session.commit()
    
    flash(f"Vehicle '{vehicle_code}' registered successfully!", "success")
    return redirect(url_for('manage_vehicles'))

@app.route('/admin/edit-vehicle/<int:id>', methods=['POST'])
@login_required
def edit_vehicle(id):
    if current_user.role not in ['admin', 'hub_admin', 'dispatcher']:
        return redirect(url_for('index'))
        
    vehicle = Vehicle.query.get_or_404(id)
    vehicle.vehicle_code = request.form.get('vehicle_code', '').strip().upper()
    vehicle.license_plate = request.form.get('license_plate', '').strip()
    vehicle.vehicle_type = request.form.get('vehicle_type')
    vehicle.current_status = request.form.get('current_status')
    vehicle.capacity_weight = float(request.form.get('capacity_weight', 100.0))
    vehicle.capacity_volume = float(request.form.get('capacity_volume', 1.0))
    vehicle.fuel_type = request.form.get('fuel_type')
    hub_id = request.form.get('hub_id')
    vehicle.hub_id = int(hub_id) if hub_id else None
    vehicle.remarks = request.form.get('remarks', '').strip()
    
    db.session.commit()
    flash(f"Vehicle '{vehicle.vehicle_code}' updated successfully!", "success")
    return redirect(url_for('manage_vehicles'))

@app.route('/admin/delete-vehicle/<int:id>', methods=['POST'])
@login_required
def delete_vehicle(id):
    if current_user.role not in ['admin', 'hub_admin']:
        return redirect(url_for('index'))
        
    vehicle = Vehicle.query.get_or_404(id)
    code = vehicle.vehicle_code
    db.session.delete(vehicle)
    db.session.commit()
    flash(f"Vehicle '{code}' removed successfully.", "success")
    return redirect(url_for('manage_vehicles'))

# --- VEHICLE MAINTENANCE MODULE ---

@app.route('/admin/maintenance')
@login_required
def manage_maintenance():
    if current_user.role not in ['admin', 'hub_admin', 'dispatcher', 'warehouse_staff']:
        return redirect(url_for('index'))
        
    hub_id = get_current_hub_id()
    if hub_id:
        maintenance_list = VehicleMaintenance.query.filter((VehicleMaintenance.hub_id == hub_id) | (VehicleMaintenance.hub_id == None)).order_by(VehicleMaintenance.created_at.desc()).all()
        vehicles = Vehicle.query.filter((Vehicle.hub_id == hub_id) | (Vehicle.hub_id == None)).all()
    else:
        maintenance_list = VehicleMaintenance.query.order_by(VehicleMaintenance.created_at.desc()).all()
        vehicles = Vehicle.query.all()
        
    return render_template('maintenance.html', active_page='maintenance', maintenance_list=maintenance_list, vehicles=vehicles)

@app.route('/admin/add-maintenance', methods=['POST'])
@login_required
def add_maintenance():
    if current_user.role not in ['admin', 'hub_admin', 'dispatcher']:
        return redirect(url_for('index'))
        
    vehicle_id = request.form.get('vehicle_id')
    maintenance_type = request.form.get('maintenance_type', 'Routine')
    cost = float(request.form.get('cost', 0.0))
    service_date_str = request.form.get('service_date')
    workshop = request.form.get('workshop', '').strip()
    description = request.form.get('description', '').strip()
    
    if not vehicle_id or not service_date_str:
        flash("Vehicle selection and service date are required.", "error")
        return redirect(url_for('manage_maintenance'))
        
    service_date = datetime.strptime(service_date_str, '%Y-%m-%d')
    vehicle = Vehicle.query.get_or_404(int(vehicle_id))
    
    vm = VehicleMaintenance(
        vehicle_id=vehicle.id,
        maintenance_type=maintenance_type,
        cost=cost,
        service_date=service_date,
        workshop=workshop,
        description=description,
        status='Scheduled',
        hub_id=vehicle.hub_id
    )
    vehicle.current_status = 'Maintenance'
    vehicle.last_service_date = service_date
    
    db.session.add(vm)
    db.session.commit()
    
    flash(f"Maintenance record for vehicle '{vehicle.vehicle_code}' scheduled!", "success")
    return redirect(url_for('manage_maintenance'))

@app.route('/admin/update-maintenance-status/<int:id>', methods=['POST'])
@login_required
def update_maintenance_status(id):
    if current_user.role not in ['admin', 'hub_admin', 'dispatcher']:
        return redirect(url_for('index'))
        
    vm = VehicleMaintenance.query.get_or_404(id)
    new_status = request.form.get('status', 'Completed')
    vm.status = new_status
    
    if new_status == 'Completed':
        vm.vehicle.current_status = 'Available'
        
    db.session.commit()
    flash(f"Maintenance status updated to {new_status}.", "success")
    return redirect(url_for('manage_maintenance'))

# --- DRIVER & VEHICLE ASSIGNMENT MODULE ---

@app.route('/admin/assignments')
@login_required
def manage_assignments():
    if current_user.role not in ['admin', 'hub_admin', 'dispatcher', 'booking_staff']:
        return redirect(url_for('index'))
        
    hub_id = get_current_hub_id()
    if hub_id:
        assignments = Assignment.query.filter((Assignment.hub_id == hub_id) | (Assignment.hub_id == None)).order_by(Assignment.assigned_date.desc()).all()
        drivers = Driver.query.filter((Driver.hub_id == hub_id) | (Driver.hub_id == None)).all()
        vehicles = Vehicle.query.filter((Vehicle.hub_id == hub_id) | (Vehicle.hub_id == None)).all()
        manifests = Manifest.query.filter((Manifest.hub_id == hub_id) | (Manifest.hub_id == None)).all()
    else:
        assignments = Assignment.query.order_by(Assignment.assigned_date.desc()).all()
        drivers = Driver.query.all()
        vehicles = Vehicle.query.all()
        manifests = Manifest.query.all()
        
    return render_template('assignments.html', active_page='assignments', assignments=assignments, drivers=drivers, vehicles=vehicles, manifests=manifests)

@app.route('/admin/create-assignment', methods=['POST'])
@login_required
def create_assignment():
    if current_user.role not in ['admin', 'hub_admin', 'dispatcher']:
        return redirect(url_for('index'))
        
    driver_id = request.form.get('driver_id')
    vehicle_id = request.form.get('vehicle_id')
    manifest_id = request.form.get('manifest_id')
    
    if not driver_id or not vehicle_id:
        flash("Validation Error: Selecting both Driver and Vehicle is mandatory.", "error")
        return redirect(url_for('manage_assignments'))
        
    driver = Driver.query.get_or_404(int(driver_id))
    vehicle = Vehicle.query.get_or_404(int(vehicle_id))
    
    # LICENSE CONSTRAINT ENFORCEMENT: Bike license -> Bike, Van license -> Van, etc.
    if not driver.can_drive_vehicle(vehicle):
        flash(f"License Restriction Violation: Driver {driver.name} holds a '{driver.license_type}' license and CANNOT operate a {vehicle.vehicle_type} ({vehicle.vehicle_code}). Bike license holders must be assigned a Bike, and Van license holders must be assigned a Van.", "error")
        return redirect(url_for('manage_assignments'))
        
    # BUSINESS RULE ENFORCEMENT: Availability & Single Active Assignment
    if driver.availability != 'Available':
        flash(f"Conflict Error: Driver {driver.name} is currently '{driver.availability}' and cannot be assigned.", "error")
        return redirect(url_for('manage_assignments'))
        
    if vehicle.current_status != 'Available':
        flash(f"Conflict Error: Vehicle {vehicle.vehicle_code} is currently '{vehicle.current_status}' and cannot be assigned.", "error")
        return redirect(url_for('manage_assignments'))
        
    active_driver_asgn = Assignment.query.filter_by(driver_id=driver.id, assignment_status='Active').first()
    if active_driver_asgn:
        flash(f"Single Assignment Violation: Driver {driver.name} already has an active assignment.", "error")
        return redirect(url_for('manage_assignments'))
        
    active_vehicle_asgn = Assignment.query.filter_by(vehicle_id=vehicle.id, assignment_status='Active').first()
    if active_vehicle_asgn:
        flash(f"Single Assignment Violation: Vehicle {vehicle.vehicle_code} already has an active assignment.", "error")
        return redirect(url_for('manage_assignments'))
        
    # Capacity & Vehicle Type Check if manifest linked
    manifest = None
    if manifest_id:
        manifest = Manifest.query.get(int(manifest_id))
        if manifest:
            if vehicle.vehicle_type == 'Bike':
                flash("Manifest Assignment Error: Manifests must be delivered using a truck or van, not a bike.", "error")
                return redirect(url_for('manage_assignments'))
            if manifest.total_weight > vehicle.capacity_weight:
                flash(f"Capacity Warning: Manifest weight ({manifest.total_weight}kg) exceeds vehicle max capacity ({vehicle.capacity_weight}kg).", "error")
                return redirect(url_for('manage_assignments'))
            
    asgn = Assignment(
        manifest_id=manifest.id if manifest else None,
        driver_id=driver.id,
        vehicle_id=vehicle.id,
        assigned_date=datetime.utcnow(),
        dispatch_time=datetime.utcnow(),
        assignment_status='Active',
        hub_id=driver.hub_id or vehicle.hub_id
    )
    
    # Automated status update
    driver.availability = 'On Delivery'
    vehicle.current_status = 'Delivering'
    
    if manifest:
        manifest.assigned_driver_id = driver.id
        manifest.assigned_vehicle_id = vehicle.id
        manifest.manifest_status = 'Dispatched'
        
    db.session.add(asgn)
    db.session.commit()
    
    flash(f"Assignment #ASG-{asgn.id} created! Courier {driver.name} dispatched with vehicle {vehicle.vehicle_code}.", "success")
    return redirect(url_for('manage_assignments'))

@app.route('/admin/complete-assignment/<int:id>', methods=['POST'])
@login_required
def complete_assignment(id):
    if current_user.role not in ['admin', 'hub_admin', 'dispatcher']:
        return redirect(url_for('index'))
        
    asgn = Assignment.query.get_or_404(id)
    asgn.assignment_status = 'Returned'
    asgn.actual_return = datetime.utcnow()
    
    asgn.driver.availability = 'Available'
    asgn.vehicle.current_status = 'Available'
    
    db.session.commit()
    flash(f"Assignment #ASG-{asgn.id} completed. Driver & Vehicle released to Available status.", "success")
    return redirect(url_for('manage_assignments'))

# --- MANIFEST MANAGEMENT MODULE ---

@app.route('/admin/manifests')
@login_required
def manage_manifests():
    if current_user.role not in ['admin', 'hub_admin', 'dispatcher', 'warehouse_staff']:
        return redirect(url_for('index'))
        
    hub_id = get_current_hub_id()
    if hub_id:
        manifests = Manifest.query.filter((Manifest.hub_id == hub_id) | (Manifest.origin_hub_id == hub_id) | (Manifest.destination_hub_id == hub_id)).order_by(Manifest.created_at.desc()).all()
    else:
        manifests = Manifest.query.order_by(Manifest.created_at.desc()).all()
        
    hubs = Hub.query.all()
    return render_template('manifests.html', active_page='manifests', manifests=manifests, hubs=hubs)

@app.route('/admin/create-manifest', methods=['POST'])
@login_required
def create_manifest():
    if current_user.role not in ['admin', 'hub_admin', 'dispatcher']:
        return redirect(url_for('index'))
        
    origin_hub_id = request.form.get('origin_hub_id')
    destination_hub_id = request.form.get('destination_hub_id')
    manifest_type = request.form.get('manifest_type', 'Inter-Hub Transfer').strip()
    route = request.form.get('route', '').strip()
    
    if not origin_hub_id:
        flash("Origin Hub is required.", "error")
        return redirect(url_for('manage_manifests'))
        
    origin_hub = Hub.query.get(int(origin_hub_id))
    dest_id = None
    if manifest_type == 'Inter-Hub Transfer':
        if not destination_hub_id:
            flash("Destination Hub is required for Inter-Hub cargo transfers.", "error")
            return redirect(url_for('manage_manifests'))
        dest_id = int(destination_hub_id)
        if not route and origin_hub:
            dest_hub = Hub.query.get(dest_id)
            route = f"{origin_hub.name} Hub -> {dest_hub.name if dest_hub else ''} Hub Transfer"
    else:
        # Hub to Home Delivery
        if destination_hub_id and destination_hub_id.isdigit():
            dest_id = int(destination_hub_id)
        if not route and origin_hub:
            route = f"{origin_hub.name} Hub -> Direct Customer Doorsteps (Home Delivery)"
        
    manifest_number = f"MNF-2026-{random.randint(1000, 9999)}"
    manifest = Manifest(
        manifest_number=manifest_number,
        manifest_type=manifest_type,
        route=route,
        origin_hub_id=int(origin_hub_id),
        destination_hub_id=dest_id,
        manifest_status='Draft',
        hub_id=int(origin_hub_id)
    )
    db.session.add(manifest)
    db.session.commit()
    
    flash(f"{manifest_type} Manifest '{manifest_number}' created successfully!", "success")
    return redirect(url_for('manifest_details', id=manifest.id))

@app.route('/admin/manifest/<int:id>')
@login_required
def manifest_details(id):
    manifest = Manifest.query.get_or_404(id)
    if current_user.role == 'driver':
        driver = Driver.query.filter_by(user_id=current_user.id).first()
        if not driver or manifest.assigned_driver_id != driver.id:
            flash("Access Denied: Manifest is not assigned to your account.", "error")
            return redirect(url_for('driver_manifests'))
    elif current_user.role not in ['admin', 'hub_admin', 'dispatcher', 'warehouse_staff', 'booking_staff']:
        return redirect(url_for('index'))
        
    pending_parcels = Parcel.query.filter_by(status='Pending').all()
    available_drivers = Driver.query.filter_by(availability='Available').all()
    available_vehicles = Vehicle.query.filter_by(current_status='Available').all()
    return render_template('manifest_details.html', active_page='manifests', manifest=manifest, pending_parcels=pending_parcels, available_drivers=available_drivers, available_vehicles=available_vehicles)

@app.route('/manifest/<int:id>/voucher')
@login_required
def view_manifest(id):
    return manifest_details(id)

@app.route('/admin/manifest/<int:id>/assign-transport', methods=['POST'])
@login_required
def assign_transport_to_manifest(id):
    if current_user.role not in ['admin', 'hub_admin', 'dispatcher']:
        return redirect(url_for('index'))
        
    manifest = Manifest.query.get_or_404(id)
    driver_id = request.form.get('driver_id')
    vehicle_id = request.form.get('vehicle_id')
    
    if not driver_id or not vehicle_id:
        flash("Both Driver and Vehicle must be selected for manifest dispatch assignment.", "error")
        return redirect(url_for('manifest_details', id=manifest.id))
        
    driver = Driver.query.get_or_404(int(driver_id))
    vehicle = Vehicle.query.get_or_404(int(vehicle_id))
    
    # LICENSE CONSTRAINT ENFORCEMENT: Bike license -> Bike, Van license -> Van, etc.
    if not driver.can_drive_vehicle(vehicle):
        flash(f"License Incompatibility Error: Driver {driver.name} holds a '{driver.license_type}' license and CANNOT operate a {vehicle.vehicle_type} ({vehicle.vehicle_code}). Bike license holders must be assigned a Bike, and Van license holders must be assigned a Van.", "error")
        return redirect(url_for('manifest_details', id=manifest.id))
        
    # Capacity Check
    if manifest.total_weight > vehicle.capacity_weight:
        flash(f"Capacity Error: Manifest weight ({manifest.total_weight:.1f} kg) exceeds vehicle max payload capacity ({vehicle.capacity_weight:.1f} kg) for {vehicle.vehicle_code} ({vehicle.vehicle_type}).", "error")
        return redirect(url_for('manifest_details', id=manifest.id))
        
    if manifest.total_volume_m3 > vehicle.capacity_volume:
        flash(f"Volume Error: Manifest volume ({manifest.total_volume_m3:.2f} m³) exceeds vehicle volumetric capacity ({vehicle.capacity_volume:.2f} m³) for {vehicle.vehicle_code}.", "error")
        return redirect(url_for('manifest_details', id=manifest.id))
        
    # Free previous driver/vehicle if any
    if manifest.assigned_driver and manifest.assigned_driver_id != driver.id:
        manifest.assigned_driver.availability = 'Available'
    if manifest.assigned_vehicle and manifest.assigned_vehicle_id != vehicle.id:
        manifest.assigned_vehicle.current_status = 'Available'
        
    manifest.assigned_driver_id = driver.id
    manifest.assigned_vehicle_id = vehicle.id
    driver.availability = 'On Delivery'
    vehicle.current_status = 'Delivering'
    
    # Synchronize assigned driver to all parcels in this manifest
    for item in manifest.items:
        if item.parcel:
            item.parcel.assigned_driver_id = driver.id
    
    # Create or update assignment
    existing_asgn = Assignment.query.filter_by(manifest_id=manifest.id, assignment_status='Active').first()
    if not existing_asgn:
        new_asgn = Assignment(
            manifest_id=manifest.id,
            driver_id=driver.id,
            vehicle_id=vehicle.id,
            assigned_date=datetime.now(),
            dispatch_time=datetime.now(),
            assignment_status='Active',
            hub_id=manifest.origin_hub_id or driver.hub_id
        )
        db.session.add(new_asgn)
    else:
        existing_asgn.driver_id = driver.id
        existing_asgn.vehicle_id = vehicle.id
        
    db.session.commit()
    flash(f"Transport successfully assigned! Courier {driver.name} and Vehicle {vehicle.vehicle_code} ({vehicle.license_plate}, Max {vehicle.capacity_weight}kg) assigned to Manifest {manifest.manifest_number}.", "success")
    return redirect(url_for('manifest_details', id=manifest.id))

@app.route('/admin/manifest/<int:id>/add-parcel', methods=['POST'])
@login_required
def add_parcel_to_manifest(id):
    manifest = Manifest.query.get_or_404(id)
    parcel_id = request.form.get('parcel_id')
    
    if parcel_id:
        parcel = Parcel.query.get(int(parcel_id))
        if parcel:
            item = ManifestItem(manifest_id=manifest.id, parcel_id=parcel.id)
            parcel.manifest_id = manifest.id
            if manifest.assigned_driver_id:
                parcel.assigned_driver_id = manifest.assigned_driver_id
            parcel.status = 'Manifested'
            
            manifest.total_parcels += 1
            manifest.total_weight += parcel.weight
            
            db.session.add(item)
            db.session.commit()
            flash(f"Parcel {parcel.tracking_id} added to manifest {manifest.manifest_number}.", "success")
            
    return redirect(url_for('manifest_details', id=manifest.id))

@app.route('/admin/manifest/<int:id>/remove-parcel/<int:item_id>', methods=['POST'])
@login_required
def remove_parcel_from_manifest(id, item_id):
    manifest = Manifest.query.get_or_404(id)
    item = ManifestItem.query.get_or_404(item_id)
    
    if item.parcel:
        item.parcel.status = 'Pending'
        item.parcel.manifest_id = None
        item.parcel.assigned_driver_id = None
        manifest.total_parcels = max(0, manifest.total_parcels - 1)
        manifest.total_weight = max(0.0, manifest.total_weight - item.parcel.weight)
        
    db.session.delete(item)
    db.session.commit()
    flash("Parcel removed from manifest batch.", "success")
    return redirect(url_for('manifest_details', id=manifest.id))

@app.route('/admin/manifest/<int:id>/dispatch', methods=['POST'])
@login_required
def dispatch_manifest(id):
    manifest = Manifest.query.get_or_404(id)
    manifest.manifest_status = 'Dispatched'
    manifest.dispatch_date = datetime.utcnow()
    
    if manifest.assigned_driver:
        manifest.assigned_driver.availability = 'On Delivery'
    if manifest.assigned_vehicle:
        manifest.assigned_vehicle.current_status = 'Delivering'
        
    for item in manifest.items:
        if item.parcel:
            if manifest.assigned_driver_id and not item.parcel.assigned_driver_id:
                item.parcel.assigned_driver_id = manifest.assigned_driver_id
            if manifest.is_home_delivery:
                item.parcel.status = 'Out For Delivery'
                db.session.add(TrackingHistory(
                    parcel_id=item.parcel.id, 
                    status='Out For Delivery', 
                    location=f"Out for direct home delivery via Manifest {manifest.manifest_number} with Courier {manifest.assigned_driver.name if manifest.assigned_driver else 'Assigned Driver'}"
                ))
            else:
                item.parcel.status = 'In Transit'
                db.session.add(TrackingHistory(
                    parcel_id=item.parcel.id, 
                    status='In Transit', 
                    location=f"In Transit via Inter-Hub Manifest {manifest.manifest_number}"
                ))
        
    db.session.commit()
    flash(f"Manifest {manifest.manifest_number} successfully dispatched!", "success")
    return redirect(url_for('manifest_details', id=manifest.id))

@app.route('/admin/manifest/<int:id>/complete', methods=['POST'])
@login_required
def complete_manifest(id):
    manifest = Manifest.query.get_or_404(id)
    manifest.manifest_status = 'Completed'
    manifest.arrival_date = datetime.utcnow()
    
    if manifest.assigned_driver:
        manifest.assigned_driver.availability = 'Available'
    if manifest.assigned_vehicle:
        manifest.assigned_vehicle.current_status = 'Available'
        
    db.session.commit()
    flash(f"Manifest {manifest.manifest_number} marked as Completed.", "success")
    return redirect(url_for('manifest_details', id=manifest.id))

# --- MERCHANDISE MODULE ---

@app.route('/admin/merchandise')
@login_required
def manage_merchandise():
    merchandise_list = Merchandise.query.all()
    return render_template('merchandise.html', active_page='merchandise', merchandise_list=merchandise_list)

@app.route('/admin/add-merchandise', methods=['POST'])
@login_required
def add_merchandise():
    m_type = request.form.get('type', '').strip()
    category = request.form.get('category', '').strip()
    description = request.form.get('description', '').strip()
    default_charge = float(request.form.get('default_charge', 100.0))
    fragile = request.form.get('fragile') == 'yes'
    hazardous = request.form.get('hazardous') == 'yes'
    temperature_controlled = request.form.get('temperature_controlled') == 'yes'
    
    if not m_type:
        flash("Merchandise type name is required.", "error")
        return redirect(url_for('manage_merchandise'))
        
    m = Merchandise(
        type=m_type,
        category=category,
        description=description,
        default_charge=default_charge,
        fragile=fragile,
        hazardous=hazardous,
        temperature_controlled=temperature_controlled
    )
    db.session.add(m)
    db.session.commit()
    
    flash(f"Merchandise type '{m_type}' added to catalog!", "success")
    return redirect(url_for('manage_merchandise'))

@app.route('/admin/delete-merchandise/<int:id>', methods=['POST'])
@login_required
def delete_merchandise(id):
    m = Merchandise.query.get_or_404(id)
    db.session.delete(m)
    db.session.commit()
    flash("Merchandise type deleted.", "success")
    return redirect(url_for('manage_merchandise'))

# --- USER & ROLE MANAGEMENT MODULE ---

@app.route('/admin/users')
@login_required
def manage_users():
    if current_user.role != 'admin':
        flash("Access Denied: Main Admin privileges required.", "error")
        return redirect(url_for('index'))
        
    all_users = User.query.order_by(User.id.asc()).all()
    staff_users = [u for u in all_users if u.role not in ['driver', 'hub_admin']]
    drivers = Driver.query.order_by(Driver.id.asc()).all()
    hub_admins = HubAdmin.query.order_by(HubAdmin.id.asc()).all()
    hubs = Hub.query.all()
    
    return render_template(
        'users.html', 
        active_page='users', 
        users=all_users,
        staff_users=staff_users,
        drivers=drivers,
        hub_admins=hub_admins,
        hubs=hubs
    )

@app.route('/admin/create-user', methods=['POST'])
@login_required
def create_user():
    if current_user.role != 'admin':
        return redirect(url_for('index'))
        
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    role = request.form.get('role', 'booking_staff')
    permissions = request.form.get('permissions', 'view,create,edit,assign,dispatch,reports')
    
    if not username or not password:
        flash("Username and Password are required.", "error")
        return redirect(url_for('manage_users'))
        
    existing = User.query.filter_by(username=username).first()
    if existing:
        flash(f"Username '{username}' is already taken.", "error")
        return redirect(url_for('manage_users'))
        
    user = User(
        username=username,
        password_hash=generate_password_hash(password),
        role=role,
        permissions=permissions
    )
    db.session.add(user)
    db.session.commit()
    
    flash(f"User account '{username}' created with role '{role}'!", "success")
    return redirect(url_for('manage_users'))

@app.route('/admin/edit-user/<int:id>', methods=['POST'])
@login_required
def edit_user(id):
    if current_user.role != 'admin':
        return redirect(url_for('index'))
        
    user = User.query.get_or_404(id)
    user.username = request.form.get('username', '').strip()
    user.role = request.form.get('role')
    user.permissions = request.form.get('permissions')
    
    password = request.form.get('password')
    if password:
        user.password_hash = generate_password_hash(password)
        
    db.session.commit()
    flash(f"User account '{user.username}' updated!", "success")
    return redirect(url_for('manage_users'))

# --- REPORTS MODULE & EXCEL EXPORTER ---

@app.route('/admin/reports')
@login_required
def view_reports():
    if current_user.role not in ['admin', 'hub_admin', 'dispatcher', 'booking_staff']:
        return redirect(url_for('index'))
        
    report_type = request.args.get('report_type', 'daily_booking')
    hub_id = request.args.get('hub_id')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    status = request.args.get('status')
    
    hubs = Hub.query.all()
    
    # Base Parcel Query
    query = Parcel.query
    if current_user.role == 'hub_admin':
        hub_name = get_current_hub_name()
        if hub_name:
            query = query.filter((Parcel.pickup_hub == hub_name) | (Parcel.delivery_hub == hub_name))
    elif hub_id:
        hub = Hub.query.get(int(hub_id))
        if hub:
            query = query.filter((Parcel.pickup_hub == hub.name) | (Parcel.delivery_hub == hub.name))
            
    if status:
        query = query.filter(Parcel.status == status)
        
    if report_type in ['daily_booking', 'delivery', 'pending', 'revenue', 'failed_deliveries']:
        if report_type == 'pending':
            query = query.filter(Parcel.status == 'Pending')
        elif report_type == 'failed_deliveries':
            query = query.filter(Parcel.delivery_attempts > 0)
            
        report_data = query.order_by(Parcel.created_at.desc()).all()
        total_aggregate_val = sum(p.delivery_charge for p in report_data)
    elif report_type == 'driver_performance':
        report_data = Driver.query.all()
        total_aggregate_val = sum(d.completed_deliveries for d in report_data)
    elif report_type == 'vehicle_utilization':
        report_data = Vehicle.query.all()
        total_aggregate_val = len(report_data)
    elif report_type == 'manifest':
        report_data = Manifest.query.all()
        total_aggregate_val = sum(m.total_weight for m in report_data)
    else:
        report_data = query.all()
        total_aggregate_val = sum(p.delivery_charge for p in report_data)
        
    return render_template(
        'reports.html',
        active_page='reports',
        report_data=report_data,
        selected_report=report_type,
        selected_hub_id=hub_id,
        start_date=start_date_str,
        end_date=end_date_str,
        selected_status=status,
        hubs=hubs,
        total_aggregate_val=total_aggregate_val
    )

@app.route('/admin/reports/export/excel')
@login_required
def export_reports_excel():
    report_type = request.args.get('report_type', 'daily_booking')
    
    si = StringIO()
    cw = csv.writer(si)
    
    if report_type in ['daily_booking', 'delivery', 'pending', 'revenue', 'failed_deliveries']:
        cw.writerow(['Tracking ID', 'Booked Date', 'Sender Name', 'Receiver Name', 'Pickup Hub', 'Delivery Hub', 'Weight (kg)', 'Charge (Rs.)', 'Status', 'Payment Status'])
        parcels = Parcel.query.all()
        for p in parcels:
            cw.writerow([p.tracking_id, p.created_at.strftime('%Y-%m-%d %H:%M'), p.sender_name, p.receiver_name, p.pickup_hub, p.delivery_hub, p.weight, p.delivery_charge, p.status, p.payment_status])
    elif report_type == 'driver_performance':
        cw.writerow(['Driver Name', 'Employee Code', 'Phone', 'Availability', 'Completed Deliveries', 'Avg Time (min)', 'Rating'])
        drivers = Driver.query.all()
        for d in drivers:
            cw.writerow([d.name, d.employee_code, d.phone, d.availability, d.completed_deliveries, d.average_delivery_time, d.rating])
    else:
        cw.writerow(['Vehicle Code', 'License Plate', 'Type', 'Weight Capacity (kg)', 'Volume (m3)', 'Status'])
        vehicles = Vehicle.query.all()
        for v in vehicles:
            cw.writerow([v.vehicle_code, v.license_plate, v.vehicle_type, v.capacity_weight, v.capacity_volume, v.current_status])
            
    output = Response(si.getvalue(), mimetype="text/csv")
    output.headers["Content-Disposition"] = f"attachment; filename=parcelfleet_report_{report_type}.csv"
    return output

# --- NOTIFICATION CENTER API ---

@app.route('/api/admin/notifications')
@login_required
def api_admin_notifications():
    notifications = []
    
    # 1. Maintenance overdue / due soon warnings
    overdue_maints = VehicleMaintenance.query.filter_by(status='Scheduled').all()
    for m in overdue_maints:
        notifications.append({
            'title': f"Maintenance Due: {m.vehicle.vehicle_code}",
            'message': f"{m.maintenance_type} scheduled for {m.service_date.strftime('%Y-%m-%d')}.",
            'type': 'warning'
        })
        
    # 2. Insurance / License expiry warnings
    vehicles = Vehicle.query.all()
    now = datetime.utcnow()
    for v in vehicles:
        if v.insurance_expiry and v.insurance_expiry < now:
            notifications.append({
                'title': f"Insurance Expired: {v.vehicle_code}",
                'message': f"Vehicle {v.license_plate} insurance expired on {v.insurance_expiry.strftime('%Y-%m-%d')}.",
                'type': 'danger'
            })
            
    drivers = Driver.query.all()
    for d in drivers:
        if d.license_expiry and d.license_expiry < now:
            notifications.append({
                'title': f"Driver License Expired: {d.name}",
                'message': f"License #{d.license_number} expired.",
                'type': 'danger'
            })
            
    return jsonify({'notifications': notifications})

# --- EXISTING PARCEL, DRIVER & HUB ROUTES (PRESERVED) ---

@app.route('/admin/parcels')
@login_required
def manage_parcels():
    if current_user.role not in ['admin', 'hub_admin', 'booking_staff', 'warehouse_staff', 'dispatcher', 'delivery_staff', 'branch_staff']:
        return redirect(url_for('index'))
        
    hub_name = get_current_hub_name()
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
    if current_user.role not in ['admin', 'hub_admin', 'booking_staff', 'warehouse_staff', 'dispatcher', 'delivery_staff', 'branch_staff']:
        return redirect(url_for('index'))
        
    parcel = Parcel.query.get_or_404(id)
    hub_name = get_current_hub_name()
    if hub_name and parcel.pickup_hub != hub_name and parcel.delivery_hub != hub_name:
        flash("Access Denied: This parcel does not belong to your hub.", "error")
        return redirect(url_for('manage_parcels'))
        
    drivers = Driver.query.all()
    # Sort drivers: Available drivers first, then by capacity adequacy for the parcel, then by name
    drivers.sort(key=lambda d: (
        0 if d.availability == 'Available' else 1,
        0 if (d.effective_capacity_weight >= (parcel.weight or 0.0)) else 1,
        d.name
    ))
    hubs = Hub.query.all()
    return render_template('parcel_details.html', active_page='parcels', parcel=parcel, drivers=drivers, hubs=hubs, hub_name=hub_name)

@app.route('/admin/book-parcel', methods=['POST'])
@login_required
def book_parcel():
    if current_user.role not in ['admin', 'hub_admin', 'booking_staff', 'branch_staff']:
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
    
    if not sender_name or not receiver_name or not pickup_address or not delivery_address:
        flash("Validation Error: All address and contact names are required.", "error")
        return redirect(url_for('manage_parcels'))

    if not validate_phone(sender_phone) or not validate_phone(receiver_phone):
        flash("Validation Error: Invalid phone format.", "error")
        return redirect(url_for('manage_parcels'))
        
    if weight <= 0 or length <= 0 or width <= 0 or height <= 0 or delivery_charge <= 0:
        flash("Validation Error: Weight and dimensions must be positive numbers.", "error")
        return redirect(url_for('manage_parcels'))
        
    if not validate_coords(pickup_latitude, pickup_longitude) or not validate_coords(delivery_latitude, delivery_longitude):
        flash("Validation Error: Coordinates must reside within Kathmandu Valley bounds.", "error")
        return redirect(url_for('manage_parcels'))

    tags = request.form.getlist('special_tags')
    special_tags = ', '.join(tags) if tags else None
    
    while True:
        tracking_id = f"PF2026{random.randint(1000, 9999)}"
        existing = Parcel.query.filter_by(tracking_id=tracking_id).first()
        if not existing:
            break
            
    pickup_hub_name = get_closest_hub(pickup_latitude, pickup_longitude)
    delivery_hub_name = get_closest_hub(delivery_latitude, delivery_longitude)
    
    hub_name = get_current_hub_name()
    if hub_name:
        pickup_hub_name = hub_name
    
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
    
    hist = TrackingHistory(parcel_id=parcel.id, status='Pending', location=f"Home pickup: {pickup_address}")
    notif = NotificationLog(parcel_id=parcel.id, message=f"Order {tracking_id} booked. Billing: Rs. {delivery_charge}.", type='Created')
    db.session.add(hist)
    db.session.add(notif)
    db.session.commit()
    
    flash(f"Parcel order {tracking_id} successfully booked!", "success")
    return redirect(url_for('manage_parcels'))

@app.route('/admin/edit-parcel/<int:id>', methods=['POST'])
@login_required
def edit_parcel(id):
    if current_user.role not in ['admin', 'hub_admin', 'booking_staff', 'dispatcher']:
        return redirect(url_for('index'))
        
    parcel = Parcel.query.get_or_404(id)
    old_status = parcel.status
    old_driver_id = parcel.assigned_driver_id
    
    parcel.sender_name = request.form.get('sender_name', '').strip()
    parcel.sender_phone = request.form.get('sender_phone', '').strip()
    parcel.receiver_name = request.form.get('receiver_name', '').strip()
    parcel.receiver_phone = request.form.get('receiver_phone', '').strip()
    parcel.pickup_address = request.form.get('pickup_address', '').strip()
    parcel.delivery_address = request.form.get('delivery_address', '').strip()

    try:
        parcel.pickup_latitude = float(request.form.get('pickup_latitude', 0.0))
        parcel.pickup_longitude = float(request.form.get('pickup_longitude', 0.0))
        parcel.delivery_latitude = float(request.form.get('delivery_latitude', 0.0))
        parcel.delivery_longitude = float(request.form.get('delivery_longitude', 0.0))
        parcel.weight = float(request.form.get('weight', 0.0))
        parcel.length = float(request.form.get('length', 0.0))
        parcel.width = float(request.form.get('width', 0.0))
        parcel.height = float(request.form.get('height', 0.0))
        parcel.delivery_charge = float(request.form.get('delivery_charge', 0.0))
    except ValueError:
        flash("Validation Error: Invalid numerical values provided.", "error")
        return redirect(url_for('manage_parcels'))
        
    parcel.parcel_type = request.form.get('parcel_type')
    parcel.payment_status = request.form.get('payment_status')
    
    tags = request.form.getlist('special_tags')
    parcel.special_tags = ', '.join(tags) if tags else None
    
    new_status = request.form.get('status')
    new_driver_id = request.form.get('assigned_driver_id')
    
    if new_status and new_status != old_status:
        parcel.status = new_status
        loc = f"Home Delivery: {parcel.delivery_address}" if new_status in ['Delivered', 'Out For Delivery', 'Failed Attempt'] else f"Home Pickup: {parcel.pickup_address}"
        hist = TrackingHistory(parcel_id=parcel.id, status=new_status, location=loc)
        notif = NotificationLog(parcel_id=parcel.id, message=f"Status updated to {new_status} by admin.", type='Created')
        db.session.add(hist)
        db.session.add(notif)
        
        if new_status in ['Delivered', 'Cancelled'] and parcel.assigned_driver:
            parcel.assigned_driver.availability = 'Available'
            if new_status == 'Delivered':
                parcel.assigned_driver.completed_deliveries += 1
                parcel.delivered_at = datetime.utcnow()
                
    if new_driver_id is not None and new_driver_id != '':
        new_driver_id = int(new_driver_id)
        if new_driver_id != old_driver_id:
            if parcel.assigned_driver:
                parcel.assigned_driver.availability = 'Available'
                
            driver = Driver.query.get(new_driver_id)
            if driver:
                # Business rule validation: Weight limits and vehicle type allocation
                if parcel.weight > 5.0:
                    flash("Validation Error: Parcels heavier than 5 kg must be grouped as a manifest and delivered using a truck or van.", "error")
                    return redirect(url_for('parcel_details', id=parcel.id))
                    
                if not driver.assigned_vehicle or driver.assigned_vehicle.vehicle_type != 'Bike':
                    flash("Validation Error: Small parcels (<= 5 kg) must be delivered by a bike driver.", "error")
                    return redirect(url_for('parcel_details', id=parcel.id))
                    
                parcel.assigned_driver_id = driver.id
                driver.availability = 'On Delivery'
                if parcel.status == 'Pending':
                    parcel.status = 'Assigned'
                    
                hist = TrackingHistory(parcel_id=parcel.id, status=parcel.status, location=parcel.pickup_address)
                notif = NotificationLog(parcel_id=parcel.id, message=f"Driver {driver.name} assigned.", type='Assigned')
                db.session.add(hist)
                db.session.add(notif)
    elif new_driver_id == '':
        if parcel.assigned_driver:
            parcel.assigned_driver.availability = 'Available'
        parcel.assigned_driver_id = None
        if parcel.status == 'Assigned':
            parcel.status = 'Pending'
            
    db.session.commit()
    flash(f"Parcel {parcel.tracking_id} updated successfully!", "success")
    return redirect(url_for('parcel_details', id=parcel.id))

@app.route('/admin/assign-driver-manual/<int:id>', methods=['POST'])
@login_required
def assign_driver_manual(id):
    if current_user.role not in ['admin', 'hub_admin', 'dispatcher', 'booking_staff', 'branch_manager']:
        return redirect(url_for('index'))
        
    parcel = Parcel.query.get_or_404(id)
    driver_id = request.form.get('driver_id')
    
    if driver_id:
        driver = Driver.query.get(int(driver_id))
        if driver:
            # Capacity validation based on vehicle limits
            cap_w = float(driver.effective_capacity_weight)
            cap_v = float(driver.effective_capacity_volume)
            v_type = driver.vehicle_type_name
            
            # Calculate driver current load
            driver_parcels = driver.parcels or []
            current_weight = sum([p.weight for p in driver_parcels if p.status not in ['Delivered', 'Cancelled'] and p.id != parcel.id])
            parcel_vol = (parcel.length * parcel.width * parcel.height) / 1000000.0 if (parcel.length and parcel.width and parcel.height) else 0.005
            
            if current_weight + parcel.weight > cap_w + 1e-6:
                flash(f"Capacity Warning: Driver {driver.name}'s vehicle ({v_type}) has limit of {cap_w} kg (Current Load: {round(current_weight, 1)} kg). Parcel weight is {parcel.weight} kg.", "error")
                return redirect(request.referrer or url_for('manage_parcels'))
                
            parcel.assigned_driver_id = driver.id
            parcel.status = 'Assigned'
            driver.availability = 'On Delivery'
            
            hist = TrackingHistory(parcel_id=parcel.id, status='Assigned', location=parcel.pickup_address)
            notif = NotificationLog(parcel_id=parcel.id, message=f"Driver {driver.name} assigned based on location proximity & vehicle capacity.", type='Assigned')
            db.session.add(hist)
            db.session.add(notif)
            db.session.commit()
            
            flash(f"Driver {driver.name} ({vehicle.vehicle_type if vehicle else 'Bike'}) assigned to {parcel.tracking_id} successfully!", "success")
            
    return redirect(request.referrer or url_for('manage_parcels'))

@app.route('/admin/auto-assign-parcel/<int:id>', methods=['POST'])
@login_required
def auto_assign_single_parcel(id):
    if current_user.role not in ['admin', 'hub_admin', 'dispatcher', 'booking_staff', 'branch_manager']:
        return redirect(url_for('index'))
        
    parcel = Parcel.query.get_or_404(id)
    available_drivers = Driver.query.filter(Driver.availability.in_(['Available', 'On Delivery'])).all()
    
    if not available_drivers:
        flash("No active drivers available in the fleet.", "warning")
        return redirect(request.referrer or url_for('manage_parcels'))
        
    driver, distance = greedy_driver_assignment(parcel, available_drivers)
    if not driver:
        flash(f"No driver found with sufficient vehicle capacity for parcel {parcel.tracking_id} ({parcel.weight} kg).", "error")
        return redirect(request.referrer or url_for('manage_parcels'))
        
    parcel.assigned_driver_id = driver.id
    parcel.status = 'Assigned'
    driver.availability = 'On Delivery'
    
    hist = TrackingHistory(parcel_id=parcel.id, status='Assigned', location=parcel.pickup_address)
    notif = NotificationLog(parcel_id=parcel.id, message=f"Auto-assigned to {driver.name} ({round(distance, 1)} km away) based on location & capacity.", type='Assigned')
    db.session.add(hist)
    db.session.add(notif)
    db.session.commit()
    
    flash(f"Parcel {parcel.tracking_id} auto-assigned to {driver.name} ({round(distance, 1)} km away, Vehicle: {driver.assigned_vehicle.vehicle_type if driver.assigned_vehicle else 'Bike'})!", "success")
    return redirect(request.referrer or url_for('manage_parcels'))

@app.route('/admin/run-fcfs-dispatch', methods=['POST'])
@app.route('/admin/auto-assign-all', methods=['POST'])
@login_required
def run_fcfs_dispatch():
    if current_user.role not in ['admin', 'hub_admin', 'dispatcher', 'booking_staff', 'branch_manager']:
        return redirect(url_for('index'))
        
    hub_name = get_current_hub_name()
    if hub_name:
        pending_parcels = Parcel.query.filter_by(status='Pending').filter((Parcel.pickup_hub == hub_name) | (Parcel.delivery_hub == hub_name)).order_by(Parcel.created_at.asc()).all()
    else:
        pending_parcels = Parcel.query.filter_by(status='Pending').order_by(Parcel.created_at.asc()).all()
        
    if not pending_parcels:
        flash("No pending parcel orders found in queue.", "info")
        return redirect(request.referrer or url_for('admin_dashboard'))
        
    available_drivers = Driver.query.filter(Driver.availability.in_(['Available', 'On Delivery'])).all()
    if not available_drivers:
        flash("No available drivers found in fleet.", "warning")
        return redirect(request.referrer or url_for('admin_dashboard'))
        
    # Run multi-courier capacity & location optimization
    optimization_result = multi_courier_optimization(available_drivers, pending_parcels)
    
    assigned_count = 0
    for route in optimization_result['courier_routes']:
        driver = Driver.query.get(route['courier_id'])
        if not driver:
            continue
            
        driver.availability = 'On Delivery'
        for stop in route['ordered_stops']:
            parcel = Parcel.query.get(stop['parcel_id'])
            if parcel and parcel.status == 'Pending':
                parcel.assigned_driver_id = driver.id
                parcel.status = 'Assigned'
                
                hist = TrackingHistory(parcel_id=parcel.id, status='Assigned', location=parcel.pickup_address)
                notif = NotificationLog(parcel_id=parcel.id, message=f"Auto-assigned to {driver.name} (Stop #{stop['stop_number']}).", type='Assigned')
                db.session.add(hist)
                db.session.add(notif)
                assigned_count += 1
                
    db.session.commit()
    
    unassigned_count = len(optimization_result['unassigned_deliveries'])
    if unassigned_count > 0:
        flash(f"Auto-dispatch complete: Assigned {assigned_count} parcels. {unassigned_count} parcels remain unassigned due to vehicle capacity limits.", "warning")
    else:
        flash(f"Auto-dispatch complete! Successfully assigned all {assigned_count} parcels to optimal drivers based on location & vehicle capacity.", "success")
        
    return redirect(request.referrer or url_for('admin_dashboard'))


# --- MULTI-COURIER DELIVERY OPTIMIZATION MODULE ---

@app.route('/admin/delivery-optimization')
@login_required
def delivery_optimization():
    if current_user.role not in ['admin', 'hub_admin', 'dispatcher', 'booking_staff']:
        return redirect(url_for('index'))
        
    hub_name = get_current_hub_name()
    hubs = Hub.query.all()
    
    # Query pending parcels
    if hub_name:
        pending_parcels = Parcel.query.filter_by(status='Pending').filter(
            (Parcel.pickup_hub == hub_name) | (Parcel.delivery_hub == hub_name)
        ).order_by(Parcel.created_at.asc()).all()
        available_drivers = Driver.query.filter(
            Driver.availability == 'Available'
        ).all()
        # Prefer drivers at current hub if assigned
        hub_drivers = [d for d in available_drivers if d.hub and d.hub.name == hub_name]
        if hub_drivers:
            available_drivers = hub_drivers
    else:
        pending_parcels = Parcel.query.filter_by(status='Pending').order_by(Parcel.created_at.asc()).all()
        available_drivers = Driver.query.filter_by(availability='Available').all()
        
    # Run multi-courier optimization algorithm
    optimization_result = multi_courier_optimization(available_drivers, pending_parcels)
    
    return render_template(
        'delivery_optimization.html',
        active_page='optimization',
        optimization_result=optimization_result,
        pending_parcels=pending_parcels,
        available_drivers=available_drivers,
        hubs=hubs,
        hub_name=hub_name
    )

@app.route('/api/optimize-dispatch')
@login_required
def api_optimize_dispatch():
    hub_name = get_current_hub_name()
    if hub_name:
        pending_parcels = Parcel.query.filter_by(status='Pending').filter(
            (Parcel.pickup_hub == hub_name) | (Parcel.delivery_hub == hub_name)
        ).order_by(Parcel.created_at.asc()).all()
        available_drivers = Driver.query.filter(
            Driver.availability == 'Available'
        ).all()
        hub_drivers = [d for d in available_drivers if d.hub and d.hub.name == hub_name]
        if hub_drivers:
            available_drivers = hub_drivers
    else:
        pending_parcels = Parcel.query.filter_by(status='Pending').order_by(Parcel.created_at.asc()).all()
        available_drivers = Driver.query.filter_by(availability='Available').all()
        
    result = multi_courier_optimization(available_drivers, pending_parcels)
    return jsonify(result)

@app.route('/admin/execute-multi-dispatch', methods=['POST'])
@login_required
def execute_multi_dispatch():
    if current_user.role not in ['admin', 'hub_admin', 'dispatcher']:
        return redirect(url_for('index'))
        
    hub_name = get_current_hub_name()
    if hub_name:
        pending_parcels = Parcel.query.filter_by(status='Pending').filter(
            (Parcel.pickup_hub == hub_name) | (Parcel.delivery_hub == hub_name)
        ).order_by(Parcel.created_at.asc()).all()
        available_drivers = Driver.query.filter(
            Driver.availability == 'Available'
        ).all()
        hub_drivers = [d for d in available_drivers if d.hub and d.hub.name == hub_name]
        if hub_drivers:
            available_drivers = hub_drivers
    else:
        pending_parcels = Parcel.query.filter_by(status='Pending').order_by(Parcel.created_at.asc()).all()
        available_drivers = Driver.query.filter_by(availability='Available').all()
        
    if not pending_parcels:
        flash("No pending parcels available to dispatch.", "info")
        return redirect(url_for('delivery_optimization'))
        
    if not available_drivers:
        flash("No available couriers in service.", "warning")
        return redirect(url_for('delivery_optimization'))
        
    # Run optimization
    optimization_result = multi_courier_optimization(available_drivers, pending_parcels)
    
    total_assigned_parcels = 0
    couriers_dispatched = 0
    
    for route in optimization_result['courier_routes']:
        driver = Driver.query.get(route['courier_id'])
        if not driver:
            continue
            
        driver.availability = 'On Delivery'
        driver.status = 'On Delivery'
        couriers_dispatched += 1
        
        for stop in route['ordered_stops']:
            parcel = Parcel.query.get(stop['parcel_id'])
            if parcel and parcel.status == 'Pending':
                parcel.assigned_driver_id = driver.id
                parcel.status = 'Assigned'
                
                # History & Notification logs
                hist = TrackingHistory(
                    parcel_id=parcel.id,
                    status='Assigned',
                    location=f"Assigned to {driver.name} (Stop #{stop['stop_number']} of {route['total_stops']})"
                )
                notif = NotificationLog(
                    parcel_id=parcel.id,
                    message=f"TSP Optimized: Dispatched to courier {driver.name} (Stop #{stop['stop_number']}).",
                    type='Assigned'
                )
                db.session.add(hist)
                db.session.add(notif)
                total_assigned_parcels += 1
                
        # Record Vehicle Assignment if driver has assigned vehicle
        if driver.assigned_vehicle_id:
            asg = Assignment(
                driver_id=driver.id,
                vehicle_id=driver.assigned_vehicle_id,
                assignment_status='Active',
                hub_id=driver.hub_id
            )
            db.session.add(asg)
            
    db.session.commit()
    
    unassigned_count = optimization_result['summary']['unassigned_count']
    msg = f"Multi-Courier Optimization Complete! Dispatched {total_assigned_parcels} deliveries across {couriers_dispatched} couriers."
    if unassigned_count > 0:
        msg += f" {unassigned_count} deliveries remain unassigned due to fleet capacity limits."
        flash(msg, "warning")
    else:
        flash(msg, "success")
        
    return redirect(url_for('delivery_optimization'))

@app.route('/admin/drivers')
@login_required
def manage_drivers():
    if current_user.role not in ['admin', 'hub_admin', 'dispatcher']:
        return redirect(url_for('index'))
        
    drivers = Driver.query.all()
    hubs = Hub.query.all()
    vehicles = Vehicle.query.all()
    return render_template('drivers.html', active_page='drivers', drivers=drivers, hubs=hubs, vehicles=vehicles)

@app.route('/admin/update-driver-state/<int:id>', methods=['POST'])
@login_required
def update_driver_state_admin(id):
    if current_user.role not in ['admin', 'hub_admin']:
        return redirect(url_for('index'))
        
    driver = Driver.query.get_or_404(id)
    state = request.form.get('state')
    if state:
        driver.availability = state
        driver.status = state
        db.session.commit()
        flash(f"Driver {driver.name} state updated to: {state}", "success")
    return redirect(url_for('manage_drivers'))

@app.route('/admin/add-driver', methods=['POST'])
@login_required
def add_driver():
    if current_user.role not in ['admin', 'hub_admin']:
        return redirect(url_for('index'))
        
    name = request.form.get('name', '').strip()
    phone = request.form.get('phone', '').strip()
    email = request.form.get('email', '').strip()
    vehicle_number = request.form.get('vehicle_number', '').strip()
    availability = request.form.get('availability', 'Available')
    employee_code = request.form.get('employee_code', '').strip()
    license_number = request.form.get('license_number', '').strip()
    license_type = request.form.get('license_type', 'Bike').strip()
    assigned_vehicle_id = request.form.get('assigned_vehicle_id')
    hub_id = request.form.get('hub_id')
    
    assigned_veh_id = None
    veh_number = None
    
    if assigned_vehicle_id and assigned_vehicle_id != 'manual':
        assigned_veh_id = int(assigned_vehicle_id)
        selected_vehicle = Vehicle.query.get(assigned_veh_id)
        if selected_vehicle:
            # Check license compatibility: Bike license -> Bike, Van license -> Van, etc.
            temp_driver = Driver(license_type=license_type)
            if not temp_driver.can_drive_vehicle(selected_vehicle):
                flash(f"License Constraint Violation: A driver with a '{license_type}' license cannot be assigned to a {selected_vehicle.vehicle_type} ({selected_vehicle.vehicle_code}). Bike license holders can only drive Bikes, and Van license holders can only drive Vans.", "error")
                return redirect(url_for('manage_drivers'))
            veh_number = selected_vehicle.license_plate
            
    if not veh_number:
        # Fall back to manual plate entry
        veh_number = vehicle_number
        
    if not name or not phone or not employee_code or not license_number or not veh_number:
        flash("Validation Error: Driver Name, Phone, Driver ID (Employee Code), License Number, and Vehicle selection/plate details are compulsory.", "error")
        return redirect(url_for('manage_drivers'))
        
    if not validate_phone(phone):
        flash("Validation Error: Invalid phone format.", "error")
        return redirect(url_for('manage_drivers'))
        
    # Prevent duplicates
    existing_phone = Driver.query.filter_by(phone=phone).first()
    if existing_phone:
        flash(f"Validation Error: Phone number '{phone}' is already registered to another driver.", "error")
        return redirect(url_for('manage_drivers'))
        
    if email:
        existing_email = Driver.query.filter_by(email=email).first()
        if existing_email:
            flash(f"Validation Error: Email address '{email}' is already registered to another driver.", "error")
            return redirect(url_for('manage_drivers'))
            
    existing_code = Driver.query.filter_by(employee_code=employee_code).first()
    if existing_code:
        flash(f"Validation Error: Driver ID (Employee Code) '{employee_code}' already exists.", "error")
        return redirect(url_for('manage_drivers'))
        
    existing_license = Driver.query.filter_by(license_number=license_number).first()
    if existing_license:
        flash(f"Validation Error: License Number '{license_number}' is already registered to another driver.", "error")
        return redirect(url_for('manage_drivers'))
        
    driver = Driver(
        user_id=None,
        name=name,
        phone=phone,
        email=email if email else None,
        vehicle_number=veh_number,
        assigned_vehicle_id=assigned_veh_id,
        availability=availability,
        status=availability,
        employee_code=employee_code,
        license_number=license_number,
        license_type=license_type,
        hub_id=int(hub_id) if hub_id else None,
        latitude=27.7172,
        longitude=85.3240
    )
    db.session.add(driver)
    db.session.commit()
    
    selected_vehicle = Vehicle.query.get(assigned_veh_id) if assigned_veh_id else None
    assigned_info = f" assigned to vehicle {selected_vehicle.vehicle_code} ({selected_vehicle.vehicle_type})" if selected_vehicle else " registered successfully"
    flash(f"Driver profile for {name} ({license_type} License){assigned_info}!", "success")
    return redirect(url_for('manage_drivers'))

@app.route('/admin/edit-driver/<int:id>', methods=['POST'])
@login_required
def edit_driver(id):
    if current_user.role not in ['admin', 'hub_admin']:
        return redirect(url_for('index'))
        
    driver = Driver.query.get_or_404(id)
    driver.name = request.form.get('name', '').strip()
    driver.phone = request.form.get('phone', '').strip()
    driver.email = request.form.get('email', '').strip() or None
    driver.vehicle_number = request.form.get('vehicle_number', '').strip()
    driver.availability = request.form.get('availability')
    driver.status = driver.availability
    driver.employee_code = request.form.get('employee_code', '').strip() or None
    driver.license_number = request.form.get('license_number', '').strip() or None
    driver.license_type = request.form.get('license_type', driver.license_type or 'Bike').strip()
    hub_id = request.form.get('hub_id')
    driver.hub_id = int(hub_id) if hub_id else None
    
    password = request.form.get('password')
    if password and driver.user:
        driver.user.password_hash = generate_password_hash(password)
        
    db.session.commit()
    flash(f"Driver {driver.name} ({driver.license_type} License) updated successfully!", "success")
    return redirect(url_for('manage_drivers'))

@app.route('/admin/delete-driver/<int:id>', methods=['POST'])
@login_required
def delete_driver(id):
    if current_user.role not in ['admin', 'hub_admin']:
        return redirect(url_for('index'))
        
    driver = Driver.query.get_or_404(id)
    name = driver.name
    if driver.user:
        db.session.delete(driver.user)
    db.session.delete(driver)
    db.session.commit()
    flash(f"Driver {name} deleted successfully!", "success")
    return redirect(url_for('manage_drivers'))

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
    
    # Prevent duplicate hubs
    existing = Hub.query.filter_by(name=name).first()
    if existing:
        flash(f"Validation Error: Hub '{name}' already exists.", "error")
        return redirect(url_for('manage_hubs'))
        
    try:
        latitude = float(request.form.get('latitude', 0.0))
        longitude = float(request.form.get('longitude', 0.0))
    except ValueError:
        flash("Validation Error: Invalid coordinates.", "error")
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
        flash("Validation Error: Name, Phone, and Hub selection are required.", "error")
        return redirect(url_for('manage_hubs'))
        
    # Prevent duplicates
    existing_phone = HubAdmin.query.filter_by(phone=phone).first()
    if existing_phone:
        flash(f"Validation Error: Phone number '{phone}' is already registered to another Hub Admin.", "error")
        return redirect(url_for('manage_hubs'))
        
    if email:
        existing_email = HubAdmin.query.filter_by(email=email).first()
        if existing_email:
            flash(f"Validation Error: Email address '{email}' is already registered to another Hub Admin.", "error")
            return redirect(url_for('manage_hubs'))
            
    if create_login:
        if not username or not password:
            flash("Validation Error: Username and Password are required to create login.", "error")
            return redirect(url_for('manage_hubs'))
            
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash(f"Validation Error: Username '{username}' is already taken.", "error")
            return redirect(url_for('manage_hubs'))
            
    user = None
    if create_login and username and password:
        user = User(
            username=username,
            password_hash=generate_password_hash(password),
            role='hub_admin',
            permissions='view,create,edit,assign,dispatch,reports'
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
    
    flash(f"Hub Admin profile for '{name}' created!", "success")
    return redirect(url_for('manage_hubs'))

@app.route('/admin/edit-hub/<int:id>', methods=['POST'])
@login_required
def edit_hub(id):
    if current_user.role != 'admin':
        return redirect(url_for('index'))
        
    hub = Hub.query.get_or_404(id)
    hub.name = request.form.get('name', '').strip()
    hub.latitude = float(request.form.get('latitude', 0.0))
    hub.longitude = float(request.form.get('longitude', 0.0))
    db.session.commit()
    flash(f"Hub '{hub.name}' updated!", "success")
    return redirect(url_for('manage_hubs'))

@app.route('/admin/edit-hub-admin/<int:id>', methods=['POST'])
@login_required
def edit_hub_admin(id):
    if current_user.role != 'admin':
        return redirect(url_for('index'))
        
    hub_admin = HubAdmin.query.get_or_404(id)
    hub_admin.name = request.form.get('name', '').strip()
    hub_admin.phone = request.form.get('phone', '').strip()
    hub_admin.email = request.form.get('email', '').strip() or None
    hub_admin.hub_id = int(request.form.get('hub_id'))
    db.session.commit()
    flash("Hub Admin updated!", "success")
    return redirect(url_for('manage_hubs'))

@app.route('/admin/delete-hub/<int:id>')
@login_required
def delete_hub(id):
    if current_user.role != 'admin':
        return redirect(url_for('index'))
        
    hub = Hub.query.get_or_404(id)
    db.session.delete(hub)
    db.session.commit()
    flash("Hub deleted.", "success")
    return redirect(url_for('manage_hubs'))

@app.route('/admin/delete-hub-admin/<int:id>')
@login_required
def delete_hub_admin(id):
    if current_user.role != 'admin':
        return redirect(url_for('index'))
        
    hub_admin = HubAdmin.query.get_or_404(id)
    if hub_admin.user:
        db.session.delete(hub_admin.user)
    db.session.delete(hub_admin)
    db.session.commit()
    flash("Hub Admin profile deleted.", "success")
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
            
        profile = HubAdmin.query.filter((HubAdmin.phone == identifier) | (HubAdmin.email == identifier)).first()
        if not profile:
            flash("The provided phone number or email is not registered.", "error")
            return redirect(url_for('hub_admin_register'))
            
        if profile.user_id is not None:
            flash("This profile already has a registered account.", "error")
            return redirect(url_for('hub_admin_register'))
            
        user = User(
            username=username,
            password_hash=generate_password_hash(password),
            role='hub_admin',
            permissions='view,create,edit,assign,dispatch,reports'
        )
        db.session.add(user)
        db.session.commit()
        
        profile.user_id = user.id
        db.session.commit()
        
        flash("Hub Admin account registered successfully! Please sign in.", "success")
        return redirect(url_for('login'))
        
    return render_template('hub_admin_register.html', no_layout=True)

@app.route('/admin/cancel-parcel/<int:id>')
@login_required
def cancel_parcel(id):
    if current_user.role not in ['admin', 'hub_admin']:
        return redirect(url_for('index'))
        
    parcel = Parcel.query.get_or_404(id)
    if parcel.status == 'Pending':
        parcel.status = 'Cancelled'
        hist = TrackingHistory(parcel_id=parcel.id, status='Cancelled', location=parcel.pickup_address)
        notif = NotificationLog(parcel_id=parcel.id, message="Order cancelled.", type='Failed')
        db.session.add(hist)
        db.session.add(notif)
        db.session.commit()
        flash(f"Parcel order {parcel.tracking_id} cancelled.", "success")
    else:
        flash("Only pending orders can be cancelled.", "error")
        
    return redirect(url_for('manage_parcels'))

@app.route('/admin/track/<string:tracking_id>')
@login_required
def live_tracking_view(tracking_id):
    parcel = Parcel.query.filter_by(tracking_id=tracking_id).first_or_404()
    return render_template('live_tracking.html', active_page='parcels', parcel=parcel)

# --- DRIVER ROUTES & HELPER FUNCTIONS ---

def get_driver_active_parcels(driver_id):
    """Retrieve all active (non-delivered, non-cancelled) parcels assigned directly or through active manifests."""
    direct = Parcel.query.filter_by(assigned_driver_id=driver_id).filter(
        Parcel.status.notin_(['Delivered', 'Cancelled'])
    ).all()
    
    manifest_p = Parcel.query.join(ManifestItem, ManifestItem.parcel_id == Parcel.id)\
        .join(Manifest, Manifest.id == ManifestItem.manifest_id)\
        .filter(Manifest.assigned_driver_id == driver_id)\
        .filter(Manifest.manifest_status != 'Completed')\
        .filter(Parcel.status.notin_(['Delivered', 'Cancelled'])).all()
        
    seen = {p.id: p for p in (direct + manifest_p)}
    res = list(seen.values())
    res.sort(key=lambda x: (0 if x.status == 'Assigned' else 1, x.id))
    return res

def get_driver_history_parcels(driver_id):
    """Retrieve all historical completed/cancelled parcels assigned directly or through manifests."""
    direct = Parcel.query.filter_by(assigned_driver_id=driver_id).filter(
        Parcel.status.in_(['Delivered', 'Cancelled'])
    ).all()
    
    manifest_p = Parcel.query.join(ManifestItem, ManifestItem.parcel_id == Parcel.id)\
        .join(Manifest, Manifest.id == ManifestItem.manifest_id)\
        .filter(Manifest.assigned_driver_id == driver_id)\
        .filter(Parcel.status.in_(['Delivered', 'Cancelled'])).all()
        
    seen = {p.id: p for p in (direct + manifest_p)}
    res = list(seen.values())
    res.sort(key=lambda x: (x.delivered_at or datetime.min), reverse=True)
    return res

@app.route('/driver/dashboard')
@login_required
def driver_dashboard():
    if current_user.role != 'driver':
        return redirect(url_for('index'))
        
    driver = Driver.query.filter_by(user_id=current_user.id).first_or_404()
    active_deliveries = get_driver_active_parcels(driver.id)
    history_deliveries = get_driver_history_parcels(driver.id)
    
    # Query Assigned Inter-Hub / Freight Manifests
    assigned_manifests = Manifest.query.filter_by(assigned_driver_id=driver.id).order_by(Manifest.created_at.desc()).all()
    active_manifests = [m for m in assigned_manifests if m.manifest_status != 'Completed']
    completed_manifests = [m for m in assigned_manifests if m.manifest_status == 'Completed']
    
    pickups_count = len([p for p in active_deliveries if p.status == 'Assigned'])
    deliveries_count = len([p for p in active_deliveries if p.status != 'Assigned'])
    total_cod = sum([p.cod_amount or p.delivery_charge for p in active_deliveries])
    
    return render_template(
        'driver_dashboard.html', 
        active_page='driver_dashboard', 
        driver=driver, 
        active_deliveries=active_deliveries, 
        history_deliveries=history_deliveries,
        active_manifests=active_manifests,
        completed_manifests=completed_manifests,
        assigned_manifests=assigned_manifests,
        pickups_count=pickups_count,
        deliveries_count=deliveries_count,
        total_cod=total_cod
    )

@app.route('/driver/manifests')
@login_required
def driver_manifests():
    if current_user.role != 'driver':
        return redirect(url_for('index'))
        
    driver = Driver.query.filter_by(user_id=current_user.id).first_or_404()
    assigned_manifests = Manifest.query.filter_by(assigned_driver_id=driver.id).order_by(Manifest.created_at.desc()).all()
    active_manifests = [m for m in assigned_manifests if m.manifest_status != 'Completed']
    completed_manifests = [m for m in assigned_manifests if m.manifest_status == 'Completed']
    
    return render_template(
        'driver_manifests.html',
        active_page='driver_manifests',
        driver=driver,
        active_manifests=active_manifests,
        completed_manifests=completed_manifests,
        assigned_manifests=assigned_manifests
    )

@app.route('/driver/manifest/<int:id>/update-status', methods=['POST'])
@login_required
def update_manifest_status_driver(id):
    if current_user.role != 'driver':
        return redirect(url_for('index'))
        
    driver = Driver.query.filter_by(user_id=current_user.id).first_or_404()
    manifest = Manifest.query.filter_by(id=id, assigned_driver_id=driver.id).first_or_404()
    new_status = request.form.get('status', 'Completed')
    
    if new_status == 'In Transit':
        manifest.manifest_status = 'Dispatched'
        manifest.dispatch_date = datetime.now()
        for item in manifest.items:
            if item.parcel:
                item.parcel.status = 'In Transit'
                db.session.add(TrackingHistory(parcel_id=item.parcel.id, status='In Transit', location=f"In Transit with Courier {driver.name} on Manifest {manifest.manifest_number}"))
        driver.availability = 'On Delivery'
        if manifest.assigned_vehicle:
            manifest.assigned_vehicle.current_status = 'Delivering'
        db.session.commit()
        flash(f"Manifest {manifest.manifest_number} marked as In Transit! Cargo batch underway.", "success")
        
    elif new_status == 'Completed':
        manifest.manifest_status = 'Completed'
        manifest.arrival_date = datetime.now()
        for item in manifest.items:
            if item.parcel:
                item.parcel.status = 'Delivered'
                item.parcel.delivered_at = datetime.now()
                db.session.add(TrackingHistory(parcel_id=item.parcel.id, status='Delivered', location=f"Delivered at {manifest.destination_hub.name if manifest.destination_hub else 'Destination'} Hub via Manifest {manifest.manifest_number}"))
            
        driver.availability = 'Available'
        driver.completed_deliveries = (driver.completed_deliveries or 0) + len(manifest.items)
        if manifest.assigned_vehicle:
            manifest.assigned_vehicle.current_status = 'Available'
            
        active_asgn = Assignment.query.filter_by(manifest_id=manifest.id, assignment_status='Active').first()
        if active_asgn:
            active_asgn.assignment_status = 'Returned'
            active_asgn.actual_return = datetime.now()
            
        db.session.commit()
        flash(f"Manifest {manifest.manifest_number} marked as Completed & Delivered to destination hub!", "success")
        
    return redirect(url_for('driver_manifests'))

@app.route('/driver/manifest/<int:manifest_id>/deliver-parcel/<int:parcel_id>', methods=['POST'])
@login_required
def driver_deliver_manifest_parcel(manifest_id, parcel_id):
    if current_user.role != 'driver':
        return redirect(url_for('index'))
        
    driver = Driver.query.filter_by(user_id=current_user.id).first_or_404()
    manifest = Manifest.query.filter_by(id=manifest_id, assigned_driver_id=driver.id).first_or_404()
    item = ManifestItem.query.filter_by(manifest_id=manifest.id, parcel_id=parcel_id).first_or_404()
    parcel = item.parcel
    
    notes = request.form.get('notes', '').strip()
    
    parcel.status = 'Delivered'
    parcel.delivered_at = datetime.now()
    
    loc = f"Direct Home Delivery Completed to {parcel.receiver_name} at {parcel.delivery_address} by Driver {driver.name} (Manifest {manifest.manifest_number})"
    if notes:
        loc += f" [Notes: {notes}]"
    db.session.add(TrackingHistory(parcel_id=parcel.id, status='Delivered', location=loc))
    
    driver.completed_deliveries = (driver.completed_deliveries or 0) + 1
    
    # Check if all parcels are delivered
    all_delivered = all(i.parcel.status == 'Delivered' for i in manifest.items if i.parcel)
    if all_delivered:
        manifest.manifest_status = 'Completed'
        manifest.arrival_date = datetime.now()
        driver.availability = 'Available'
        if manifest.assigned_vehicle:
            manifest.assigned_vehicle.current_status = 'Available'
        active_asgn = Assignment.query.filter_by(manifest_id=manifest.id, assignment_status='Active').first()
        if active_asgn:
            active_asgn.assignment_status = 'Returned'
            active_asgn.actual_return = datetime.now()
        db.session.commit()
        flash(f"Home delivery completed for #{parcel.tracking_id}! All parcels on Manifest {manifest.manifest_number} have been delivered.", "success")
    else:
        if manifest.manifest_status in ['Draft', 'Created']:
            manifest.manifest_status = 'Dispatched'
            manifest.dispatch_date = datetime.now()
        driver.availability = 'On Delivery'
        if manifest.assigned_vehicle:
            manifest.assigned_vehicle.current_status = 'Delivering'
        db.session.commit()
        remaining = manifest.pending_items_count
        flash(f"Parcel #{parcel.tracking_id} successfully delivered! {remaining} stop(s) remaining.", "success")
        
    return redirect(url_for('driver_manifests'))

@app.route('/driver/pickups')
@login_required
def driver_pickups():
    if current_user.role != 'driver':
        return redirect(url_for('index'))
        
    driver = Driver.query.filter_by(user_id=current_user.id).first_or_404()
    pickups = [p for p in get_driver_active_parcels(driver.id) if p.status == 'Assigned']
    
    return render_template(
        'driver_pickups.html',
        active_page='driver_pickups',
        driver=driver,
        pickups=pickups
    )

@app.route('/driver/tasks')
@login_required
def driver_tasks():
    if current_user.role != 'driver':
        return redirect(url_for('index'))
        
    driver = Driver.query.filter_by(user_id=current_user.id).first_or_404()
    tasks = get_driver_active_parcels(driver.id)
    active_manifests = Manifest.query.filter_by(assigned_driver_id=driver.id).filter(Manifest.manifest_status != 'Completed').order_by(Manifest.created_at.desc()).all()
    
    return render_template(
        'driver_tasks.html',
        active_page='driver_tasks',
        driver=driver,
        tasks=tasks,
        active_manifests=active_manifests
    )

@app.route('/driver/route-planner')
@login_required
def driver_route_planner():
    if current_user.role != 'driver':
        return redirect(url_for('index'))
        
    driver = Driver.query.filter_by(user_id=current_user.id).first_or_404()
    active_deliveries = get_driver_active_parcels(driver.id)
    
    return render_template(
        'driver_route_planner.html',
        active_page='driver_route_planner',
        driver=driver,
        active_deliveries=active_deliveries
    )

@app.route('/driver/history')
@login_required
def driver_history():
    if current_user.role != 'driver':
        return redirect(url_for('index'))
        
    driver = Driver.query.filter_by(user_id=current_user.id).first_or_404()
    history_deliveries = get_driver_history_parcels(driver.id)
    completed_manifests = Manifest.query.filter_by(assigned_driver_id=driver.id, manifest_status='Completed').order_by(Manifest.arrival_date.desc()).all()
    
    return render_template(
        'driver_history.html',
        active_page='driver_history',
        driver=driver,
        history_deliveries=history_deliveries,
        completed_manifests=completed_manifests
    )

@app.route('/driver/account')
@login_required
def driver_account():
    if current_user.role != 'driver':
        return redirect(url_for('index'))
        
    driver = Driver.query.filter_by(user_id=current_user.id).first_or_404()
    recent_delivered = [p for p in get_driver_history_parcels(driver.id) if p.status == 'Delivered'][:15]
    
    cod_in_hand = sum([p.delivery_charge for p in recent_delivered])
    estimated_earnings = driver.completed_deliveries * 35.0  # Commission per delivery
    
    return render_template(
        'driver_account.html',
        active_page='driver_account',
        driver=driver,
        recent_delivered=recent_delivered,
        cod_in_hand=cod_in_hand,
        estimated_earnings=estimated_earnings
    )

@app.route('/driver/profile', methods=['GET', 'POST'])
@login_required
def driver_profile():
    if current_user.role != 'driver':
        return redirect(url_for('index'))
        
    driver = Driver.query.filter_by(user_id=current_user.id).first_or_404()
    
    if request.method == 'POST':
        driver.name = request.form.get('name', driver.name)
        driver.phone = request.form.get('phone', driver.phone)
        driver.email = request.form.get('email', driver.email)
        db.session.commit()
        flash("Rider profile details updated successfully!", "success")
        return redirect(url_for('driver_profile'))
        
    return render_template(
        'driver_profile.html',
        active_page='driver_profile',
        driver=driver
    )

@app.route('/driver/update-status/<int:id>', methods=['POST'])
@login_required
def update_parcel_status_driver(id):
    if current_user.role != 'driver':
        return redirect(url_for('index'))
        
    parcel = Parcel.query.get_or_404(id)
    driver = Driver.query.filter_by(user_id=current_user.id).first_or_404()
    status = request.form.get('status')
    
    if not parcel.assigned_driver_id:
        parcel.assigned_driver_id = driver.id
        
    if status == 'Picked Up':
        file = request.files.get('pickup_image')
        if file:
            filename = secure_filename(f"pickup_{parcel.tracking_id}_{file.filename}")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            parcel.pickup_image = filename
            
        parcel.status = 'Picked Up'
        db.session.add(TrackingHistory(parcel_id=parcel.id, status='Picked Up', location=parcel.pickup_address))
        db.session.add(NotificationLog(parcel_id=parcel.id, message="Package picked up by driver.", type='Picked Up'))
        
    elif status == 'In Transit':
        parcel.status = 'In Transit'
        db.session.add(TrackingHistory(parcel_id=parcel.id, status='In Transit', location=parcel.pickup_address))
        db.session.add(NotificationLog(parcel_id=parcel.id, message="Shipment in transit.", type='In Transit'))
        
    elif status == 'Out For Delivery':
        parcel.status = 'Out For Delivery'
        db.session.add(TrackingHistory(parcel_id=parcel.id, status='Out For Delivery', location=parcel.delivery_address))
        db.session.add(NotificationLog(parcel_id=parcel.id, message="Out for delivery.", type='Out For Delivery'))
        
    elif status == 'Delivered':
        file = request.files.get('delivery_image')
        if file:
            filename = secure_filename(f"delivery_{parcel.tracking_id}_{file.filename}")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            parcel.delivery_image = filename
            
        parcel.delivery_notes = request.form.get('delivery_notes')
        parcel.customer_signature = request.form.get('customer_signature')
        parcel.delivered_at = datetime.utcnow()
        parcel.status = 'Delivered'
        parcel.payment_status = 'Paid'
        
        driver.completed_deliveries = (driver.completed_deliveries or 0) + 1
        
        db.session.add(TrackingHistory(parcel_id=parcel.id, status='Delivered', location=f"Delivered to {parcel.receiver_name} at {parcel.delivery_address} by Driver {driver.name}"))
        db.session.add(NotificationLog(parcel_id=parcel.id, message="Shipment delivered successfully.", type='Delivered'))
        
        # If part of a manifest, check if all items are now delivered
        if parcel.manifest:
            all_del = all(i.parcel.status == 'Delivered' for i in parcel.manifest.items if i.parcel)
            if all_del:
                parcel.manifest.manifest_status = 'Completed'
                parcel.manifest.arrival_date = datetime.utcnow()
                driver.availability = 'Available'
                if parcel.manifest.assigned_vehicle:
                    parcel.manifest.assigned_vehicle.current_status = 'Available'
                active_asgn = Assignment.query.filter_by(manifest_id=parcel.manifest.id, assignment_status='Active').first()
                if active_asgn:
                    active_asgn.assignment_status = 'Returned'
                    active_asgn.actual_return = datetime.utcnow()
        else:
            driver.availability = 'Available'
            
    elif status == 'Failed Attempt':
        failed_reason = request.form.get('failed_reason')
        parcel.delivery_attempts = (parcel.delivery_attempts or 0) + 1
        parcel.failed_reason = failed_reason
        parcel.status = 'Assigned'
        
        db.session.add(TrackingHistory(parcel_id=parcel.id, status='Failed Attempt', location=parcel.delivery_address))
        db.session.add(NotificationLog(parcel_id=parcel.id, message=f"Delivery attempt failed. Reason: {failed_reason}.", type='Failed'))
        
    db.session.commit()
    flash(f"Shipment {parcel.tracking_id} updated to {status}!", "success")
    return redirect(request.referrer or url_for('driver_dashboard'))

# --- PUBLIC & PRINT HELPER ROUTES ---

@app.route('/track')
def customer_tracking_view():
    tracking_id = request.args.get('tracking_id')
    parcel = None
    manifest = None
    error = False
    if tracking_id:
        tid = tracking_id.strip()
        parcel = Parcel.query.filter_by(tracking_id=tid).first()
        if not parcel:
            manifest = Manifest.query.filter_by(manifest_number=tid).first()
            if not manifest:
                error = True
    return render_template('customer_tracking.html', tracking_id=tracking_id, parcel=parcel, manifest=manifest, error=error, no_layout=True)

@app.route('/parcel/<int:id>/label')
@login_required
def print_shipping_label(id):
    parcel = Parcel.query.get_or_404(id)
    return render_template('shipping_label.html', parcel=parcel, no_layout=True)

@app.route('/api/barcode/<tracking_id>')
def generate_barcode_api(tracking_id):
    try:
        code128 = barcode.get('code128', tracking_id, writer=ImageWriter())
        buffer = BytesIO()
        code128.write(buffer, options={'write_text': False, 'quiet_zone': 1})
        buffer.seek(0)
        return send_file(buffer, mimetype='image/png')
    except Exception:
        from barcode.writer import SVGWriter
        code128 = barcode.get('code128', tracking_id, writer=SVGWriter())
        buffer = BytesIO()
        code128.write(buffer, options={'write_text': False, 'quiet_zone': 1})
        buffer.seek(0)
        return send_file(buffer, mimetype='image/svg+xml')

@app.route('/api/qrcode/<tracking_id>')
def generate_qrcode_api(tracking_id):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=6,
        border=1,
    )
    qr.add_data(tracking_id)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    return send_file(buffer, mimetype='image/png')

@app.route('/parcel/<int:id>/proof')
def view_proof_of_delivery(id):
    parcel = Parcel.query.get_or_404(id)
    return render_template('proof_of_delivery.html', parcel=parcel, no_layout=True)

@app.route('/static/uploads/<filename>')
def uploaded_file(filename):
    return send_file(os.path.join(app.config['UPLOAD_FOLDER'], filename))

# --- REAL-TIME TELEMETRY APIs ---

@app.route('/api/admin/analytics')
@login_required
def api_admin_analytics():
    if current_user.role not in ['admin', 'hub_admin', 'dispatcher']:
        return jsonify({'error': 'Unauthorized'}), 401
        
    hub_name = get_current_hub_name()
    if hub_name:
        parcels = Parcel.query.filter((Parcel.pickup_hub == hub_name) | (Parcel.delivery_hub == hub_name)).all()
    else:
        parcels = Parcel.query.all()
        
    status_counts = {}
    for p in parcels:
        status_counts[p.status] = status_counts.get(p.status, 0) + 1
        
    hub_dist = {}
    for p in parcels:
        hub_dist[p.pickup_hub] = hub_dist.get(p.pickup_hub, 0) + 1
        
    drivers = Driver.query.all()
    driver_stats = [{
        'name': d.name,
        'completed': d.completed_deliveries,
        'status': d.availability
    } for d in drivers]
    
    return jsonify({
        'status_counts': status_counts,
        'hub_distribution': hub_dist,
        'driver_stats': driver_stats
    })

@app.route('/api/admin/drivers-location')
def api_drivers_location():
    drivers = Driver.query.all()
    data = [{
        'id': d.id,
        'name': d.name,
        'vehicle': d.vehicle_number,
        'availability': d.availability,
        'latitude': d.latitude,
        'longitude': d.longitude,
        'phone': d.phone
    } for d in drivers]
    return jsonify(data)

@app.route('/api/parcel/<tracking_id>/route')
def api_parcel_route(tracking_id):
    parcel = Parcel.query.filter_by(tracking_id=tracking_id).first_or_404()
    
    driver = parcel.assigned_driver or (parcel.manifest.assigned_driver if parcel.manifest else None)
    vehicle = (driver.assigned_vehicle if driver and driver.assigned_vehicle else None) or (parcel.manifest.assigned_vehicle if parcel.manifest else None)
    
    driver_coords = None
    if driver and driver.latitude and driver.longitude:
        driver_coords = {'lat': driver.latitude, 'lng': driver.longitude}
        
    hubs_dict = get_all_hubs_dict()
    pickup_hub = hubs_dict.get(parcel.pickup_hub)
    delivery_hub = hubs_dict.get(parcel.delivery_hub)
    
    if not pickup_hub or not delivery_hub:
        return jsonify({'error': 'Invalid hubs'}), 400

    routing_from_driver = False
    if driver_coords and parcel.status in ['Assigned', 'Picked Up', 'In Transit', 'Out For Delivery']:
        routing_from_driver = True
        start_lat = driver_coords['lat']
        start_lng = driver_coords['lng']
        start_name = 'Driver Location'
        
        if parcel.status == 'Assigned':
            end_lat, end_lng, end_name = pickup_hub['lat'], pickup_hub['lng'], f"{parcel.pickup_hub} Hub"
        elif parcel.status in ['Picked Up', 'In Transit']:
            end_lat, end_lng, end_name = delivery_hub['lat'], delivery_hub['lng'], f"{parcel.delivery_hub} Hub"
        else:
            end_lat, end_lng, end_name = parcel.delivery_latitude, parcel.delivery_longitude, 'Home Delivery'
    else:
        start_lat, start_lng, start_name = pickup_hub['lat'], pickup_hub['lng'], f"{parcel.pickup_hub} Hub"
        end_lat, end_lng, end_name = parcel.delivery_latitude, parcel.delivery_longitude, 'Home Delivery'
        
    driver_data = None
    if driver:
        driver_data = {
            'name': driver.name,
            'vehicle': vehicle.vehicle_code if vehicle else driver.vehicle_number,
            'vehicle_plate': vehicle.license_plate if vehicle else driver.vehicle_number,
            'vehicle_type': vehicle.vehicle_type if vehicle else 'Bike',
            'lat': driver.latitude,
            'lng': driver.longitude
        }

    routes = fetch_osrm_routes_with_alternatives(start_lat, start_lng, end_lat, end_lng)
    recommended_route_pts = routes[0]['coordinates'] if routes else []

    if routing_from_driver:
        segments = [{
            'from': start_name,
            'to': end_name,
            'coordinates': recommended_route_pts,
            'traffic': 'Moderate',
            'condition': 'Active courier delivery routing',
            'color': '#2563EB',
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
        
    path, distance = dijkstra(parcel.pickup_hub, parcel.delivery_hub)
    hub_coords = get_route_coordinates(path)
    path_coords = list(hub_coords)
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
    dest_lat = parcel.delivery_latitude
    dest_lng = parcel.delivery_longitude
    
    distance_remaining_km = 0.0
    eta_minutes = 0
    speed_kmh = 0.0
    progress_percent = 0.0
    
    pickup_hub_name = get_closest_hub(parcel.pickup_latitude, parcel.pickup_longitude)
    delivery_hub_name = get_closest_hub(parcel.delivery_latitude, parcel.delivery_longitude)
    
    driver = parcel.assigned_driver or (parcel.manifest.assigned_driver if parcel.manifest else None)
    
    if parcel.status == 'Delivered':
        progress_percent = 100.0
    elif parcel.status == 'Cancelled':
        progress_percent = 0.0
    elif driver:
        distance_remaining_km = haversine_distance(driver.latitude, driver.longitude, dest_lat, dest_lng)
        path, total_dist = dijkstra(pickup_hub_name, delivery_hub_name)
        hubs_dict = get_all_hubs_dict()
        pickup_hub_coords = hubs_dict.get(pickup_hub_name)
        delivery_hub_coords = hubs_dict.get(delivery_hub_name)
        
        dist_pickup_to_hub = haversine_distance(parcel.pickup_latitude, parcel.pickup_longitude, pickup_hub_coords['lat'], pickup_hub_coords['lng'])
        dist_hub_to_delivery = haversine_distance(delivery_hub_coords['lat'], delivery_hub_coords['lng'], parcel.delivery_latitude, parcel.delivery_longitude)
        total_dist_home_to_home = dist_pickup_to_hub + total_dist + dist_hub_to_delivery
        
        if parcel.status == 'Assigned':
            progress_percent = 10.0
            eta_minutes = int((total_dist_home_to_home / 25.0) * 60) + 10
        elif parcel.status == 'Picked Up':
            progress_percent = 20.0
            eta_minutes = int((total_dist_home_to_home / 25.0) * 60)
        elif parcel.status in ['In Transit', 'Manifested']:
            progress_percent = 45.0
            speed_kmh = 32.0
            eta_minutes = int((distance_remaining_km / 25.0) * 60)
        elif parcel.status == 'Out For Delivery':
            progress_percent = 85.0
            speed_kmh = 18.0
            eta_minutes = int((distance_remaining_km / 15.0) * 60)
            
        if eta_minutes < 1 and parcel.status != 'Delivered':
            eta_minutes = 3
    else:
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
        
    notifications = [{
        'message': log.message,
        'type': log.type,
        'timestamp': log.timestamp.isoformat()
    } for log in parcel.notifications]
        
    return jsonify({
        'tracking_id': parcel.tracking_id,
        'status': parcel.status,
        'progress_percent': progress_percent,
        'distance_remaining_km': distance_remaining_km,
        'eta_minutes': eta_minutes,
        'speed_kmh': speed_kmh,
        'driver_latitude': driver.latitude if driver else None,
        'driver_longitude': driver.longitude if driver else None,
        'notifications': notifications
    })

# --- MANIFEST / GROUP SHIPMENT TELEMETRY APIs ---

@app.route('/api/manifest/<int:id>/route')
def api_manifest_route(id):
    manifest = Manifest.query.get_or_404(id)
    origin_hub = manifest.origin_hub
    dest_hub = manifest.destination_hub
    
    if not origin_hub or not dest_hub:
        return jsonify({'error': 'Invalid hubs'}), 400
        
    driver = manifest.assigned_driver
    vehicle = manifest.assigned_vehicle
    
    driver_data = None
    if driver:
        driver_data = {
            'name': driver.name,
            'vehicle': vehicle.vehicle_code if vehicle else driver.vehicle_number,
            'vehicle_plate': vehicle.license_plate if vehicle else driver.vehicle_number,
            'vehicle_type': vehicle.vehicle_type if vehicle else 'Truck',
            'lat': driver.latitude,
            'lng': driver.longitude
        }
        
    # Get OSRM road route between origin hub and destination hub
    start_lat, start_lng = origin_hub.latitude, origin_hub.longitude
    end_lat, end_lng = dest_hub.latitude, dest_hub.longitude
    
    routes = fetch_osrm_routes_with_alternatives(start_lat, start_lng, end_lat, end_lng)
    recommended_route_pts = routes[0]['coordinates'] if routes else []
    
    segments = [{
        'from': f"{origin_hub.name} Hub",
        'to': f"{dest_hub.name} Hub",
        'coordinates': recommended_route_pts,
        'traffic': 'Moderate',
        'condition': 'Inter-hub freight transit route',
        'color': '#2563EB',
        'speed_limit': 60
    }]
    
    return jsonify({
        'manifest_number': manifest.manifest_number,
        'origin': {'name': f"{origin_hub.name} Hub", 'lat': origin_hub.latitude, 'lng': origin_hub.longitude},
        'destination': {'name': f"{dest_hub.name} Hub", 'lat': dest_hub.latitude, 'lng': dest_hub.longitude},
        'status': manifest.manifest_status,
        'path': recommended_route_pts,
        'segments': segments,
        'driver': driver_data,
        'total_parcels': manifest.total_parcels,
        'total_weight': manifest.total_weight
    })

@app.route('/api/manifest/<int:id>/telemetry')
def api_manifest_telemetry(id):
    manifest = Manifest.query.get_or_404(id)
    origin_hub = manifest.origin_hub
    dest_hub = manifest.destination_hub
    
    distance_remaining_km = 0.0
    eta_minutes = 0
    speed_kmh = 0.0
    progress_percent = 0.0
    
    total_dist = haversine_distance(origin_hub.latitude, origin_hub.longitude, dest_hub.latitude, dest_hub.longitude) if origin_hub and dest_hub else 10.0
    
    if manifest.manifest_status == 'Completed':
        progress_percent = 100.0
        speed_kmh = 0.0
        distance_remaining_km = 0.0
        eta_minutes = 0
    elif manifest.manifest_status == 'Dispatched':
        progress_percent = 50.0
        speed_kmh = 42.0
        if manifest.assigned_driver and dest_hub:
            driver = manifest.assigned_driver
            distance_remaining_km = haversine_distance(driver.latitude, driver.longitude, dest_hub.latitude, dest_hub.longitude)
            eta_minutes = max(2, int((distance_remaining_km / 40.0) * 60))
            if total_dist > 0:
                progress_percent = min(95.0, max(10.0, ((total_dist - distance_remaining_km) / total_dist) * 100.0))
        else:
            distance_remaining_km = total_dist
            eta_minutes = max(5, int((total_dist / 40.0) * 60))
    else: # Draft or Created
        progress_percent = 0.0
        distance_remaining_km = total_dist
        eta_minutes = int((total_dist / 40.0) * 60) + 10
        
    return jsonify({
        'manifest_number': manifest.manifest_number,
        'status': manifest.manifest_status,
        'progress_percent': round(progress_percent, 1),
        'distance_remaining_km': round(distance_remaining_km, 2),
        'eta_minutes': eta_minutes,
        'speed_kmh': speed_kmh,
        'driver_latitude': manifest.assigned_driver.latitude if manifest.assigned_driver else None,
        'driver_longitude': manifest.assigned_driver.longitude if manifest.assigned_driver else None
    })

# --- DRIVER GPS & ROUTING APIs ---

@app.route('/api/driver/update-location', methods=['POST'])
@app.route('/api/driver/location', methods=['POST'])
@login_required
def api_driver_update_location():
    if current_user.role != 'driver':
        return jsonify({'error': 'Unauthorized'}), 401
        
    driver = Driver.query.filter_by(user_id=current_user.id).first_or_404()
    data = request.get_json() or {}
    
    lat = data.get('latitude')
    lng = data.get('longitude')
    availability = data.get('availability') or data.get('state')
    
    updated = False
    if lat is not None and lng is not None:
        try:
            lat = float(lat)
            lng = float(lng)
            if not (lat == 0.0 and lng == 0.0):
                driver.latitude = lat
                driver.longitude = lng
                updated = True
        except (TypeError, ValueError):
            pass
            
    if availability in ['Available', 'On Delivery', 'On Break', 'Offline']:
        driver.availability = availability
        driver.status = availability
        updated = True
        
    if updated:
        db.session.commit()
    
    return jsonify({
        'success': True,
        'driver_id': driver.id,
        'name': driver.name,
        'latitude': driver.latitude,
        'longitude': driver.longitude,
        'availability': driver.availability,
        'updated_at': datetime.utcnow().isoformat()
    })

@app.route('/api/driver/update-state', methods=['POST'])
@login_required
def api_driver_update_state():
    if current_user.role != 'driver':
        return jsonify({'error': 'Unauthorized'}), 401
        
    driver = Driver.query.filter_by(user_id=current_user.id).first_or_404()
    data = request.get_json() or {}
    state = data.get('state')
    
    if state in ['Available', 'On Delivery', 'On Break', 'Offline']:
        driver.availability = state
        driver.status = state
        db.session.commit()
        return jsonify({'success': True, 'state': state})
        
    return jsonify({'error': 'Invalid state'}), 400

@app.route('/api/driver/active-route')
@login_required
def api_driver_active_route():
    if current_user.role != 'driver':
        return jsonify({'error': 'Unauthorized'}), 401
        
    driver = Driver.query.filter_by(user_id=current_user.id).first_or_404()
    vehicle = driver.assigned_vehicle
    
    driver_data = {
        'id': driver.id,
        'name': driver.name,
        'phone': driver.phone,
        'lat': driver.latitude,
        'lng': driver.longitude,
        'vehicle': vehicle.vehicle_code if vehicle else driver.vehicle_number,
        'vehicle_plate': vehicle.license_plate if vehicle else driver.vehicle_number,
        'vehicle_type': vehicle.vehicle_type if vehicle else 'Bike',
        'availability': driver.availability
    }
    
    # 1. Fetch all active parcels assigned to driver (directly or grouped in active manifests)
    active_parcels = get_driver_active_parcels(driver.id)
    
    if not active_parcels:
        # Check if driver has a bare manifest with no parcels attached yet
        dispatched_manifest = Manifest.query.filter_by(assigned_driver_id=driver.id).filter(Manifest.manifest_status != 'Completed').first()
        if dispatched_manifest and dispatched_manifest.destination_hub:
            routes = fetch_osrm_routes_with_alternatives(
                driver_data['lat'], driver_data['lng'],
                dispatched_manifest.destination_hub.latitude, dispatched_manifest.destination_hub.longitude
            )
            rec_route = routes[0] if routes else {
                'coordinates': [{'lat': driver_data['lat'], 'lng': driver_data['lng']}, {'lat': dispatched_manifest.destination_hub.latitude, 'lng': dispatched_manifest.destination_hub.longitude}],
                'distance_km': haversine_distance(driver_data['lat'], driver_data['lng'], dispatched_manifest.destination_hub.latitude, dispatched_manifest.destination_hub.longitude),
                'duration_min': 15.0
            }
            return jsonify({
                'type': 'manifest',
                'driver': driver_data,
                'manifest_number': dispatched_manifest.manifest_number,
                'manifest_type': dispatched_manifest.manifest_type,
                'origin': {'name': f"{dispatched_manifest.origin_hub.name if dispatched_manifest.origin_hub else 'Origin'} Hub", 'lat': dispatched_manifest.origin_hub.latitude if dispatched_manifest.origin_hub else driver_data['lat'], 'lng': dispatched_manifest.origin_hub.longitude if dispatched_manifest.origin_hub else driver_data['lng']},
                'destination': {'name': f"{dispatched_manifest.destination_hub.name} Hub", 'lat': dispatched_manifest.destination_hub.latitude, 'lng': dispatched_manifest.destination_hub.longitude},
                'coordinates': rec_route['coordinates'],
                'distance_km': rec_route.get('distance_km', 0.0),
                'duration_min': rec_route.get('duration_min', 0.0),
                'stops': [
                    {
                        'stop_number': 1,
                        'name': f"Destination: {dispatched_manifest.destination_hub.name} Hub",
                        'delivery_address': f"{dispatched_manifest.destination_hub.name} Hub, {dispatched_manifest.destination_hub.city or ''}",
                        'lat': dispatched_manifest.destination_hub.latitude,
                        'lng': dispatched_manifest.destination_hub.longitude,
                        'type': 'hub'
                    }
                ]
            })

        return jsonify({
            'type': 'idle',
            'driver': driver_data,
            'coordinates': [],
            'stops': [],
            'distance_km': 0.0,
            'duration_min': 0.0
        })

    # 2. Build stops for all active consignments (both direct deliveries and manifest stops)
    driver_start = {'lat': driver.latitude or 27.7000, 'lng': driver.longitude or 85.3200, 'name': f"My Location ({driver.name})"}
    stops_input = []
    for p in active_parcels:
        if p.status == 'Assigned':
            stop_lat = p.pickup_latitude or 27.7000
            stop_lng = p.pickup_longitude or 85.3200
            stop_addr = p.pickup_address or 'Sender Location'
            stop_action = 'Pick Up from Sender'
        else:
            stop_lat = p.delivery_latitude or 27.7100
            stop_lng = p.delivery_longitude or 85.3300
            stop_addr = p.delivery_address or 'Recipient Delivery Address'
            stop_action = 'Deliver to Doorstep' if (p.manifest and p.manifest.is_home_delivery) else 'Deliver to Recipient'
            
        stops_input.append({
            'parcel_id': p.id,
            'tracking_id': p.tracking_id,
            'receiver_name': p.receiver_name or 'Recipient',
            'receiver_phone': p.receiver_phone or '',
            'sender_name': p.sender_name or 'Sender',
            'sender_phone': p.sender_phone or '',
            'delivery_address': stop_addr,
            'pickup_address': p.pickup_address or '',
            'lat': stop_lat,
            'lng': stop_lng,
            'weight': p.weight or 1.0,
            'status': p.status,
            'action_type': stop_action,
            'payment_status': p.payment_status or 'Pending',
            'delivery_charge': p.delivery_charge or 0.0,
            'cod_amount': p.cod_amount or 0.0,
            'manifest_id': p.manifest_id,
            'manifest_number': p.manifest.manifest_number if p.manifest else None,
            'is_home_delivery': bool(p.manifest and p.manifest.is_home_delivery)
        })

    # Run TSP to sequence multiple stops optimally from driver's current GPS location
    ordered_stops, total_dist, legs = solve_tsp(driver_start, stops_input)
    
    # Generate continuous turn-by-turn road polyline through all stops
    full_route_pts = []
    for leg in legs:
        leg_pts = fetch_osrm_route(leg['from_lat'], leg['from_lng'], leg['to_lat'], leg['to_lng'])
        if full_route_pts and leg_pts:
            full_route_pts.extend(leg_pts[1:])
        else:
            full_route_pts.extend(leg_pts)
            
    est_duration = round((total_dist / 25.0) * 60.0 + (len(ordered_stops) * 4), 1)

    return jsonify({
        'type': 'parcels',
        'driver': driver_data,
        'stops': ordered_stops,
        'current_target': ordered_stops[0] if ordered_stops else None,
        'coordinates': full_route_pts,
        'distance_km': total_dist,
        'duration_min': est_duration,
        'legs': legs
    })

# ==========================================
# --- 5-PORTAL SYSTEM ENDPOINTS & LOGIC ---
# ==========================================

# 1. PUBLIC PORTAL APIs
# ---------------------

@app.route('/api/public/rate-calculate', methods=['POST'])
def api_public_rate_calculate():
    data = request.get_json() or {}
    origin_hub_name = data.get('origin_hub')
    dest_hub_name = data.get('destination_hub')
    service_type = data.get('service_type', 'Standard')
    
    try:
        weight = float(data.get('weight', 1.0))
    except (TypeError, ValueError):
        weight = 1.0
        
    origin_hub = Hub.query.filter_by(name=origin_hub_name).first() if origin_hub_name else None
    dest_hub = Hub.query.filter_by(name=dest_hub_name).first() if dest_hub_name else None
    
    rule = None
    if origin_hub and dest_hub:
        rule = PricingRule.query.filter_by(
            origin_hub_id=origin_hub.id,
            destination_hub_id=dest_hub.id,
            service_type=service_type,
            is_active=True
        ).first()
        
    if not rule:
        rule = PricingRule.query.filter_by(service_type=service_type, is_active=True).first()
        
    base_rate = rule.base_rate if rule else (180.0 if service_type == 'Express' else 120.0)
    extra_kg_rate = rule.extra_kg_rate if rule else 40.0
    base_weight = rule.base_weight_kg if rule else 1.0
    est_hours = rule.delivery_time_hours if rule else (12 if service_type == 'Express' else 24)
    
    extra_weight = max(0.0, weight - base_weight)
    total_charge = base_rate + (extra_weight * extra_kg_rate)
    
    distance_km = 4.5
    if origin_hub and dest_hub and origin_hub.name != dest_hub.name:
        _, distance_km = dijkstra(origin_hub.name, dest_hub.name)
        
    return jsonify({
        'success': True,
        'total_charge': round(total_charge, 2),
        'base_rate': base_rate,
        'extra_kg_rate': extra_kg_rate,
        'weight': weight,
        'service_type': service_type,
        'delivery_time_hours': est_hours,
        'distance_km': round(distance_km, 2)
    })

@app.route('/api/public/branches')
def api_public_branches():
    hubs = Hub.query.all()
    data = [{
        'id': h.id,
        'name': h.name,
        'latitude': h.latitude,
        'longitude': h.longitude,
        'total_riders': len(h.drivers),
        'active_parcels': len(h.parcels)
    } for h in hubs]
    return jsonify(data)

# 2. CUSTOMER PORTAL
# ------------------

@app.route('/customer/dashboard')
@login_required
def customer_dashboard():
    if current_user.role != 'customer':
        return redirect(url_for('index'))
        
    profile = CustomerProfile.query.filter_by(user_id=current_user.id).first()
    if not profile:
        profile = CustomerProfile(
            user_id=current_user.id,
            contact_person=current_user.username,
            phone="9800000000"
        )
        db.session.add(profile)
        db.session.commit()
        
    parcels = Parcel.query.filter_by(customer_id=profile.id).order_by(Parcel.created_at.desc()).all()
    
    total_bookings = len(parcels)
    in_transit = sum(1 for p in parcels if p.status in ['Assigned', 'Picked Up', 'In Transit', 'Out For Delivery'])
    delivered = sum(1 for p in parcels if p.status == 'Delivered')
    total_spent = sum(p.delivery_charge for p in parcels if p.payment_status == 'Paid')
    
    support_tickets = SupportTicket.query.filter_by(customer_id=profile.id).order_by(SupportTicket.created_at.desc()).limit(5).all()
    
    return render_template(
        'customer_dashboard.html',
        active_page='customer_dashboard',
        profile=profile,
        parcels=parcels[:8],
        all_parcels=parcels,
        total_bookings=total_bookings,
        in_transit=in_transit,
        delivered=delivered,
        total_spent=round(total_spent, 2),
        support_tickets=support_tickets
    )

@app.route('/customer/book', methods=['GET', 'POST'])
@login_required
def customer_book():
    if current_user.role != 'customer':
        return redirect(url_for('index'))
        
    profile = CustomerProfile.query.filter_by(user_id=current_user.id).first_or_404()
    hubs = Hub.query.all()
    saved_addresses = CustomerAddress.query.filter_by(customer_id=profile.id).all()
    merchandise_types = Merchandise.query.all()
    
    if request.method == 'POST':
        sender_name = request.form.get('sender_name', '').strip()
        sender_phone = request.form.get('sender_phone', '').strip()
        receiver_name = request.form.get('receiver_name', '').strip()
        receiver_phone = request.form.get('receiver_phone', '').strip()
        pickup_address = request.form.get('pickup_address', '').strip()
        delivery_address = request.form.get('delivery_address', '').strip()
        pickup_hub = request.form.get('pickup_hub')
        delivery_hub = request.form.get('delivery_hub')
        parcel_type = request.form.get('parcel_type', 'Standard Parcel')
        service_type = request.form.get('service_type', 'Standard')
        weight = float(request.form.get('weight', 1.0))
        length = float(request.form.get('length', 10.0))
        width = float(request.form.get('width', 10.0))
        height = float(request.form.get('height', 10.0))
        payment_status = request.form.get('payment_status', 'Pending')
        cod_amount = float(request.form.get('cod_amount', 0.0)) if payment_status == 'COD' else 0.0
        
        pickup_lat = float(request.form.get('pickup_latitude', 27.7154))
        pickup_lng = float(request.form.get('pickup_longitude', 85.3123))
        delivery_lat = float(request.form.get('delivery_latitude', 27.6915))
        delivery_lng = float(request.form.get('delivery_longitude', 85.3331))
        
        if not sender_name or not sender_phone or not receiver_name or not receiver_phone:
            flash("Sender and Receiver contact details are mandatory.", "error")
            return redirect(url_for('customer_book'))
            
        # Calculate delivery charge from pricing rules
        p_hub_obj = Hub.query.filter_by(name=pickup_hub).first()
        d_hub_obj = Hub.query.filter_by(name=delivery_hub).first()
        rule = PricingRule.query.filter_by(
            origin_hub_id=p_hub_obj.id if p_hub_obj else None,
            destination_hub_id=d_hub_obj.id if d_hub_obj else None,
            service_type=service_type,
            is_active=True
        ).first() if p_hub_obj and d_hub_obj else None
        
        if not rule:
            rule = PricingRule.query.filter_by(service_type=service_type, is_active=True).first()
            
        base_rate = rule.base_rate if rule else (180.0 if service_type == 'Express' else 120.0)
        extra_kg_rate = rule.extra_kg_rate if rule else 40.0
        extra_weight = max(0.0, weight - (rule.base_weight_kg if rule else 1.0))
        delivery_charge = round(base_rate + (extra_weight * extra_kg_rate), 2)
        
        # Generate Waybill Tracking ID
        tracking_id = f"AWB{datetime.utcnow().strftime('%y%m%d')}{random.randint(1000, 9999)}"
        
        parcel = Parcel(
            tracking_id=tracking_id,
            customer_id=profile.id,
            sender_name=sender_name,
            sender_phone=sender_phone,
            receiver_name=receiver_name,
            receiver_phone=receiver_phone,
            pickup_address=pickup_address,
            delivery_address=delivery_address,
            pickup_hub=pickup_hub or (p_hub_obj.name if p_hub_obj else "Kathmandu"),
            delivery_hub=delivery_hub or (d_hub_obj.name if d_hub_obj else "Kathmandu"),
            hub_id=p_hub_obj.id if p_hub_obj else None,
            pickup_latitude=pickup_lat,
            pickup_longitude=pickup_lng,
            delivery_latitude=delivery_lat,
            delivery_longitude=delivery_lng,
            parcel_type=parcel_type,
            service_type=service_type,
            weight=weight,
            length=length,
            width=width,
            height=height,
            delivery_charge=delivery_charge,
            payment_status=payment_status,
            cod_amount=cod_amount,
            status='Pending'
        )
        db.session.add(parcel)
        db.session.commit()
        
        # Log History & Notifications
        hist = TrackingHistory(parcel_id=parcel.id, status='Pending', location=pickup_address)
        notif = NotificationLog(parcel_id=parcel.id, message="Shipment booked via Customer Self-Service Portal.", type='Booking')
        db.session.add(hist)
        db.session.add(notif)
        db.session.commit()
        
        flash(f"Shipment booked successfully! Tracking ID: {tracking_id}", "success")
        return redirect(url_for('customer_dashboard'))
        
    return render_template(
        'customer_booking.html',
        active_page='customer_book',
        profile=profile,
        hubs=hubs,
        saved_addresses=saved_addresses,
        merchandise_types=merchandise_types
    )

@app.route('/customer/shipments')
@login_required
def customer_shipments():
    if current_user.role != 'customer':
        return redirect(url_for('index'))
    profile = CustomerProfile.query.filter_by(user_id=current_user.id).first_or_404()
    parcels = Parcel.query.filter_by(customer_id=profile.id).order_by(Parcel.created_at.desc()).all()
    return render_template('customer_shipments.html', active_page='customer_shipments', parcels=parcels, profile=profile)

@app.route('/customer/addresses')
@login_required
def customer_addresses():
    if current_user.role != 'customer':
        return redirect(url_for('index'))
    profile = CustomerProfile.query.filter_by(user_id=current_user.id).first_or_404()
    addresses = CustomerAddress.query.filter_by(customer_id=profile.id).all()
    return render_template('customer_addresses.html', active_page='customer_addresses', addresses=addresses, profile=profile)

@app.route('/customer/address/add', methods=['POST'])
@login_required
def customer_add_address():
    if current_user.role != 'customer':
        return redirect(url_for('index'))
    profile = CustomerProfile.query.filter_by(user_id=current_user.id).first_or_404()
    
    label = request.form.get('label', 'Home').strip()
    recipient_name = request.form.get('recipient_name', '').strip()
    phone = request.form.get('phone', '').strip()
    address = request.form.get('address', '').strip()
    city = request.form.get('city', 'Kathmandu').strip()
    is_default = True if request.form.get('is_default') else False
    
    if not recipient_name or not phone or not address:
        flash("Recipient Name, Phone, and Address are required.", "error")
        return redirect(url_for('customer_addresses'))
        
    if is_default:
        CustomerAddress.query.filter_by(customer_id=profile.id).update({'is_default': False})
        
    new_addr = CustomerAddress(
        customer_id=profile.id,
        label=label,
        recipient_name=recipient_name,
        phone=phone,
        address=address,
        city=city,
        is_default=is_default
    )
    db.session.add(new_addr)
    db.session.commit()
    flash("New address saved to address book!", "success")
    return redirect(url_for('customer_addresses'))

@app.route('/customer/address/delete/<int:id>')
@login_required
def customer_delete_address(id):
    if current_user.role != 'customer':
        return redirect(url_for('index'))
    profile = CustomerProfile.query.filter_by(user_id=current_user.id).first_or_404()
    addr = CustomerAddress.query.filter_by(id=id, customer_id=profile.id).first_or_404()
    db.session.delete(addr)
    db.session.commit()
    flash("Address removed.", "info")
    return redirect(url_for('customer_addresses'))

@app.route('/customer/invoices')
@login_required
def customer_invoices():
    if current_user.role != 'customer':
        return redirect(url_for('index'))
    profile = CustomerProfile.query.filter_by(user_id=current_user.id).first_or_404()
    parcels = Parcel.query.filter_by(customer_id=profile.id).order_by(Parcel.created_at.desc()).all()
    company = CompanySetting.query.first()
    return render_template('customer_invoices.html', active_page='customer_invoices', parcels=parcels, profile=profile, company=company)

@app.route('/customer/support-tickets', methods=['GET', 'POST'])
@login_required
def customer_support_tickets():
    if current_user.role != 'customer':
        return redirect(url_for('index'))
    profile = CustomerProfile.query.filter_by(user_id=current_user.id).first_or_404()
    
    if request.method == 'POST':
        subject = request.form.get('subject', '').strip()
        category = request.form.get('category', 'Delivery Issue')
        priority = request.form.get('priority', 'Medium')
        message = request.form.get('message', '').strip()
        tracking_id = request.form.get('tracking_id', '').strip()
        
        parcel = Parcel.query.filter_by(tracking_id=tracking_id).first() if tracking_id else None
        
        ticket_number = f"TKT-{random.randint(10000, 99999)}"
        ticket = SupportTicket(
            ticket_number=ticket_number,
            customer_id=profile.id,
            parcel_id=parcel.id if parcel else None,
            subject=subject,
            category=category,
            priority=priority,
            status='Open'
        )
        db.session.add(ticket)
        db.session.commit()
        
        if message:
            reply = TicketReply(
                ticket_id=ticket.id,
                user_id=current_user.id,
                message=message
            )
            db.session.add(reply)
            db.session.commit()
            
        flash(f"Support ticket {ticket_number} created! Our staff will respond shortly.", "success")
        return redirect(url_for('customer_support_tickets'))
        
    tickets = SupportTicket.query.filter_by(customer_id=profile.id).order_by(SupportTicket.created_at.desc()).all()
    parcels = Parcel.query.filter_by(customer_id=profile.id).all()
    return render_template('customer_support.html', active_page='customer_support', tickets=tickets, parcels=parcels, profile=profile)

@app.route('/customer/support-ticket/<int:id>', methods=['GET', 'POST'])
@login_required
def customer_ticket_detail(id):
    ticket = SupportTicket.query.get_or_404(id)
    
    # Allow ticket access to the customer who owns it, or admin/branch manager
    if current_user.role == 'customer':
        profile = CustomerProfile.query.filter_by(user_id=current_user.id).first_or_404()
        if ticket.customer_id != profile.id:
            return redirect(url_for('index'))
            
    if request.method == 'POST':
        message = request.form.get('message', '').strip()
        if message:
            reply = TicketReply(
                ticket_id=ticket.id,
                user_id=current_user.id,
                message=message
            )
            db.session.add(reply)
            ticket.updated_at = datetime.utcnow()
            
            # If admin/branch manager replied, set to In Progress
            if current_user.role in ['admin', 'hub_admin', 'branch_manager']:
                ticket.status = 'In Progress'
                
            db.session.commit()
            flash("Reply posted.", "success")
            
    return render_template('ticket_detail.html', ticket=ticket)

# 3. BRANCH PORTAL
# ----------------

@app.route('/branch/dashboard')
@login_required
def branch_dashboard():
    if current_user.role not in ['hub_admin', 'branch_manager', 'booking_staff', 'warehouse_staff', 'dispatcher', 'branch_staff', 'admin']:
        return redirect(url_for('index'))
        
    hub_name = get_current_hub_name()
    hub = Hub.query.filter_by(name=hub_name).first() if hub_name else Hub.query.first()
    
    if hub:
        parcels = Parcel.query.filter((Parcel.pickup_hub == hub.name) | (Parcel.delivery_hub == hub.name)).all()
        riders = Driver.query.filter((Driver.hub_id == hub.id) | (Driver.hub_id == None)).all()
        manifests = Manifest.query.filter((Manifest.origin_hub_id == hub.id) | (Manifest.destination_hub_id == hub.id)).all()
        delivery_sheets = DeliverySheet.query.filter_by(hub_id=hub.id).order_by(DeliverySheet.created_at.desc()).limit(5).all()
    else:
        parcels = Parcel.query.all()
        riders = Driver.query.all()
        manifests = Manifest.query.all()
        delivery_sheets = DeliverySheet.query.order_by(DeliverySheet.created_at.desc()).limit(5).all()
        
    total_parcels = len(parcels)
    pending_pickups = sum(1 for p in parcels if p.status == 'Pending')
    out_for_delivery = sum(1 for p in parcels if p.status == 'Out For Delivery')
    delivered_today = sum(1 for p in parcels if p.status == 'Delivered' and p.delivered_at and p.delivered_at.date() == datetime.utcnow().date())
    active_riders = sum(1 for r in riders if r.availability in ['Available', 'On Delivery'])
    
    stats = {
        'total_parcels': total_parcels,
        'pending_pickups': pending_pickups,
        'out_for_delivery': out_for_delivery,
        'delivered_today': delivered_today,
        'active_riders': active_riders,
        'total_manifests': len(manifests)
    }
    
    recent_parcels = [p for p in parcels if p.status != 'Delivered'][:8]
    
    return render_template(
        'branch_dashboard.html',
        active_page='branch_dashboard',
        hub=hub,
        stats=stats,
        recent_parcels=recent_parcels,
        riders=riders,
        delivery_sheets=delivery_sheets
    )

@app.route('/admin/booking')
@login_required
def admin_booking():
    return redirect(url_for('manage_parcels'))

@app.route('/branch/booking', methods=['GET', 'POST'])
@login_required
def branch_booking():
    if current_user.role not in ['hub_admin', 'branch_manager', 'booking_staff', 'warehouse_staff', 'dispatcher', 'branch_staff', 'admin']:
        return redirect(url_for('index'))
        
    hub_name = get_current_hub_name()
    hubs = Hub.query.all()
    customers = CustomerProfile.query.all()
    merchandise_types = Merchandise.query.all()
    
    if request.method == 'POST':
        sender_name = request.form.get('sender_name', '').strip()
        sender_phone = request.form.get('sender_phone', '').strip()
        receiver_name = request.form.get('receiver_name', '').strip()
        receiver_phone = request.form.get('receiver_phone', '').strip()
        pickup_address = request.form.get('pickup_address', '').strip()
        delivery_address = request.form.get('delivery_address', '').strip()
        pickup_hub = request.form.get('pickup_hub') or hub_name or (hubs[0].name if hubs else "Kathmandu")
        delivery_hub = request.form.get('delivery_hub') or (hubs[1].name if len(hubs) > 1 else pickup_hub)
        parcel_type = request.form.get('parcel_type', 'Standard Parcel')
        service_type = request.form.get('service_type', 'Standard')
        
        try:
            weight = float(request.form.get('weight', 1.0))
        except (ValueError, TypeError):
            weight = 1.0
            
        try:
            length = float(request.form.get('length', 10.0))
            width = float(request.form.get('width', 10.0))
            height = float(request.form.get('height', 10.0))
        except (ValueError, TypeError):
            length, width, height = 10.0, 10.0, 10.0
            
        payment_status = request.form.get('payment_status', 'Pending')
        try:
            cod_amount = float(request.form.get('cod_amount', 0.0)) if payment_status == 'COD' else 0.0
        except (ValueError, TypeError):
            cod_amount = 0.0
        
        pickup_lat = float(request.form.get('pickup_latitude', 27.7154))
        pickup_lng = float(request.form.get('pickup_longitude', 85.3123))
        delivery_lat = float(request.form.get('delivery_latitude', 27.6915))
        delivery_lng = float(request.form.get('delivery_longitude', 85.3331))
        auto_assign = bool(request.form.get('auto_assign_driver'))
        
        if not sender_name or not sender_phone or not receiver_name or not receiver_phone:
            flash("Sender and Receiver contact details are mandatory.", "error")
            return redirect(url_for('branch_booking'))
            
        p_hub_obj = Hub.query.filter_by(name=pickup_hub).first()
        d_hub_obj = Hub.query.filter_by(name=delivery_hub).first()
        rule = PricingRule.query.filter_by(
            origin_hub_id=p_hub_obj.id if p_hub_obj else None,
            destination_hub_id=d_hub_obj.id if d_hub_obj else None,
            service_type=service_type,
            is_active=True
        ).first() if p_hub_obj and d_hub_obj else None
        
        if not rule:
            rule = PricingRule.query.filter_by(service_type=service_type, is_active=True).first()
            
        base_rate = rule.base_rate if rule else (180.0 if service_type == 'Express' else 120.0)
        extra_kg_rate = rule.extra_kg_rate if rule else 40.0
        extra_weight = max(0.0, weight - (rule.base_weight_kg if rule else 1.0))
        delivery_charge = round(base_rate + (extra_weight * extra_kg_rate), 2)
        
        tracking_id = f"WB{datetime.utcnow().strftime('%y%m%d')}{random.randint(1000, 9999)}"
        
        parcel = Parcel(
            tracking_id=tracking_id,
            sender_name=sender_name,
            sender_phone=sender_phone,
            receiver_name=receiver_name,
            receiver_phone=receiver_phone,
            pickup_address=pickup_address,
            delivery_address=delivery_address,
            pickup_hub=pickup_hub,
            delivery_hub=delivery_hub,
            hub_id=p_hub_obj.id if p_hub_obj else None,
            pickup_latitude=pickup_lat,
            pickup_longitude=pickup_lng,
            delivery_latitude=delivery_lat,
            delivery_longitude=delivery_lng,
            parcel_type=parcel_type,
            service_type=service_type,
            weight=weight,
            length=length,
            width=width,
            height=height,
            delivery_charge=delivery_charge,
            payment_status=payment_status,
            cod_amount=cod_amount,
            status='Pending',
            created_at=datetime.utcnow()
        )
        db.session.add(parcel)
        db.session.commit()
        
        assigned_driver_msg = ""
        if auto_assign:
            available_drivers = Driver.query.filter(Driver.availability.in_(['Available', 'On Delivery'])).all()
            matched_driver, dist = greedy_driver_assignment(parcel, available_drivers)
            if matched_driver:
                parcel.assigned_driver_id = matched_driver.id
                parcel.status = 'Assigned'
                matched_driver.availability = 'On Delivery'
                assigned_driver_msg = f" & auto-assigned to {matched_driver.name} ({round(dist, 1)} km away)"
                
        hist = TrackingHistory(parcel_id=parcel.id, status=parcel.status, location=f"Waybill Booked: {pickup_hub} Branch")
        notif = NotificationLog(parcel_id=parcel.id, message=f"Waybill {tracking_id} booked at {pickup_hub} Branch. Fare: Rs. {delivery_charge}{assigned_driver_msg}.", type='Created')
        db.session.add(hist)
        db.session.add(notif)
        db.session.commit()
        
        flash(f"Waybill {tracking_id} generated successfully at {pickup_hub}! Fare: Rs. {delivery_charge}{assigned_driver_msg}", "success")
        return redirect(url_for('branch_dashboard'))
        
    return render_template(
        'branch_booking.html',
        active_page='branch_booking',
        hub_name=hub_name,
        hubs=hubs,
        customers=customers,
        merchandise_types=merchandise_types
    )

@app.route('/branch/delivery-sheets')
@login_required
def delivery_sheets():
    if current_user.role not in ['admin', 'hub_admin', 'branch_manager', 'dispatcher']:
        return redirect(url_for('index'))
        
    hub_id = get_current_hub_id()
    if hub_id:
        sheets = DeliverySheet.query.filter_by(hub_id=hub_id).order_by(DeliverySheet.created_at.desc()).all()
    else:
        sheets = DeliverySheet.query.order_by(DeliverySheet.created_at.desc()).all()
        
    return render_template('delivery_sheets.html', active_page='delivery_sheets', sheets=sheets)

@app.route('/branch/delivery-sheet/create', methods=['GET', 'POST'])
@login_required
def create_delivery_sheet():
    if current_user.role not in ['admin', 'hub_admin', 'branch_manager', 'dispatcher']:
        return redirect(url_for('index'))
        
    hub_name = get_current_hub_name()
    hub = Hub.query.filter_by(name=hub_name).first() if hub_name else Hub.query.first()
    
    if request.method == 'POST':
        rider_id = int(request.form.get('rider_id'))
        parcel_ids = request.form.getlist('parcel_ids')
        notes = request.form.get('notes', '').strip()
        
        if not parcel_ids:
            flash("Please select at least one parcel for this delivery sheet.", "error")
            return redirect(url_for('create_delivery_sheet'))
            
        rider = Driver.query.get_or_404(rider_id)
        sheet_number = f"DS-{datetime.utcnow().strftime('%y%m%d')}-{random.randint(1000, 9999)}"
        
        total_cod = 0.0
        sheet = DeliverySheet(
            sheet_number=sheet_number,
            hub_id=hub.id if hub else rider.hub_id,
            rider_id=rider.id,
            status='Created',
            total_parcels=len(parcel_ids),
            notes=notes
        )
        db.session.add(sheet)
        db.session.commit()
        
        for idx, pid in enumerate(parcel_ids, 1):
            p = Parcel.query.get(int(pid))
            if p:
                p.assigned_driver_id = rider.id
                p.status = 'Out For Delivery'
                if p.payment_status == 'COD':
                    total_cod += p.delivery_charge
                    
                item = DeliverySheetItem(
                    delivery_sheet_id=sheet.id,
                    parcel_id=p.id,
                    stop_sequence=idx,
                    status='Pending'
                )
                db.session.add(item)
                
                hist = TrackingHistory(parcel_id=p.id, status='Out For Delivery', location=f"Assigned to Courier {rider.name} on Sheet {sheet_number}")
                notif = NotificationLog(parcel_id=p.id, message=f"Out for delivery with rider {rider.name}.", type='Out For Delivery')
                db.session.add(hist)
                db.session.add(notif)
                
        sheet.total_cod_amount = total_cod
        rider.availability = 'On Delivery'
        db.session.commit()
        
        flash(f"Delivery Sheet {sheet_number} created with {len(parcel_ids)} parcels assigned to {rider.name}!", "success")
        return redirect(url_for('delivery_sheets'))
        
    available_parcels = Parcel.query.filter(Parcel.status.in_(['Assigned', 'Picked Up', 'In Transit', 'Pending'])).all()
    riders = Driver.query.filter(Driver.availability.in_(['Available', 'On Delivery'])).all()
    
    return render_template(
        'create_delivery_sheet.html',
        active_page='delivery_sheets',
        hub=hub,
        available_parcels=available_parcels,
        riders=riders
    )

@app.route('/branch/delivery-sheet/<int:id>')
@login_required
def view_delivery_sheet(id):
    sheet = DeliverySheet.query.get_or_404(id)
    company = CompanySetting.query.first()
    return render_template('delivery_sheet_detail.html', sheet=sheet, company=company, no_layout=True)

# 4. ADMIN PRICING RULES & SETTINGS
# ---------------------------------

@app.route('/admin/pricing-rules')
@login_required
def pricing_rules():
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    rules = PricingRule.query.all()
    hubs = Hub.query.all()
    return render_template('pricing_rules.html', active_page='pricing_rules', rules=rules, hubs=hubs)

@app.route('/admin/pricing-rule/add', methods=['POST'])
@login_required
def add_pricing_rule():
    if current_user.role != 'admin':
        return redirect(url_for('index'))
        
    origin_hub_id = request.form.get('origin_hub_id')
    destination_hub_id = request.form.get('destination_hub_id')
    service_type = request.form.get('service_type', 'Standard')
    base_weight_kg = float(request.form.get('base_weight_kg', 1.0))
    base_rate = float(request.form.get('base_rate', 100.0))
    extra_kg_rate = float(request.form.get('extra_kg_rate', 40.0))
    delivery_time_hours = int(request.form.get('delivery_time_hours', 24))
    
    rule = PricingRule(
        origin_hub_id=int(origin_hub_id) if origin_hub_id else None,
        destination_hub_id=int(destination_hub_id) if destination_hub_id else None,
        service_type=service_type,
        base_weight_kg=base_weight_kg,
        base_rate=base_rate,
        extra_kg_rate=extra_kg_rate,
        delivery_time_hours=delivery_time_hours,
        is_active=True
    )
    db.session.add(rule)
    db.session.commit()
    flash("Pricing rule created successfully!", "success")
    return redirect(url_for('pricing_rules'))

@app.route('/admin/pricing-rule/delete/<int:id>')
@login_required
def delete_pricing_rule(id):
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    rule = PricingRule.query.get_or_404(id)
    db.session.delete(rule)
    db.session.commit()
    flash("Pricing rule deleted.", "info")
    return redirect(url_for('pricing_rules'))

@app.route('/admin/company-settings', methods=['GET', 'POST'])
@login_required
def company_settings():
    if current_user.role != 'admin':
        return redirect(url_for('index'))
        
    setting = CompanySetting.query.first()
    if not setting:
        setting = CompanySetting()
        db.session.add(setting)
        db.session.commit()
        
    if request.method == 'POST':
        setting.company_name = request.form.get('company_name', '').strip()
        setting.phone = request.form.get('phone', '').strip()
        setting.email = request.form.get('email', '').strip()
        setting.address = request.form.get('address', '').strip()
        setting.vat_pan_number = request.form.get('vat_pan_number', '').strip()
        setting.currency = request.form.get('currency', 'Rs.').strip()
        setting.terms_conditions = request.form.get('terms_conditions', '').strip()
        db.session.commit()
        flash("Company settings updated successfully!", "success")
        
    return render_template('company_settings.html', active_page='company_settings', setting=setting)

@app.route('/admin/cod-reconciliation')
@login_required
def cod_reconciliation():
    if current_user.role not in ['admin', 'hub_admin']:
        return redirect(url_for('index'))
        
    drivers = Driver.query.all()
    cod_parcels = Parcel.query.filter_by(payment_status='COD').all()
    
    total_cod = sum(p.delivery_charge for p in cod_parcels)
    collected_cod = sum(p.delivery_charge for p in cod_parcels if p.status == 'Delivered')
    pending_cod = total_cod - collected_cod
    
    return render_template(
        'cod_reconciliation.html',
        active_page='cod_reconciliation',
        drivers=drivers,
        cod_parcels=cod_parcels,
        total_cod=round(total_cod, 2),
        collected_cod=round(collected_cod, 2),
        pending_cod=round(pending_cod, 2)
    )

if __name__ == '__main__':
    app.run(debug=True, port=5000)

