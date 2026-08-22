from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(30), nullable=False)  # 'admin', 'hub_admin', 'booking_staff', 'warehouse_staff', 'dispatcher', 'delivery_staff', 'branch_staff', 'driver'
    permissions = db.Column(db.String(255), nullable=True) # Comma-separated permissions: view,create,edit,delete,assign,dispatch,reports,settings
    
    # Relationships
    driver_profile = db.relationship('Driver', backref='user', uselist=False, cascade="all, delete-orphan")
    hub_admin_profile = db.relationship('HubAdmin', backref='user', uselist=False, cascade="all, delete-orphan")

class Vehicle(db.Model):
    __tablename__ = 'vehicles'
    
    id = db.Column(db.Integer, primary_key=True)
    vehicle_code = db.Column(db.String(50), unique=True, nullable=False)
    license_plate = db.Column(db.String(50), unique=True, nullable=False)
    vehicle_type = db.Column(db.String(30), nullable=False)  # 'Bike', 'Van', 'Truck', 'Pickup', 'Car'
    capacity_weight = db.Column(db.Float, nullable=False, default=100.0)  # in kg
    capacity_volume = db.Column(db.Float, nullable=False, default=1.0)  # in cubic meters
    fuel_type = db.Column(db.String(30), default='Petrol')  # Petrol, Diesel, Electric, Hybrid
    current_status = db.Column(db.String(30), default='Available')  # 'Available', 'Delivering', 'Maintenance', 'Out of Service'
    current_location = db.Column(db.String(100), nullable=True)
    last_service_date = db.Column(db.DateTime, nullable=True)
    insurance_expiry = db.Column(db.DateTime, nullable=True)
    remarks = db.Column(db.Text, nullable=True)
    
    hub_id = db.Column(db.Integer, db.ForeignKey('hubs.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    maintenance_records = db.relationship('VehicleMaintenance', backref='vehicle', cascade="all, delete-orphan")
    assignments = db.relationship('Assignment', backref='vehicle', cascade="all, delete-orphan")
    drivers = db.relationship('Driver', backref='assigned_vehicle', foreign_keys="Driver.assigned_vehicle_id")

class Driver(db.Model):
    __tablename__ = 'drivers'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False, unique=True)
    email = db.Column(db.String(100), nullable=True, unique=True)
    vehicle_number = db.Column(db.String(50), nullable=False)  # Kept for backward compatibility
    availability = db.Column(db.String(20), default='Available')  # 'Available', 'On Delivery', 'Offline', 'On Break'
    latitude = db.Column(db.Float, nullable=False, default=27.7172)  # Default Kathmandu Coordinates
    longitude = db.Column(db.Float, nullable=False, default=85.3240)
    
    completed_deliveries = db.Column(db.Integer, default=0)
    average_delivery_time = db.Column(db.Float, default=0.0)  # In minutes
    
    # Extended Driver Attributes
    employee_code = db.Column(db.String(50), unique=True, nullable=True)
    address = db.Column(db.String(255), nullable=True)
    license_number = db.Column(db.String(50), nullable=True)
    license_expiry = db.Column(db.DateTime, nullable=True)
    joining_date = db.Column(db.DateTime, default=datetime.utcnow)
    assigned_vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicles.id'), nullable=True)
    emergency_contact = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(30), default='Available')  # 'Available', 'Delivering', 'Off Duty', 'On Leave'
    hub_id = db.Column(db.Integer, db.ForeignKey('hubs.id'), nullable=True)
    rating = db.Column(db.Float, default=5.0)
    remarks = db.Column(db.Text, nullable=True)
    
    total_deliveries = db.Column(db.Integer, default=0)
    successful_deliveries = db.Column(db.Integer, default=0)
    failed_deliveries = db.Column(db.Integer, default=0)
    
    # Relationships
    parcels = db.relationship('Parcel', backref='assigned_driver', foreign_keys="Parcel.assigned_driver_id")
    assignments = db.relationship('Assignment', backref='driver', cascade="all, delete-orphan")

