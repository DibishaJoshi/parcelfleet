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

    @property
    def effective_capacity_weight(self):
        """Returns the driver's vehicle weight capacity in kg."""
        if self.assigned_vehicle and self.assigned_vehicle.capacity_weight:
            return float(self.assigned_vehicle.capacity_weight)
        return 30.0  # Default bike capacity fallback (kg)

    @property
    def effective_capacity_volume(self):
        """Returns the driver's vehicle volume capacity in cubic meters (m3)."""
        if self.assigned_vehicle and self.assigned_vehicle.capacity_volume:
            return float(self.assigned_vehicle.capacity_volume)
        return 0.2  # Default bike volume fallback (m3)

    @property
    def vehicle_type_name(self):
        """Returns vehicle type string or 'Bike' as fallback."""
        if self.assigned_vehicle:
            return self.assigned_vehicle.vehicle_type
        return 'Bike'

    @property
    def assigned_parcels(self):
        """Returns the driver's associated parcels."""
        return self.parcels or []


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
    
    service_type = db.Column(db.String(50), nullable=False, default='Standard')  # 'Standard', 'Express', 'Air', 'Surface'
    cod_amount = db.Column(db.Float, default=0.0)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer_profiles.id'), nullable=True)
    
    # Extended Multi-Hub & Linked Relations
    hub_id = db.Column(db.Integer, db.ForeignKey('hubs.id'), nullable=True)
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

    @property
    def volume_m3(self):
        """Volume in cubic meters (m3), computed from dimensions in cm."""
        return (self.length * self.width * self.height) / 1000000.0

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

class HubAdmin(db.Model):
    __tablename__ = 'hub_admins'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False, unique=True)
    email = db.Column(db.String(100), nullable=True, unique=True)
    hub_id = db.Column(db.Integer, db.ForeignKey('hubs.id'), nullable=False)

class CustomerProfile(db.Model):
    __tablename__ = 'customer_profiles'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    company_name = db.Column(db.String(150), nullable=True)
    contact_person = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(100), nullable=True)
    address = db.Column(db.String(255), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    account_type = db.Column(db.String(30), default='individual')  # 'individual', 'business'
    credit_limit = db.Column(db.Float, default=0.0)
    balance = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref=db.backref('customer_profile', uselist=False, cascade="all, delete-orphan"))
    addresses = db.relationship('CustomerAddress', backref='customer', cascade="all, delete-orphan")
    support_tickets = db.relationship('SupportTicket', backref='customer', cascade="all, delete-orphan")

class CustomerAddress(db.Model):
    __tablename__ = 'customer_addresses'
    
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer_profiles.id'), nullable=False)
    label = db.Column(db.String(50), nullable=False, default='Home')  # Home, Office, Warehouse
    recipient_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    address = db.Column(db.String(255), nullable=False)
    city = db.Column(db.String(100), nullable=False)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    is_default = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class PricingRule(db.Model):
    __tablename__ = 'pricing_rules'
    
    id = db.Column(db.Integer, primary_key=True)
    origin_hub_id = db.Column(db.Integer, db.ForeignKey('hubs.id'), nullable=True)
    destination_hub_id = db.Column(db.Integer, db.ForeignKey('hubs.id'), nullable=True)
    service_type = db.Column(db.String(50), nullable=False, default='Standard')  # 'Standard', 'Express', 'Air', 'Surface'
    base_weight_kg = db.Column(db.Float, default=1.0)
    base_rate = db.Column(db.Float, nullable=False, default=100.0)
    extra_kg_rate = db.Column(db.Float, nullable=False, default=40.0)
    cod_percentage = db.Column(db.Float, default=0.0)  # COD processing fee %
    delivery_time_hours = db.Column(db.Integer, default=24)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    origin_hub = db.relationship('Hub', foreign_keys=[origin_hub_id])
    destination_hub = db.relationship('Hub', foreign_keys=[destination_hub_id])

class DeliverySheet(db.Model):
    __tablename__ = 'delivery_sheets'
    
    id = db.Column(db.Integer, primary_key=True)
    sheet_number = db.Column(db.String(50), unique=True, nullable=False)
    hub_id = db.Column(db.Integer, db.ForeignKey('hubs.id'), nullable=False)
    rider_id = db.Column(db.Integer, db.ForeignKey('drivers.id'), nullable=False)
    status = db.Column(db.String(30), default='Created')  # 'Created', 'Out For Delivery', 'Completed', 'Cancelled'
    total_parcels = db.Column(db.Integer, default=0)
    total_cod_amount = db.Column(db.Float, default=0.0)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    dispatched_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    
    hub = db.relationship('Hub', backref='delivery_sheets')
    rider = db.relationship('Driver', backref='delivery_sheets')
    items = db.relationship('DeliverySheetItem', backref='delivery_sheet', cascade="all, delete-orphan")

class DeliverySheetItem(db.Model):
    __tablename__ = 'delivery_sheet_items'
    
    id = db.Column(db.Integer, primary_key=True)
    delivery_sheet_id = db.Column(db.Integer, db.ForeignKey('delivery_sheets.id'), nullable=False)
    parcel_id = db.Column(db.Integer, db.ForeignKey('parcels.id'), nullable=False)
    stop_sequence = db.Column(db.Integer, default=1)
    status = db.Column(db.String(30), default='Pending')  # 'Pending', 'Delivered', 'Failed Attempt'
    notes = db.Column(db.String(255), nullable=True)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    parcel = db.relationship('Parcel', backref='delivery_sheet_items')

class SupportTicket(db.Model):
    __tablename__ = 'support_tickets'
    
    id = db.Column(db.Integer, primary_key=True)
    ticket_number = db.Column(db.String(50), unique=True, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer_profiles.id'), nullable=True)
    parcel_id = db.Column(db.Integer, db.ForeignKey('parcels.id'), nullable=True)
    subject = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50), default='Delivery Issue')  # 'Delivery Issue', 'Tracking', 'Billing', 'General'
    priority = db.Column(db.String(20), default='Medium')  # 'Low', 'Medium', 'High', 'Urgent'
    status = db.Column(db.String(30), default='Open')  # 'Open', 'In Progress', 'Resolved', 'Closed'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    parcel = db.relationship('Parcel', backref='support_tickets')
    replies = db.relationship('TicketReply', backref='ticket', cascade="all, delete-orphan", order_by="TicketReply.created_at.asc()")

class TicketReply(db.Model):
    __tablename__ = 'ticket_replies'
    
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('support_tickets.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User')

class CompanySetting(db.Model):
    __tablename__ = 'company_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(150), default='ParcelFleet Courier Services')
    phone = db.Column(db.String(50), default='+977-1-4567890')
    email = db.Column(db.String(100), default='info@parcelfleet.com.np')
    address = db.Column(db.String(255), default='Patan, Lalitpur, Nepal')
    vat_pan_number = db.Column(db.String(50), default='601234567')
    currency = db.Column(db.String(10), default='Rs.')
    terms_conditions = db.Column(db.Text, nullable=True)

