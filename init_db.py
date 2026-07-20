from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta
import random

# Import db and models
from models import db, User, Driver, Parcel, TrackingHistory, NotificationLog, Hub, HubAdmin
from app import app  # Import app to use its database context

def seed_database():
    with app.app_context():
        # Drop all tables and recreate them
        db.drop_all()
        db.create_all()
        
        print("Database tables created successfully!")
        
        # 1. Create Users
        # Admin User
        admin_user = User(
            username='admin',
            password_hash=generate_password_hash('admin123'),
            role='admin'
        )
        db.session.add(admin_user)
        
        # Driver 1 User
        driver1_user = User(
            username='driver1',
            password_hash=generate_password_hash('driver123'),
            role='driver'
        )
        db.session.add(driver1_user)
        
        # Driver 2 User
        driver2_user = User(
            username='driver2',
            password_hash=generate_password_hash('driver223'),
            role='driver'
        )
        db.session.add(driver2_user)

        # Hub Admin User
        hubadmin1_user = User(
            username='hubadmin1',
            password_hash=generate_password_hash('hub123'),
            role='hub_admin'
        )
        db.session.add(hubadmin1_user)
        
        db.session.commit()
        print("Users seeded successfully!")

        # Seed Hubs
        from algorithms import HUBS, get_closest_hub
        seeded_hubs = {}
        for hub_name, coords in HUBS.items():
            hub = Hub(name=hub_name, latitude=coords['lat'], longitude=coords['lng'])
            db.session.add(hub)
            seeded_hubs[hub_name] = hub
        db.session.commit()
        print("Hubs seeded successfully!")

        # Seed Hub Admin Profile
        hub_admin_profile = HubAdmin(
            user_id=hubadmin1_user.id,
            name='Anup Dahal',
            phone='9867123456',
            email='anup@parcelfleet.com',
            hub_id=seeded_hubs['Kalanki'].id
        )
        db.session.add(hub_admin_profile)
        db.session.commit()
        print("Hub admin profile seeded successfully!")
        
        # 2. Create Drivers
        # Driver 1 Profile (Suman Thapa - positioned at Kalanki)
        driver1_profile = Driver(
            user_id=driver1_user.id,
            name='Suman Thapa',
            phone='9841234567',
            email='suman@parcelfleet.com',
            vehicle_number='BA 2 PA 5678',
            availability='Available',
            latitude=27.6946,  # Kalanki Coordinates
            longitude=85.2813,
            completed_deliveries=8,
            average_delivery_time=24.5
        )
        db.session.add(driver1_profile)
        
        # Driver 2 Profile (Niranjan Shrestha - positioned at Chabahil)
        driver2_profile = Driver(
            user_id=driver2_user.id,
            name='Niranjan Shrestha',
            phone='9801234567',
            email='niranjan@parcelfleet.com',
            vehicle_number='BA 3 PA 1234',
            availability='Available',
            latitude=27.7172,  # Chabahil Coordinates
            longitude=85.3444,
            completed_deliveries=12,
            average_delivery_time=19.8
        )
        db.session.add(driver2_profile)
        
        db.session.commit()
        print("Drivers seeded successfully!")
        
        # 3. Create Sample Parcels
        # Parcel 1: Standard Document - Paid (Bhaktapur to Thamel)
        parcel1 = Parcel(
            tracking_id='PF20261001',
            sender_name='Dibisha Joshi',
            sender_phone='9841999999',
            receiver_name='Ram Sharma',
            receiver_phone='9801999999',
            pickup_address='Bhaktapur',
            delivery_address='Thamel',
            pickup_latitude=27.6740,
            pickup_longitude=85.4300,
            delivery_latitude=27.7180,
            delivery_longitude=85.3150,
            pickup_hub=get_closest_hub(27.6740, 85.4300),
            delivery_hub=get_closest_hub(27.7180, 85.3150),
            parcel_type='Documents',
            weight=0.5,
            length=15.0,
            width=20.0,
            height=2.0,
            status='Pending',
            delivery_charge=100.0,
            payment_status='Paid',
            special_tags='Confidential Documents',
            created_at=datetime.utcnow() - timedelta(hours=3)
        )
        db.session.add(parcel1)
        
        # Parcel 2: Fragile Electronics - COD (Kalanki to New Baneshwor)
        parcel2 = Parcel(
            tracking_id='PF20261002',
            sender_name='Subash Pokhrel',
            sender_phone='9851122334',
            receiver_name='Anita Shrestha',
            receiver_phone='9818456789',
            pickup_address='Kalanki',
            delivery_address='New Baneshwor',
            pickup_latitude=27.6965,
            pickup_longitude=85.2835,
            delivery_latitude=27.6900,
            delivery_longitude=85.3360,
            pickup_hub=get_closest_hub(27.6965, 85.2835),
            delivery_hub=get_closest_hub(27.6900, 85.3360),
            parcel_type='Electronics',
            weight=2.5,
            length=30.0,
            width=25.0,
            height=15.0,
            status='Pending',
            delivery_charge=265.0,  # Volumetric: (30*25*15)/5000 = 2.25kg, actual 2.5kg. electronics base 200 + 2.5 * 30 = 275, let's keep 275 or 265
            payment_status='COD',
            special_tags='Fragile,Handle With Care',
            created_at=datetime.utcnow() - timedelta(hours=2)
        )
        db.session.add(parcel2)
 
        # Parcel 3: Delivered Medical Supplies - Paid (Lagankhel to Koteshwor)
        delivered_time = datetime.utcnow() - timedelta(minutes=45)
        parcel3 = Parcel(
            tracking_id='PF20261003',
            sender_name='Bir Hospital Pharmacy',
            sender_phone='9803123456',
            receiver_name='Koteshwor Clinic',
            receiver_phone='9849555666',
            pickup_address='Lagankhel',
            delivery_address='Koteshwor',
            pickup_latitude=27.6650,
            pickup_longitude=85.3200,
            delivery_latitude=27.6790,
            delivery_longitude=85.3505,
            pickup_hub=get_closest_hub(27.6650, 85.3200),
            delivery_hub=get_closest_hub(27.6790, 85.3505),
            parcel_type='Medical Supplies',
            weight=1.2,
            length=10.0,
            width=10.0,
            height=10.0,
            status='Delivered',
            delivery_charge=204.0,  # base 180 + 1.2*20 = 204
            payment_status='Paid',
            assigned_driver_id=driver2_profile.id,
            created_at=datetime.utcnow() - timedelta(hours=5),
            delivered_at=delivered_time,
            delivery_notes='Handed over safely to receptionist at reception desk. All items intact.',
            customer_signature='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAJYAAABkCAYAAAB2bM62AAAABmJLR0QA/wD/AP+gvaeTAAAHHElEQVR4nO2dbYhURRjHf+fq' # Dummy base64 signature
        )
        db.session.add(parcel3)
        
        db.session.commit()

        
        # 4. Create Tracking Histories & Notifications
        # For Parcel 1
        hist1 = TrackingHistory(
            parcel_id=parcel1.id,
            status='Pending',
            location='Bhaktapur',
            timestamp=parcel1.created_at
        )
        notif1 = NotificationLog(
            parcel_id=parcel1.id,
            message='Order PF20261001 created successfully. Delivery charge: Rs. 100.0.',
            type='Created',
            timestamp=parcel1.created_at
        )
        db.session.add(hist1)
        db.session.add(notif1)
        
        # For Parcel 2
        hist2 = TrackingHistory(
            parcel_id=parcel2.id,
            status='Pending',
            location='Kalanki',
            timestamp=parcel2.created_at
        )
        notif2 = NotificationLog(
            parcel_id=parcel2.id,
            message='Order PF20261002 created successfully. Payment Status: Cash on Delivery (COD).',
            type='Created',
            timestamp=parcel2.created_at
        )
        db.session.add(hist2)
        db.session.add(notif2)
        
        # For Parcel 3 (Complete history timeline)
        h3_1 = TrackingHistory(parcel_id=parcel3.id, status='Pending', location='Lagankhel', timestamp=parcel3.created_at)
        h3_2 = TrackingHistory(parcel_id=parcel3.id, status='Assigned', location='Lagankhel', timestamp=parcel3.created_at + timedelta(minutes=15))
        h3_3 = TrackingHistory(parcel_id=parcel3.id, status='Picked Up', location='Lagankhel', timestamp=parcel3.created_at + timedelta(minutes=45))
        h3_4 = TrackingHistory(parcel_id=parcel3.id, status='In Transit', location='New Baneshwor', timestamp=parcel3.created_at + timedelta(hours=2))
        h3_5 = TrackingHistory(parcel_id=parcel3.id, status='Out For Delivery', location='Koteshwor', timestamp=parcel3.created_at + timedelta(hours=3.5))
        h3_6 = TrackingHistory(parcel_id=parcel3.id, status='Delivered', location='Koteshwor', timestamp=delivered_time)
        
        n3_1 = NotificationLog(parcel_id=parcel3.id, message='Order PF20261003 created successfully.', type='Created', timestamp=parcel3.created_at)
        n3_2 = NotificationLog(parcel_id=parcel3.id, message='Driver Niranjan Shrestha assigned to deliver your parcel.', type='Assigned', timestamp=parcel3.created_at + timedelta(minutes=15))
        n3_3 = NotificationLog(parcel_id=parcel3.id, message='Driver has picked up the parcel from Lagankhel.', type='Picked Up', timestamp=parcel3.created_at + timedelta(minutes=45))
        n3_4 = NotificationLog(parcel_id=parcel3.id, message='Parcel is out for delivery with driver Niranjan Shrestha.', type='Out For Delivery', timestamp=parcel3.created_at + timedelta(hours=3.5))
        n3_5 = NotificationLog(parcel_id=parcel3.id, message='Parcel successfully delivered. Thank you for using ParcelFleet!', type='Delivered', timestamp=delivered_time)
        
        db.session.add_all([h3_1, h3_2, h3_3, h3_4, h3_5, h3_6, n3_1, n3_2, n3_3, n3_4, n3_5])
        
        db.session.commit()
        print("Database successfully initialized and seeded with premium test records!")

if __name__ == '__main__':
    seed_database()