class VehicleMaintenance(db.Model):
    __tablename__ = 'vehicle_maintenance'
    
    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicles.id'), nullable=False)
    maintenance_type = db.Column(db.String(50), nullable=False)  # 'Routine', 'Repair', 'Inspection', 'Emergency'
    description = db.Column(db.Text, nullable=True)
    service_date = db.Column(db.DateTime, nullable=False)
    next_service_date = db.Column(db.DateTime, nullable=True)
    cost = db.Column(db.Float, default=0.0)
    workshop = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(30), default='Scheduled')  # 'Scheduled', 'Completed', 'Cancelled'
    
    hub_id = db.Column(db.Integer, db.ForeignKey('hubs.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Assignment(db.Model):
    __tablename__ = 'vehicle_assignments'
    
    id = db.Column(db.Integer, primary_key=True)
    manifest_id = db.Column(db.Integer, db.ForeignKey('manifests.id'), nullable=True)
    delivery_id = db.Column(db.Integer, db.ForeignKey('parcels.id'), nullable=True)
    driver_id = db.Column(db.Integer, db.ForeignKey('drivers.id'), nullable=False)
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicles.id'), nullable=False)
    assigned_date = db.Column(db.DateTime, default=datetime.utcnow)
    dispatch_time = db.Column(db.DateTime, nullable=True)
    expected_return = db.Column(db.DateTime, nullable=True)
    actual_return = db.Column(db.DateTime, nullable=True)
    assignment_status = db.Column(db.String(30), default='Active')  # 'Active', 'Returned', 'Cancelled'
    
    hub_id = db.Column(db.Integer, db.ForeignKey('hubs.id'), nullable=True)
    
    # Relationships
    manifest = db.relationship('Manifest', backref='assignments')
    delivery = db.relationship('Parcel', backref='assignments')
    hub = db.relationship('Hub', backref='assignments')

class Manifest(db.Model):
    __tablename__ = 'manifests'
    
    id = db.Column(db.Integer, primary_key=True)
    manifest_number = db.Column(db.String(50), unique=True, nullable=False)
    route = db.Column(db.String(255), nullable=True)
    origin_hub_id = db.Column(db.Integer, db.ForeignKey('hubs.id'), nullable=True)
    destination_hub_id = db.Column(db.Integer, db.ForeignKey('hubs.id'), nullable=True)
    assigned_driver_id = db.Column(db.Integer, db.ForeignKey('drivers.id'), nullable=True)
    assigned_vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicles.id'), nullable=True)
    total_parcels = db.Column(db.Integer, default=0)
    total_weight = db.Column(db.Float, default=0.0)
    dispatch_date = db.Column(db.DateTime, nullable=True)
    arrival_date = db.Column(db.DateTime, nullable=True)
    manifest_status = db.Column(db.String(30), default='Draft')  # 'Draft', 'Created', 'Dispatched', 'Completed', 'Cancelled'
    
    hub_id = db.Column(db.Integer, db.ForeignKey('hubs.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    items = db.relationship('ManifestItem', backref='manifest', cascade="all, delete-orphan")
    origin_hub = db.relationship('Hub', foreign_keys=[origin_hub_id])
    destination_hub = db.relationship('Hub', foreign_keys=[destination_hub_id])
    assigned_driver = db.relationship('Driver', foreign_keys=[assigned_driver_id])
    assigned_vehicle = db.relationship('Vehicle', foreign_keys=[assigned_vehicle_id])

class ManifestItem(db.Model):
    __tablename__ = 'manifest_items'
    
    id = db.Column(db.Integer, primary_key=True)
    manifest_id = db.Column(db.Integer, db.ForeignKey('manifests.id'), nullable=False)
    parcel_id = db.Column(db.Integer, db.ForeignKey('parcels.id'), nullable=False)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    parcel = db.relationship('Parcel', backref='manifest_items')

class Shipper(db.Model):
    __tablename__ = 'shippers'
    
    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(100), nullable=False)
    contact_person = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(100), nullable=True)
    address = db.Column(db.String(255), nullable=False)
    billing_address = db.Column(db.String(255), nullable=True)
    credit_limit = db.Column(db.Float, default=0.0)
    outstanding_balance = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(30), default='Active')  # 'Active', 'Inactive', 'Suspended'
    
    hub_id = db.Column(db.Integer, db.ForeignKey('hubs.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    parcels = db.relationship('Parcel', backref='shipper', cascade="all, delete-orphan")

class Consignee(db.Model):
    __tablename__ = 'consignees'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    alternate_phone = db.Column(db.String(20), nullable=True)
    address = db.Column(db.String(255), nullable=False)
    city = db.Column(db.String(100), nullable=True, default='Kathmandu')
    state = db.Column(db.String(100), nullable=True, default='Bagmati')
    country = db.Column(db.String(100), nullable=True, default='Nepal')
    postal_code = db.Column(db.String(20), nullable=True)
    delivery_instructions = db.Column(db.Text, nullable=True)
    
    hub_id = db.Column(db.Integer, db.ForeignKey('hubs.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    parcels = db.relationship('Parcel', backref='consignee', cascade="all, delete-orphan")

class Merchandise(db.Model):
    __tablename__ = 'merchandise'
    
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(50), nullable=False)  # Documents, Electronics, Clothing, Food Items, Fragile Goods, Medical Supplies, Others
    category = db.Column(db.String(50), nullable=True)
    description = db.Column(db.Text, nullable=True)
    weight = db.Column(db.Float, default=1.0)
    unit = db.Column(db.String(10), default='kg')
    fragile = db.Column(db.Boolean, default=False)
    hazardous = db.Column(db.Boolean, default=False)
    temperature_controlled = db.Column(db.Boolean, default=False)
    default_charge = db.Column(db.Float, default=100.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    parcels = db.relationship('Parcel', backref='merchandise')

class Parcel(db.Model):
    __tablename__ = 'parcels'
    
    id = db.Column(db.Integer, primary_key=True)
    tracking_id = db.Column(db.String(50), unique=True, nullable=False)
    
    sender_name = db.Column(db.String(100), nullable=False)
    sender_phone = db.Column(db.String(20), nullable=False)
    receiver_name = db.Column(db.String(100), nullable=False)
    receiver_phone = db.Column(db.String(20), nullable=False)
    
    pickup_address = db.Column(db.String(100), nullable=False)
    delivery_address = db.Column(db.String(100), nullable=False)
    pickup_hub = db.Column(db.String(100), nullable=True)
    delivery_hub = db.Column(db.String(100), nullable=True)
    
    pickup_latitude = db.Column(db.Float, nullable=False, default=27.7154)
    pickup_longitude = db.Column(db.Float, nullable=False, default=85.3123)
    delivery_latitude = db.Column(db.Float, nullable=False, default=27.6915)
    delivery_longitude = db.Column(db.Float, nullable=False, default=85.3331)
    
    parcel_type = db.Column(db.String(50), nullable=False)
    weight = db.Column(db.Float, nullable=False)
    length = db.Column(db.Float, nullable=False, default=10.0)
    width = db.Column(db.Float, nullable=False, default=10.0)
    height = db.Column(db.Float, nullable=False, default=10.0)
    
    status = db.Column(db.String(30), default='Pending')  # 'Pending', 'Assigned', 'Manifested', 'Picked Up', 'In Transit', 'Out For Delivery', 'Delivered', 'Failed Delivery', 'Returned', 'Cancelled'
    delivery_charge = db.Column(db.Float, nullable=False, default=0.0)
    payment_status = db.Column(db.String(20), default='Pending')  # 'Pending', 'Paid', 'COD'
    
    assigned_driver_id = db.Column(db.Integer, db.ForeignKey('drivers.id'), nullable=True)
    
    # Extended Multi-Hub & Linked Relations
    hub_id = db.Column(db.Integer, db.ForeignKey('hubs.id'), nullable=True)
    shipper_id = db.Column(db.Integer, db.ForeignKey('shippers.id'), nullable=True)
    consignee_id = db.Column(db.Integer, db.ForeignKey('consignees.id'), nullable=True)
    merchandise_id = db.Column(db.Integer, db.ForeignKey('merchandise.id'), nullable=True)
    manifest_id = db.Column(db.Integer, db.ForeignKey('manifests.id'), nullable=True)
    expected_delivery_date = db.Column(db.DateTime, nullable=True)
    
    # Verification and Attempt Tracking
    pickup_image = db.Column(db.String(255), nullable=True)
    delivery_image = db.Column(db.String(255), nullable=True)
    delivery_attempts = db.Column(db.Integer, default=0)
    failed_reason = db.Column(db.String(255), nullable=True)
    
    special_tags = db.Column(db.String(255), nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    delivered_at = db.Column(db.DateTime, nullable=True)
    delivery_notes = db.Column(db.Text, nullable=True)
    customer_signature = db.Column(db.Text, nullable=True)
    
    # Relationships
    history = db.relationship('TrackingHistory', backref='parcel', cascade="all, delete-orphan", order_by="TrackingHistory.timestamp.asc()")
    notifications = db.relationship('NotificationLog', backref='parcel', cascade="all, delete-orphan", order_by="NotificationLog.timestamp.asc()")
    
    @property
    def volumetric_weight(self):
        return (self.length * self.width * self.height) / 5000.0
        
    @property
    def chargeable_weight(self):
        return max(self.weight, self.volumetric_weight)

class TrackingHistory(db.Model):
    __tablename__ = 'tracking_history'
    
    id = db.Column(db.Integer, primary_key=True)
    parcel_id = db.Column(db.Integer, db.ForeignKey('parcels.id'), nullable=False)
    status = db.Column(db.String(30), nullable=False)
    location = db.Column(db.String(100), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class NotificationLog(db.Model):
    __tablename__ = 'notification_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    parcel_id = db.Column(db.Integer, db.ForeignKey('parcels.id'), nullable=True)
    message = db.Column(db.String(255), nullable=False)
    type = db.Column(db.String(30), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Hub(db.Model):
    __tablename__ = 'hubs'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    
    # Relationships
    hub_admins = db.relationship('HubAdmin', backref='hub', cascade="all, delete-orphan")
    vehicles = db.relationship('Vehicle', backref='hub', cascade="all, delete-orphan")
    drivers = db.relationship('Driver', backref='hub', cascade="all, delete-orphan", foreign_keys="Driver.hub_id")
    parcels = db.relationship('Parcel', backref='hub', cascade="all, delete-orphan", foreign_keys="Parcel.hub_id")
    shippers = db.relationship('Shipper', backref='hub', cascade="all, delete-orphan")
    consignees = db.relationship('Consignee', backref='hub', cascade="all, delete-orphan")

class HubAdmin(db.Model):
    __tablename__ = 'hub_admins'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False, unique=True)
    email = db.Column(db.String(100), nullable=True, unique=True)
    hub_id = db.Column(db.Integer, db.ForeignKey('hubs.id'), nullable=False)
