from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'admin' or 'driver'
    
    # Relationships
    driver_profile = db.relationship('Driver', backref='user', uselist=False, cascade="all, delete-orphan")

class Driver(db.Model):
    __tablename__ = 'drivers'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False, unique=True)
    email = db.Column(db.String(100), nullable=True, unique=True)
    vehicle_number = db.Column(db.String(50), nullable=False)
    availability = db.Column(db.String(20), default='Available')  # 'Available', 'On Delivery', 'Offline', 'On Break'
    latitude = db.Column(db.Float, nullable=False, default=27.7172)  # Default Kathmandu Coordinates
    longitude = db.Column(db.Float, nullable=False, default=85.3240)
    
    completed_deliveries = db.Column(db.Integer, default=0)
    average_delivery_time = db.Column(db.Float, default=0.0)  # In minutes
    
    # Relationships
    parcels = db.relationship('Parcel', backref='assigned_driver')

class Parcel(db.Model):
    __tablename__ = 'parcels'
    
    id = db.Column(db.Integer, primary_key=True)
    tracking_id = db.Column(db.String(50), unique=True, nullable=False)
    
    sender_name = db.Column(db.String(100), nullable=False)
    sender_phone = db.Column(db.String(20), nullable=False)
    receiver_name = db.Column(db.String(100), nullable=False)
    receiver_phone = db.Column(db.String(20), nullable=False)
    
    pickup_address = db.Column(db.String(100), nullable=False)  # Kathmandu Hub Node
    delivery_address = db.Column(db.String(100), nullable=False)  # Kathmandu Hub Node
    
    pickup_latitude = db.Column(db.Float, nullable=False, default=27.7154)
    pickup_longitude = db.Column(db.Float, nullable=False, default=85.3123)
    delivery_latitude = db.Column(db.Float, nullable=False, default=27.6915)
    delivery_longitude = db.Column(db.Float, nullable=False, default=85.3331)
    
    parcel_type = db.Column(db.String(50), nullable=False)  # Documents, Electronics, Clothing, Food Items, Fragile Goods, Medical Supplies, Others
    weight = db.Column(db.Float, nullable=False)  # Actual weight in kg
    length = db.Column(db.Float, nullable=False, default=10.0)  # Dimensions in cm
    width = db.Column(db.Float, nullable=False, default=10.0)
    height = db.Column(db.Float, nullable=False, default=10.0)
    
    status = db.Column(db.String(30), default='Pending')  # 'Pending', 'Assigned', 'Picked Up', 'In Transit', 'Out For Delivery', 'Delivered', 'Cancelled'
    delivery_charge = db.Column(db.Float, nullable=False, default=0.0)
    payment_status = db.Column(db.String(20), default='Pending')  # 'Pending', 'Paid', 'COD'
    
    assigned_driver_id = db.Column(db.Integer, db.ForeignKey('drivers.id'), nullable=True)
    
    # Verification and Attempt Tracking
    pickup_image = db.Column(db.String(255), nullable=True)  # Filename
    delivery_image = db.Column(db.String(255), nullable=True)  # Filename
    delivery_attempts = db.Column(db.Integer, default=0)
    failed_reason = db.Column(db.String(255), nullable=True)  # E.g. 'Customer Not Available', etc.
    
    special_tags = db.Column(db.String(255), nullable=True)  # Comma-separated tags (e.g. 'Fragile, Express')
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    delivered_at = db.Column(db.DateTime, nullable=True)
    delivery_notes = db.Column(db.Text, nullable=True)
    customer_signature = db.Column(db.Text, nullable=True)  # Base64 Canvas Data
    
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
    location = db.Column(db.String(100), nullable=False)  # Node or hub name
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class NotificationLog(db.Model):
    __tablename__ = 'notification_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    parcel_id = db.Column(db.Integer, db.ForeignKey('parcels.id'), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    type = db.Column(db.String(30), nullable=False)  # 'Created', 'Assigned', 'Picked Up', 'Out For Delivery', 'Delivered', 'Failed'
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
