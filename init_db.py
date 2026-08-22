from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta
import random

# Import db and models
from models import (
    db, User, Driver, Parcel, TrackingHistory, NotificationLog, Hub, HubAdmin,
    Vehicle, VehicleMaintenance, Assignment, Manifest, ManifestItem, Shipper, Consignee, Merchandise
)
from app import app  # Import app to use its database context

def seed_database():
    with app.app_context():
        # Drop all tables and recreate them
        db.drop_all()
        db.create_all()
        
        print("Database tables created successfully!")
        
        # 1. Create Users
        # Main Admin User
        admin_user = User(
            username='admin',
            password_hash=generate_password_hash('admin123'),
            role='admin',
            permissions='view,create,edit,delete,assign,dispatch,reports,settings'
        )
        db.session.add(admin_user)
        
        # Driver 1 User
        driver1_user = User(
            username='driver1',
            password_hash=generate_password_hash('driver123'),
            role='driver',
            permissions='view,edit'
        )
        db.session.add(driver1_user)
        
        # Driver 2 User
        driver2_user = User(
            username='driver2',
            password_hash=generate_password_hash('driver223'),
            role='driver',
            permissions='view,edit'
        )
        db.session.add(driver2_user)

        # Hub Admin User
        hubadmin1_user = User(
            username='hubadmin1',
            password_hash=generate_password_hash('hub123'),
            role='hub_admin',
            permissions='view,create,edit,assign,dispatch,reports'
        )
        db.session.add(hubadmin1_user)

        # Staff Users
        dispatcher_user = User(
            username='dispatcher1',
            password_hash=generate_password_hash('dispatch123'),
            role='dispatcher',
            permissions='view,assign,dispatch'
        )
        db.session.add(dispatcher_user)
        
        db.session.commit()
        print("Users seeded successfully!")

        # 2. Seed Hubs
        from algorithms import HUBS, get_closest_hub
        seeded_hubs = {}
        for hub_name, coords in HUBS.items():
            hub = Hub(name=hub_name, latitude=coords['lat'], longitude=coords['lng'])
            db.session.add(hub)
            seeded_hubs[hub_name] = hub
        db.session.commit()
        print("Hubs seeded successfully!")

        # 3. Seed Hub Admin Profile
        kalanki_hub = seeded_hubs['Kalanki']
        chabahil_hub = seeded_hubs['Chabahil']
        thamel_hub = seeded_hubs['Thamel']

        hub_admin_profile = HubAdmin(
            user_id=hubadmin1_user.id,
            name='Anup Dahal',
            phone='9867123456',
            email='anup@parcelfleet.com',
            hub_id=kalanki_hub.id
        )
        db.session.add(hub_admin_profile)
        db.session.commit()
        print("Hub admin profile seeded successfully!")
        
        # 4. Seed Vehicles
        v1 = Vehicle(
            vehicle_code='V-BIKE-01',
            license_plate='BA 2 PA 5678',
            vehicle_type='Bike',
            capacity_weight=30.0,
            capacity_volume=0.2,
            fuel_type='Petrol',
            current_status='Available',
            current_location='Kalanki Hub',
            last_service_date=datetime.utcnow() - timedelta(days=20),
            insurance_expiry=datetime.utcnow() + timedelta(days=180),
            remarks='Equipped with rear insulated top box.',
            hub_id=kalanki_hub.id
        )
        v2 = Vehicle(
            vehicle_code='V-VAN-01',
            license_plate='BA 3 PA 1234',
            vehicle_type='Van',
            capacity_weight=800.0,
            capacity_volume=4.5,
            fuel_type='Diesel',
            current_status='Available',
            current_location='Chabahil Hub',
            last_service_date=datetime.utcnow() - timedelta(days=45),
            insurance_expiry=datetime.utcnow() + timedelta(days=90),
            remarks='Heavy parcel delivery van.',
            hub_id=chabahil_hub.id
        )
        v3 = Vehicle(
            vehicle_code='V-TRUCK-01',
            license_plate='BA 1 CHA 9988',
            vehicle_type='Truck',
            capacity_weight=3000.0,
            capacity_volume=18.0,
            fuel_type='Diesel',
            current_status='Maintenance',
            current_location='Kalanki Workshop',
            last_service_date=datetime.utcnow() - timedelta(days=90),
            insurance_expiry=datetime.utcnow() - timedelta(days=5), # Overdue warning test!
            remarks='Engine tune-up scheduled.',
            hub_id=kalanki_hub.id
        )
        db.session.add_all([v1, v2, v3])
        db.session.commit()
        print("Vehicles seeded successfully!")

        # 5. Seed Drivers
        driver1_profile = Driver(
            user_id=driver1_user.id,
            name='Suman Thapa',
            phone='9841234567',
            email='suman@parcelfleet.com',
            vehicle_number=v1.license_plate,
            availability='Available',
            latitude=27.6946,
            longitude=85.2813,
            completed_deliveries=8,
            average_delivery_time=24.5,
            employee_code='DRV-1001',
            address='Kalanki, Kathmandu',
            license_number='LIC-998877',
            license_expiry=datetime.utcnow() + timedelta(days=300),
            joining_date=datetime.utcnow() - timedelta(days=365),
            assigned_vehicle_id=v1.id,
            emergency_contact='9841000000',
            status='Available',
            hub_id=kalanki_hub.id,
            rating=4.8,
            remarks='Top rated driver.',
            total_deliveries=10,
            successful_deliveries=8,
            failed_deliveries=2
        )
        driver2_profile = Driver(
            user_id=driver2_user.id,
            name='Niranjan Shrestha',
            phone='9801234567',
            email='niranjan@parcelfleet.com',
            vehicle_number=v2.license_plate,
            availability='Available',
            latitude=27.7172,
            longitude=85.3444,
            completed_deliveries=12,
            average_delivery_time=19.8,
            employee_code='DRV-1002',
            address='Chabahil, Kathmandu',
            license_number='LIC-554433',
            license_expiry=datetime.utcnow() + timedelta(days=120),
            joining_date=datetime.utcnow() - timedelta(days=200),
            assigned_vehicle_id=v2.id,
            emergency_contact='9801000000',
            status='Available',
            hub_id=chabahil_hub.id,
            rating=4.9,
            remarks='Fast express rider.',
            total_deliveries=14,
            successful_deliveries=12,
            failed_deliveries=2
        )
        db.session.add_all([driver1_profile, driver2_profile])
        db.session.commit()
        print("Drivers seeded successfully!")

        # 6. Seed Shippers, Consignees & Merchandise
        shipper1 = Shipper(
            company_name='Himalaya Tech Supplies',
            contact_person='Dibisha Joshi',
            phone='9841999999',
            email='dibisha@himalayatech.com',
            address='Bhaktapur Industrial Area',
            billing_address='Bhaktapur Main Road',
            credit_limit=50000.0,
            outstanding_balance=12500.0,
            status='Active',
            hub_id=seeded_hubs['Bhaktapur'].id
        )
        shipper2 = Shipper(
            company_name='Kathmandu Pharma Traders',
            contact_person='Bir Medicals',
            phone='9803123456',
            email='sales@ktmpharma.com',
            address='Lagankhel, Lalitpur',
            billing_address='Lagankhel Plaza',
            credit_limit=100000.0,
            outstanding_balance=4500.0,
            status='Active',
            hub_id=seeded_hubs['Lagankhel'].id
        )
        db.session.add_all([shipper1, shipper2])

        consignee1 = Consignee(
            name='Ram Sharma',
            phone='9801999999',
            alternate_phone='9801999998',
            address='Thamel Chowk, Kathmandu',
            city='Kathmandu',
            state='Bagmati',
            country='Nepal',
            postal_code='44600',
            delivery_instructions='Deliver to 2nd floor reception.',
            hub_id=thamel_hub.id
        )
        consignee2 = Consignee(
            name='Anita Shrestha',
            phone='9818456789',
            address='New Baneshwor, Kathmandu',
            city='Kathmandu',
            state='Bagmati',
            country='Nepal',
            postal_code='44600',
            delivery_instructions='Call before arrival.',
            hub_id=seeded_hubs['New Baneshwor'].id
        )
        db.session.add_all([consignee1, consignee2])

        m1 = Merchandise(type='Documents', category='Office Paperwork', description='Official contracts and files', weight=0.5, unit='kg', fragile=False, hazardous=False, default_charge=100.0)
        m2 = Merchandise(type='Electronics', category='Gadgets', description='Laptops, Smartphones, Microchips', weight=2.5, unit='kg', fragile=True, hazardous=False, default_charge=250.0)
        m3 = Merchandise(type='Medical Supplies', category='Healthcare', description='Therapeutic vaccines and medicines', weight=1.2, unit='kg', fragile=True, temperature_controlled=True, default_charge=200.0)
        db.session.add_all([m1, m2, m3])
        db.session.commit()

        # 7. Seed Sample Parcels
        parcel1 = Parcel(
            tracking_id='PF20261001',
            sender_name=shipper1.contact_person,
            sender_phone=shipper1.phone,
            receiver_name=consignee1.name,
            receiver_phone=consignee1.phone,
            pickup_address='Bhaktapur',
            delivery_address='Thamel',
            pickup_latitude=27.6740,
            pickup_longitude=85.4300,
            delivery_latitude=27.7180,
            delivery_longitude=85.3150,
            pickup_hub='Bhaktapur',
            delivery_hub='Thamel',
            parcel_type='Documents',
            weight=0.5,
            length=15.0,
            width=20.0,
            height=2.0,
            status='Pending',
            delivery_charge=100.0,
            payment_status='Paid',
            special_tags='Confidential Documents',
            hub_id=seeded_hubs['Bhaktapur'].id,
            shipper_id=shipper1.id,
            consignee_id=consignee1.id,
            merchandise_id=m1.id,
            expected_delivery_date=datetime.utcnow() + timedelta(days=1),
            created_at=datetime.utcnow() - timedelta(hours=3)
        )
        parcel2 = Parcel(
            tracking_id='PF20261002',
            sender_name='Subash Pokhrel',
            sender_phone='9851122334',
            receiver_name=consignee2.name,
            receiver_phone=consignee2.phone,
            pickup_address='Kalanki',
            delivery_address='New Baneshwor',
            pickup_latitude=27.6965,
            pickup_longitude=85.2835,
            delivery_latitude=27.6900,
            delivery_longitude=85.3360,
            pickup_hub='Kalanki',
            delivery_hub='New Baneshwor',
            parcel_type='Electronics',
            weight=2.5,
            length=30.0,
            width=25.0,
            height=15.0,
            status='Pending',
            delivery_charge=265.0,
            payment_status='COD',
            special_tags='Fragile,Handle With Care',
            hub_id=kalanki_hub.id,
            consignee_id=consignee2.id,
            merchandise_id=m2.id,
            expected_delivery_date=datetime.utcnow() + timedelta(days=1),
            created_at=datetime.utcnow() - timedelta(hours=2)
        )
        delivered_time = datetime.utcnow() - timedelta(minutes=45)
        parcel3 = Parcel(
            tracking_id='PF20261003',
            sender_name=shipper2.company_name,
            sender_phone=shipper2.phone,
            receiver_name='Koteshwor Clinic',
            receiver_phone='9849555666',
            pickup_address='Lagankhel',
            delivery_address='Koteshwor',
            pickup_latitude=27.6650,
            pickup_longitude=85.3200,
            delivery_latitude=27.6790,
            delivery_longitude=85.3505,
            pickup_hub='Lagankhel',
            delivery_hub='Koteshwor',
            parcel_type='Medical Supplies',
            weight=1.2,
            length=10.0,
            width=10.0,
            height=10.0,
            status='Delivered',
            delivery_charge=204.0,
            payment_status='Paid',
            assigned_driver_id=driver2_profile.id,
            hub_id=seeded_hubs['Lagankhel'].id,
            shipper_id=shipper2.id,
            merchandise_id=m3.id,
            created_at=datetime.utcnow() - timedelta(hours=5),
            delivered_at=delivered_time,
            delivery_notes='Handed over safely to receptionist at reception desk. All items intact.',
            customer_signature='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAJYAAABkCAYAAAB2bM62AAAABmJLR0QA/wD/AP+gvaeTAAAHHElEQVR4nO2dbYhURRjHf+fq'
        )
        db.session.add_all([parcel1, parcel2, parcel3])
        db.session.commit()

        # 8. Seed Manifest & Items
        manifest1 = Manifest(
            manifest_number='MNF-2026-001',
            route='Bhaktapur -> Thamel Express',
            origin_hub_id=seeded_hubs['Bhaktapur'].id,
            destination_hub_id=thamel_hub.id,
            assigned_driver_id=driver1_profile.id,
            assigned_vehicle_id=v1.id,
            total_parcels=1,
            total_weight=0.5,
            dispatch_date=datetime.utcnow() - timedelta(hours=1),
            manifest_status='Dispatched',
            hub_id=seeded_hubs['Bhaktapur'].id
        )
        db.session.add(manifest1)
        db.session.commit()

        mi1 = ManifestItem(manifest_id=manifest1.id, parcel_id=parcel1.id)
        db.session.add(mi1)
        parcel1.manifest_id = manifest1.id
        parcel1.status = 'Manifested'

        # 9. Seed Vehicle Maintenance Record
        vm1 = VehicleMaintenance(
            vehicle_id=v3.id,
            maintenance_type='Engine Repair',
            description='Routine brake overhaul and engine oil flush.',
            service_date=datetime.utcnow() - timedelta(days=2),
            next_service_date=datetime.utcnow() + timedelta(days=30),
            cost=8500.0,
            workshop='Kalanki Central Garage',
            status='Scheduled',
            hub_id=kalanki_hub.id
        )
        db.session.add(vm1)

        # 10. Seed Vehicle Assignment Record
        asgn1 = Assignment(
            manifest_id=manifest1.id,
            driver_id=driver1_profile.id,
            vehicle_id=v1.id,
            assigned_date=datetime.utcnow() - timedelta(hours=1),
            dispatch_time=datetime.utcnow() - timedelta(hours=1),
            expected_return=datetime.utcnow() + timedelta(hours=3),
            assignment_status='Active',
            hub_id=seeded_hubs['Bhaktapur'].id
        )
        db.session.add(asgn1)

        # 11. Create Tracking Histories & Notifications
        hist1 = TrackingHistory(parcel_id=parcel1.id, status='Manifested', location='Bhaktapur Hub', timestamp=parcel1.created_at)
        notif1 = NotificationLog(parcel_id=parcel1.id, message='Order PF20261001 added to Manifest MNF-2026-001.', type='Manifested', timestamp=parcel1.created_at)
        
        hist2 = TrackingHistory(parcel_id=parcel2.id, status='Pending', location='Kalanki', timestamp=parcel2.created_at)
        notif2 = NotificationLog(parcel_id=parcel2.id, message='Order PF20261002 created successfully.', type='Created', timestamp=parcel2.created_at)

        h3_1 = TrackingHistory(parcel_id=parcel3.id, status='Pending', location='Lagankhel', timestamp=parcel3.created_at)
        h3_2 = TrackingHistory(parcel_id=parcel3.id, status='Delivered', location='Koteshwor', timestamp=delivered_time)
        n3_1 = NotificationLog(parcel_id=parcel3.id, message='Parcel successfully delivered.', type='Delivered', timestamp=delivered_time)
        
        db.session.add_all([hist1, notif1, hist2, notif2, h3_1, h3_2, n3_1])
        db.session.commit()

        print("Database successfully initialized and seeded with comprehensive extended test records!")

if __name__ == '__main__':
    seed_database()
