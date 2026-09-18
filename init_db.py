import os
import sys
from datetime import datetime, timedelta
import random
from werkzeug.security import generate_password_hash

# Ensure root directory in path
sys.path.insert(0, r'd:\ParcelFleet')
from app import app, db
from models import (
    User, Driver, Parcel, TrackingHistory, NotificationLog, Hub, HubAdmin,
    Vehicle, VehicleMaintenance, Assignment, Manifest, ManifestItem, Merchandise,
    CustomerProfile, CustomerAddress, PricingRule, DeliverySheet, DeliverySheetItem,
    SupportTicket, TicketReply, CompanySetting
)
from algorithms import HUBS

def seed_comprehensive_data():
    with app.app_context():
        print("Resetting database schema...")
        db.drop_all()
        db.create_all()
        print("Schema recreated successfully!")

        # 1. Company Settings
        setting = CompanySetting(
            company_name="ParcelFleet Logistics Pvt. Ltd.",
            phone="01-4234567 / 9801234567",
            email="support@parcelfleet.com.np",
            address="Tripureshwor, Kathmandu, Nepal",
            vat_pan_number="609876543",
            currency="Rs.",
            terms_conditions="Standard multimodal freight and express courier terms apply. Goods subject to volumetric calculation."
        )
        db.session.add(setting)

        # 2. Users (Admin, Hub Admins, Dispatchers, Customers)
        admin_user = User(
            username='admin',
            password_hash=generate_password_hash('admin123'),
            role='admin',
            permissions='view,create,edit,delete,assign,dispatch,reports,settings'
        )
        hubadmin1_user = User(
            username='hubadmin1',
            password_hash=generate_password_hash('hub123'),
            role='hub_admin',
            permissions='view,create,edit,assign,dispatch,reports'
        )
        hubadmin2_user = User(
            username='hubadmin2',
            password_hash=generate_password_hash('hub123'),
            role='hub_admin',
            permissions='view,create,edit,assign,dispatch,reports'
        )
        dispatcher_user = User(
            username='dispatcher1',
            password_hash=generate_password_hash('dispatch123'),
            role='dispatcher',
            permissions='view,assign,dispatch'
        )
        cust1_user = User(
            username='customer1',
            password_hash=generate_password_hash('cust123'),
            role='customer',
            permissions='view,create,reports'
        )
        db.session.add_all([admin_user, hubadmin1_user, hubadmin2_user, dispatcher_user, cust1_user])
        db.session.commit()

        # 3. Seed Hubs
        seeded_hubs = {}
        for hub_name, coords in HUBS.items():
            hub = Hub(name=hub_name, latitude=coords['lat'], longitude=coords['lng'])
            db.session.add(hub)
            seeded_hubs[hub_name] = hub
        db.session.commit()
        print(f"Seeded {len(seeded_hubs)} Regional Hubs.")

        # Hub Admin Profiles
        kalanki_hub = seeded_hubs.get('Kalanki') or seeded_hubs['Kathmandu']
        chabahil_hub = seeded_hubs.get('Chabahil') or seeded_hubs['Kathmandu']
        thamel_hub = seeded_hubs.get('Thamel') or seeded_hubs['Kathmandu']
        bhaktapur_hub = seeded_hubs.get('Bhaktapur') or seeded_hubs['Kathmandu']
        lagankhel_hub = seeded_hubs.get('Lagankhel') or seeded_hubs['Kathmandu']
        baneshwor_hub = seeded_hubs.get('New Baneshwor') or seeded_hubs['Kathmandu']
        koteshwor_hub = seeded_hubs.get('Koteshwor') or seeded_hubs['Kathmandu']

        ha1 = HubAdmin(user_id=hubadmin1_user.id, name='Anup Dahal', phone='9867123456', email='anup.kalanki@parcelfleet.com', hub_id=kalanki_hub.id)
        ha2 = HubAdmin(user_id=hubadmin2_user.id, name='Saroj KC', phone='9867987654', email='saroj.thamel@parcelfleet.com', hub_id=thamel_hub.id)
        db.session.add_all([ha1, ha2])

        # 4. Customer Profile
        cp1 = CustomerProfile(
            user_id=cust1_user.id,
            company_name="Himalayan Traders Pvt Ltd",
            contact_person="Dibisha Haleyo Joshi",
            phone="9860640413",
            email="dibisha@himalayan.com",
            address="Thankot, Kathmandu",
            city="Kathmandu",
            account_type="business",
            credit_limit=50000.0,
            balance=12500.0
        )
        db.session.add(cp1)
        db.session.flush()

        ca1 = CustomerAddress(
            customer_id=cp1.id,
            label="Corporate Warehouse",
            recipient_name="Dibisha Joshi",
            phone="9860640413",
            address="Thankot Industrial Zone",
            city="Kathmandu",
            latitude=27.6946,
            longitude=85.2813,
            is_default=True
        )
        db.session.add(ca1)

        # 5. Seed Diverse Fleet of Vehicles (Bikes, Vans, Pickups, Heavy Cargo Trucks)
        vehicles_data = [
            # Bikes (Capacity: 25 - 35 kg, 0.18 - 0.25 m3)
            {'code': 'V-BIKE-01', 'plate': 'BA 2 PA 5678', 'type': 'Bike', 'w': 30.0, 'v': 0.20, 'fuel': 'Petrol', 'loc': 'Kalanki Hub', 'hub': kalanki_hub.id, 'rem': 'Rear insulated courier box.'},
            {'code': 'V-BIKE-02', 'plate': 'BA 1 PA 8822', 'type': 'Bike', 'w': 35.0, 'v': 0.25, 'fuel': 'Petrol', 'loc': 'Thamel Hub', 'hub': thamel_hub.id, 'rem': 'High mobility express city bike.'},
            {'code': 'V-BIKE-03', 'plate': 'BA 4 PA 3311', 'type': 'Bike', 'w': 30.0, 'v': 0.20, 'fuel': 'Electric', 'loc': 'Chabahil Hub', 'hub': chabahil_hub.id, 'rem': 'Zero-emission electric delivery bike.'},
            {'code': 'V-BIKE-04', 'plate': 'BA 5 PA 9900', 'type': 'Bike', 'w': 25.0, 'v': 0.18, 'fuel': 'Petrol', 'loc': 'Lagankhel Hub', 'hub': lagankhel_hub.id, 'rem': 'Compact delivery scooter.'},
            {'code': 'V-BIKE-05', 'plate': 'BA 6 PA 1122', 'type': 'Bike', 'w': 30.0, 'v': 0.20, 'fuel': 'Petrol', 'loc': 'Bhaktapur Hub', 'hub': bhaktapur_hub.id, 'rem': 'Suburban courier bike.'},

            # Vans (Capacity: 650 - 900 kg, 3.8 - 5.0 m3)
            {'code': 'V-VAN-01', 'plate': 'BA 3 CHA 1234', 'type': 'Van', 'w': 800.0, 'v': 4.50, 'fuel': 'Diesel', 'loc': 'Chabahil Hub', 'hub': chabahil_hub.id, 'rem': 'Consolidated inter-hub transit van.'},
            {'code': 'V-VAN-02', 'plate': 'BA 2 CHA 5566', 'type': 'Van', 'w': 650.0, 'v': 3.80, 'fuel': 'Diesel', 'loc': 'Kalanki Hub', 'hub': kalanki_hub.id, 'rem': 'Medium freight delivery van.'},
            {'code': 'V-VAN-03', 'plate': 'BA 1 CHA 4433', 'type': 'Van', 'w': 750.0, 'v': 4.20, 'fuel': 'Diesel', 'loc': 'Thamel Hub', 'hub': thamel_hub.id, 'rem': 'Commercial cargo van.'},
            {'code': 'V-VAN-04', 'plate': 'BA 4 CHA 7788', 'type': 'Van', 'w': 900.0, 'v': 5.00, 'fuel': 'Diesel', 'loc': 'Bhaktapur Hub', 'hub': bhaktapur_hub.id, 'rem': 'Heavy multi-carton van.'},

            # Pickups & Light Cargo (Capacity: 1200 - 1500 kg, 7.5 - 9.0 m3)
            {'code': 'V-PICKUP-01', 'plate': 'BA 1 KHA 3322', 'type': 'Pickup', 'w': 1500.0, 'v': 9.00, 'fuel': 'Diesel', 'loc': 'Lagankhel Hub', 'hub': lagankhel_hub.id, 'rem': 'Heavy goods open-deck pickup.'},
            {'code': 'V-PICKUP-02', 'plate': 'BA 2 KHA 6611', 'type': 'Pickup', 'w': 1200.0, 'v': 7.50, 'fuel': 'Diesel', 'loc': 'Koteshwor Hub', 'hub': koteshwor_hub.id, 'rem': 'Regional transfer pickup.'},

            # Heavy Freight Trucks (Capacity: 4000 - 5000 kg, 22.0 - 28.0 m3)
            {'code': 'V-TRUCK-01', 'plate': 'BA 1 CHA 9988', 'type': 'Truck', 'w': 4000.0, 'v': 22.00, 'fuel': 'Diesel', 'loc': 'Kalanki Freight Depot', 'hub': kalanki_hub.id, 'rem': 'Long-haul inter-city cargo carrier.'},
            {'code': 'V-TRUCK-02', 'plate': 'BA 3 KHA 8800', 'type': 'Truck', 'w': 5000.0, 'v': 28.00, 'fuel': 'Diesel', 'loc': 'Central Cargo Depot', 'hub': kalanki_hub.id, 'rem': 'High-tonnage container truck.'}
        ]

        seeded_vehicles = {}
        for vd in vehicles_data:
            veh = Vehicle(
                vehicle_code=vd['code'],
                license_plate=vd['plate'],
                vehicle_type=vd['type'],
                capacity_weight=vd['w'],
                capacity_volume=vd['v'],
                fuel_type=vd['fuel'],
                current_status='Available',
                current_location=vd['loc'],
                last_service_date=datetime.utcnow() - timedelta(days=random.randint(10, 60)),
                insurance_expiry=datetime.utcnow() + timedelta(days=random.randint(90, 365)),
                remarks=vd['rem'],
                hub_id=vd['hub']
            )
            db.session.add(veh)
            seeded_vehicles[vd['code']] = veh
        db.session.commit()
        print(f"Seeded {len(seeded_vehicles)} Fleet Vehicles.")

        # 6. Seed Drivers / Couriers and User Accounts
        drivers_data = [
            {'username': 'driver1', 'name': 'Suman Thapa', 'phone': '9841234567', 'email': 'suman.driver@parcelfleet.com', 'license_type': 'Bike', 'veh': 'V-BIKE-01', 'hub': kalanki_hub.id, 'lat': 27.6946, 'lng': 85.2813, 'code': 'DRV-1001', 'rating': 4.8},
            {'username': 'driver2', 'name': 'Niranjan Shrestha', 'phone': '9801234567', 'email': 'niranjan.driver@parcelfleet.com', 'license_type': 'Van', 'veh': 'V-VAN-01', 'hub': chabahil_hub.id, 'lat': 27.7172, 'lng': 85.3444, 'code': 'DRV-1002', 'rating': 4.9},
            {'username': 'driver3', 'name': 'Ramesh Adhikari', 'phone': '9841888999', 'email': 'ramesh.driver@parcelfleet.com', 'license_type': 'Bike', 'veh': 'V-BIKE-02', 'hub': thamel_hub.id, 'lat': 27.7154, 'lng': 85.3123, 'code': 'DRV-1003', 'rating': 4.7},
            {'username': 'driver4', 'name': 'Bikash Maharjan', 'phone': '9851444555', 'email': 'bikash.driver@parcelfleet.com', 'license_type': 'Pickup', 'veh': 'V-PICKUP-01', 'hub': lagankhel_hub.id, 'lat': 27.6650, 'lng': 85.3200, 'code': 'DRV-1004', 'rating': 4.9},
            {'username': 'driver5', 'name': 'Rajesh Gurung', 'phone': '9860111222', 'email': 'rajesh.driver@parcelfleet.com', 'license_type': 'Truck', 'veh': 'V-TRUCK-01', 'hub': kalanki_hub.id, 'lat': 27.6965, 'lng': 85.2835, 'code': 'DRV-1005', 'rating': 5.0},
            {'username': 'driver6', 'name': 'Prakash Silwal', 'phone': '9841777888', 'email': 'prakash.driver@parcelfleet.com', 'license_type': 'Van', 'veh': 'V-VAN-02', 'hub': kalanki_hub.id, 'lat': 27.6980, 'lng': 85.2900, 'code': 'DRV-1006', 'rating': 4.8},
            {'username': 'driver7', 'name': 'Deepak Karki', 'phone': '9801555666', 'email': 'deepak.driver@parcelfleet.com', 'license_type': 'Bike', 'veh': 'V-BIKE-05', 'hub': bhaktapur_hub.id, 'lat': 27.6740, 'lng': 85.4300, 'code': 'DRV-1007', 'rating': 4.6},
            {'username': 'driver8', 'name': 'Sandesh Basnet', 'phone': '9849333444', 'email': 'sandesh.driver@parcelfleet.com', 'license_type': 'Van', 'veh': 'V-VAN-03', 'hub': thamel_hub.id, 'lat': 27.7200, 'lng': 85.3100, 'code': 'DRV-1008', 'rating': 4.8},
            {'username': 'driver9', 'name': 'Amit Tamang', 'phone': '9818222333', 'email': 'amit.driver@parcelfleet.com', 'license_type': 'Pickup', 'veh': 'V-PICKUP-02', 'hub': koteshwor_hub.id, 'lat': 27.6790, 'lng': 85.3505, 'code': 'DRV-1009', 'rating': 4.9},
            {'username': 'driver10', 'name': 'Roshan Shrestha', 'phone': '9841666777', 'email': 'roshan.driver@parcelfleet.com', 'license_type': 'Truck', 'veh': 'V-TRUCK-02', 'hub': kalanki_hub.id, 'lat': 27.7000, 'lng': 85.2800, 'code': 'DRV-1010', 'rating': 4.95}
        ]

        seeded_drivers = {}
        for dd in drivers_data:
            drv_user = User(
                username=dd['username'],
                password_hash=generate_password_hash('driver123'),
                role='driver',
                permissions='view,edit'
            )
            db.session.add(drv_user)
            db.session.flush()

            assigned_veh = seeded_vehicles[dd['veh']]
            drv = Driver(
                user_id=drv_user.id,
                name=dd['name'],
                phone=dd['phone'],
                email=dd['email'],
                license_type=dd['license_type'],
                vehicle_number=assigned_veh.license_plate,
                availability='Available',
                latitude=dd['lat'],
                longitude=dd['lng'],
                completed_deliveries=random.randint(15, 65),
                average_delivery_time=round(random.uniform(18.0, 28.0), 1),
                employee_code=dd['code'],
                address=f"{dd['name']} Residence, Kathmandu",
                license_number=f"LIC-{random.randint(100000, 999999)}",
                license_expiry=datetime.now() + timedelta(days=random.randint(180, 500)),
                joining_date=datetime.now() - timedelta(days=random.randint(100, 400)),
                assigned_vehicle_id=assigned_veh.id,
                emergency_contact='9841000000',
                status='Available',
                hub_id=dd['hub'],
                rating=dd['rating'],
                remarks=f"Experienced {dd['license_type']} license driver.",
                total_deliveries=random.randint(20, 80),
                successful_deliveries=random.randint(18, 75),
                failed_deliveries=random.randint(0, 5)
            )
            assert drv.can_drive_vehicle(assigned_veh), f"Driver {drv.name} ({drv.license_type}) cannot drive {assigned_veh.vehicle_type}!"
            db.session.add(drv)
            seeded_drivers[dd['username']] = drv
        db.session.commit()
        print(f"Seeded {len(seeded_drivers)} Couriers/Drivers with matched license types.")

        # 7. Seed Merchandise Categories
        merch_list = [
            Merchandise(type='Documents', category='Paperwork', description='Official contracts, passports, legal papers', weight=0.5, unit='kg', fragile=False, default_charge=100.0),
            Merchandise(type='Electronics', category='Gadgets', description='Laptops, Smartphones, Microchips', weight=2.5, unit='kg', fragile=True, default_charge=250.0),
            Merchandise(type='Medical Supplies', category='Healthcare', description='Therapeutic vaccines, diagnostics, meds', weight=1.5, unit='kg', fragile=True, temperature_controlled=True, default_charge=200.0),
            Merchandise(type='Clothing & Apparel', category='Textiles', description='Garments, footwear, designer apparel', weight=3.0, unit='kg', fragile=False, default_charge=140.0),
            Merchandise(type='Industrial Hardware', category='Heavy Machinery', description='Machine replacement components, tools', weight=45.0, unit='kg', fragile=False, default_charge=850.0),
            Merchandise(type='Fragile Glassware', category='Ceramics', description='Porcelain, luxury crystalware', weight=4.0, unit='kg', fragile=True, default_charge=300.0),
            Merchandise(type='Commercial Freight', category='Bulk Goods', description='Wholesale packaged FMCG items', weight=150.0, unit='kg', fragile=False, default_charge=1800.0)
        ]
        db.session.add_all(merch_list)
        db.session.commit()

        # 8. Seed Pricing Rules
        p_rules = [
            PricingRule(service_type='Standard', base_weight_kg=1.0, base_rate=120.0, extra_kg_rate=35.0, delivery_time_hours=24, is_active=True),
            PricingRule(service_type='Express', base_weight_kg=1.0, base_rate=180.0, extra_kg_rate=45.0, delivery_time_hours=12, is_active=True),
            PricingRule(service_type='Air Cargo', base_weight_kg=1.0, base_rate=250.0, extra_kg_rate=60.0, delivery_time_hours=8, is_active=True),
            PricingRule(service_type='Surface', base_weight_kg=5.0, base_rate=300.0, extra_kg_rate=25.0, delivery_time_hours=48, is_active=True)
        ]
        db.session.add_all(p_rules)
        db.session.commit()

        # 9. Seed 25 Extensive Parcel Shipments with Diverse Specifications
        parcels_specs = [
            # Light Parcels (Documents / Small Electronics - Suitable for Bikes)
            {'id': 'PF20261001', 's_name': 'Himalayan Law Firm', 's_ph': '9841112233', 'r_name': 'Supreme Court Registry', 'r_ph': '9801223344', 'p_addr': 'Bhaktapur Durbar Square', 'd_addr': 'Thamel, Kathmandu', 'p_hub': 'Bhaktapur', 'd_hub': 'Thamel', 'p_lat': 27.6740, 'p_lng': 85.4300, 'd_lat': 27.7180, 'd_lng': 85.3150, 'type': 'Documents', 'w': 0.6, 'l': 15.0, 'wd': 20.0, 'h': 2.0, 'fare': 100.0, 'pay': 'Paid', 'tags': 'Confidential Documents'},
            {'id': 'PF20261002', 's_name': 'TechHub Nepal', 's_ph': '9841555666', 'r_name': 'Prashant Sharma', 'r_ph': '9818999888', 'p_addr': 'Kalanki Chowk', 'd_addr': 'Chabahil Ring Road', 'p_hub': 'Kalanki', 'd_hub': 'Chabahil', 'p_lat': 27.6965, 'p_lng': 85.2835, 'd_lat': 27.7172, 'd_lng': 85.3444, 'type': 'Electronics', 'w': 1.8, 'l': 25.0, 'wd': 18.0, 'h': 8.0, 'fare': 230.0, 'pay': 'COD', 'tags': 'Fragile,Handle With Care'},
            {'id': 'PF20261003', 's_name': 'Patan Handicrafts', 's_ph': '9851000111', 'r_name': 'Suman Shakya', 'r_ph': '9849222111', 'p_addr': 'Lagankhel Bus Park', 'd_addr': 'New Baneshwor Plaza', 'p_hub': 'Lagankhel', 'd_hub': 'New Baneshwor', 'p_lat': 27.6650, 'p_lng': 85.3200, 'd_lat': 27.6900, 'd_lng': 85.3360, 'type': 'Fragile Glassware', 'w': 3.2, 'l': 22.0, 'wd': 22.0, 'h': 18.0, 'fare': 270.0, 'pay': 'Paid', 'tags': 'Fragile'},
            {'id': 'PF20261004', 's_name': 'Apex Bank Ltd', 's_ph': '9841333222', 'r_name': 'Khadka Trade Enterprises', 'r_ph': '9801444333', 'p_addr': 'Suryabinayak, Bhaktapur', 'd_addr': 'Jyatha, Thamel', 'p_hub': 'Bhaktapur', 'd_hub': 'Thamel', 'p_lat': 27.6710, 'p_lng': 85.4250, 'd_lat': 27.7145, 'd_lng': 85.3130, 'type': 'Documents', 'w': 0.8, 'l': 18.0, 'wd': 24.0, 'h': 3.0, 'fare': 120.0, 'pay': 'Paid', 'tags': 'Express Delivery'},
            {'id': 'PF20261005', 's_name': 'Global IT Solutions', 's_ph': '9841777000', 'r_name': 'Kiran Shrestha', 'r_ph': '9801888111', 'p_addr': 'Rabi Bhawan, Kalanki', 'd_addr': 'Mitrapark, Chabahil', 'p_hub': 'Kalanki', 'd_hub': 'Chabahil', 'p_lat': 27.6980, 'p_lng': 85.2910, 'd_lat': 27.7190, 'd_lng': 85.3480, 'type': 'Electronics', 'w': 2.4, 'l': 32.0, 'wd': 24.0, 'h': 6.0, 'fare': 260.0, 'pay': 'COD', 'tags': 'Handle With Care'},
            
            # Medium Parcels (Apparel / Medical / Multi-Carton - Suitable for Vans)
            {'id': 'PF20261006', 's_name': 'Himalayan Garment Factory', 's_ph': '9841888333', 'r_name': 'Baneshwor Fashion Boutique', 'r_ph': '9801999444', 'p_addr': 'Kumaripati, Lalitpur', 'd_addr': 'Minbhawan, Baneshwor', 'p_hub': 'Lagankhel', 'd_hub': 'New Baneshwor', 'p_lat': 27.6700, 'p_lng': 85.3210, 'd_lat': 27.6880, 'd_lng': 85.3400, 'type': 'Clothing & Apparel', 'w': 18.5, 'l': 60.0, 'wd': 40.0, 'h': 35.0, 'fare': 650.0, 'pay': 'Paid', 'tags': 'Standard Freight'},
            {'id': 'PF20261007', 's_name': 'National Pathology Lab', 's_ph': '9851222999', 'r_name': 'Thamel Family Clinic', 'r_ph': '9841333888', 'p_addr': 'Kamalbinayak, Bhaktapur', 'd_addr': 'Chaksibari, Thamel', 'p_hub': 'Bhaktapur', 'd_hub': 'Thamel', 'p_lat': 27.6780, 'p_lng': 85.4350, 'd_lat': 27.7160, 'd_lng': 85.3110, 'type': 'Medical Supplies', 'w': 2.1, 'l': 20.0, 'wd': 20.0, 'h': 15.0, 'fare': 240.0, 'pay': 'Paid', 'tags': 'Temperature Sensitive,Fragile'},
            {'id': 'PF20261008', 's_name': 'Kathmandu Audio Gear', 's_ph': '9841666111', 'r_name': 'St. Xavier Sound Lab', 'r_ph': '9801777222', 'p_addr': 'Sitapaila, Kalanki', 'd_addr': 'Gaurighat, Chabahil', 'p_hub': 'Kalanki', 'd_hub': 'Chabahil', 'p_lat': 27.7050, 'p_lng': 85.2800, 'd_lat': 27.7185, 'd_lng': 85.3520, 'type': 'Electronics', 'w': 14.5, 'l': 50.0, 'wd': 40.0, 'h': 30.0, 'fare': 580.0, 'pay': 'Paid', 'tags': 'Fragile,Express Delivery'},
            {'id': 'PF20261009', 's_name': 'Heavy Diesel Spare Parts', 's_ph': '9851000888', 'r_name': 'Pokhara Transport Fleet', 'r_ph': '9841999222', 'p_addr': 'Kalanki Cargo Warehouse', 'd_addr': 'Prithvi Chowk, Pokhara', 'p_hub': 'Kalanki', 'd_hub': 'Pokhara', 'p_lat': 27.6940, 'p_lng': 85.2810, 'd_lat': 28.2096, 'd_lng': 83.9856, 'type': 'Industrial Hardware', 'w': 420.0, 'l': 120.0, 'wd': 90.0, 'h': 85.0, 'fare': 4500.0, 'pay': 'Paid', 'tags': 'Heavy Freight'},
            {'id': 'PF20261010', 's_name': 'Lalitpur Textile Exporters', 's_ph': '9841444111', 'r_name': 'Baneshwor Garment Depo', 'r_ph': '9801555222', 'p_addr': 'Patan Industrial Area', 'd_addr': 'Shankhamul Road', 'p_hub': 'Lagankhel', 'd_hub': 'New Baneshwor', 'p_lat': 27.6620, 'p_lng': 85.3240, 'd_lat': 27.6850, 'd_lng': 85.3340, 'type': 'Clothing & Apparel', 'w': 85.0, 'l': 90.0, 'wd': 70.0, 'h': 60.0, 'fare': 1250.0, 'pay': 'Paid', 'tags': 'Standard Cargo'},

            # Heavy Bulk & Multi-Carton (Suitable for Trucks & Pickups)
            {'id': 'PF20261011', 's_name': 'Bhaktapur Pottery Guild', 's_ph': '9841999111', 'r_name': 'Heritage Crafts Thamel', 'r_ph': '9801111000', 'p_addr': 'Pottery Square, Bhaktapur', 'd_addr': 'Tridevi Marg, Thamel', 'p_hub': 'Bhaktapur', 'd_hub': 'Thamel', 'p_lat': 27.6720, 'p_lng': 85.4280, 'd_lat': 27.7130, 'd_lng': 85.3140, 'type': 'Fragile Glassware', 'w': 2.3, 'l': 25.0, 'wd': 25.0, 'h': 20.0, 'fare': 250.0, 'pay': 'COD', 'tags': 'Fragile,Handle With Care'},
            {'id': 'PF20261012', 's_name': 'Kantipur Pharmaceutical Depot', 's_ph': '9851333444', 'r_name': 'Medicare Hospital Chabahil', 'r_ph': '9841444555', 'p_addr': 'Bafal, Kalanki', 'd_addr': 'Chabahil Ring Road', 'p_hub': 'Kalanki', 'd_hub': 'Chabahil', 'p_lat': 27.7010, 'p_lng': 85.2850, 'd_lat': 27.7170, 'd_lng': 85.3460, 'type': 'Medical Supplies', 'w': 48.0, 'l': 75.0, 'wd': 55.0, 'h': 45.0, 'fare': 1100.0, 'pay': 'Paid', 'tags': 'Temperature Sensitive'},
            {'id': 'PF20261013', 's_name': 'Hydro Machinery Components', 's_ph': '9851888000', 'r_name': 'Gandaki Hydropower Project', 'r_ph': '9841000555', 'p_addr': 'Kalanki Freight Yard', 'd_addr': 'Lakeside Industrial Site, Pokhara', 'p_hub': 'Kalanki', 'd_hub': 'Pokhara', 'p_lat': 27.6950, 'p_lng': 85.2820, 'd_lat': 28.2150, 'd_lng': 83.9900, 'type': 'Industrial Hardware', 'w': 580.0, 'l': 150.0, 'wd': 110.0, 'h': 95.0, 'fare': 6200.0, 'pay': 'Paid', 'tags': 'Heavy Freight'},
            {'id': 'PF20261014', 's_name': 'Patan Handicrafts Export', 's_ph': '9841222777', 'r_name': 'Baneshwor Souvenirs', 'r_ph': '9801333888', 'p_addr': 'Jawalakhel, Lalitpur', 'd_addr': 'Old Baneshwor Chowk', 'p_hub': 'Lagankhel', 'd_hub': 'New Baneshwor', 'p_lat': 27.6730, 'p_lng': 85.3180, 'd_lat': 27.6950, 'd_lng': 85.3380, 'type': 'Clothing & Apparel', 'w': 218.3, 'l': 110.0, 'wd': 85.0, 'h': 75.0, 'fare': 2400.0, 'pay': 'Paid', 'tags': 'Bulk Cargo'},
            {'id': 'PF20261015', 's_name': 'SuperTech Wholesale Hub', 's_ph': '9841555222', 'r_name': 'Pashupati Electronic Store', 'r_ph': '9801666333', 'p_addr': 'Kalanki Trade Complex', 'd_addr': 'Chabahil Chowk', 'p_hub': 'Kalanki', 'd_hub': 'Chabahil', 'p_lat': 27.6970, 'p_lng': 85.2840, 'd_lat': 27.7175, 'd_lng': 85.3450, 'type': 'Electronics', 'w': 62.0, 'l': 80.0, 'wd': 60.0, 'h': 50.0, 'fare': 1350.0, 'pay': 'COD', 'tags': 'Fragile,High Value'},
            
            # Additional Heavy and Regional Shipments
            {'id': 'PF20261016', 's_name': 'Universal Steel & Fasteners', 's_ph': '9851666777', 'r_name': 'Western Engineering Works', 'r_ph': '9841777888', 'p_addr': 'Kalanki Central Depot', 'd_addr': 'Pokhara Industrial Estate', 'p_hub': 'Kalanki', 'd_hub': 'Pokhara', 'p_lat': 27.6955, 'p_lng': 85.2825, 'd_lat': 28.2120, 'd_lng': 83.9870, 'type': 'Industrial Hardware', 'w': 350.0, 'l': 100.0, 'wd': 80.0, 'h': 70.0, 'fare': 3800.0, 'pay': 'Paid', 'tags': 'Heavy Freight'},
            {'id': 'PF20261017', 's_name': 'Kathmandu Organic Tea', 's_ph': '9841999555', 'r_name': 'Thamel Himalayan Mart', 'r_ph': '9801222666', 'p_addr': 'Baluwatar, Kathmandu', 'd_addr': 'Thamel Marg', 'p_hub': 'Thamel', 'd_hub': 'Thamel', 'p_lat': 27.7250, 'p_lng': 85.3300, 'd_lat': 27.7150, 'd_lng': 85.3120, 'type': 'Commercial Freight', 'w': 12.0, 'l': 40.0, 'wd': 30.0, 'h': 25.0, 'fare': 320.0, 'pay': 'Paid', 'tags': 'Standard'},
            {'id': 'PF20261018', 's_name': 'Everest Solar Panels', 's_ph': '9851444999', 'r_name': 'Green Energy Chabahil', 'r_ph': '9841555000', 'p_addr': 'Kalanki Ring Road', 'd_addr': 'Chabahil Bhatbhateni', 'p_hub': 'Kalanki', 'd_hub': 'Chabahil', 'p_lat': 27.6960, 'p_lng': 85.2830, 'd_lat': 27.7180, 'd_lng': 85.3440, 'type': 'Electronics', 'w': 10.8, 'l': 120.0, 'wd': 65.0, 'h': 12.0, 'fare': 450.0, 'pay': 'Paid', 'tags': 'Fragile,Handle With Care'},
            {'id': 'PF20261019', 's_name': 'Patan Silver Jewelry', 's_ph': '9841333777', 'r_name': 'Thamel Gem Vault', 'r_ph': '9801444888', 'p_addr': 'Mangalbazar, Lalitpur', 'd_addr': 'Z-Street, Thamel', 'p_hub': 'Lagankhel', 'd_hub': 'Thamel', 'p_lat': 27.6725, 'p_lng': 85.3250, 'd_lat': 27.7165, 'd_lng': 85.3115, 'type': 'Fragile Glassware', 'w': 1.5, 'l': 20.0, 'wd': 15.0, 'h': 10.0, 'fare': 220.0, 'pay': 'Paid', 'tags': 'High Value,Insured'},
            {'id': 'PF20261020', 's_name': 'Nepal Paper Mill Wholesale', 's_ph': '9851999333', 'r_name': 'Pokhara Book House', 'r_ph': '9841888444', 'p_addr': 'Kalanki Transit Station', 'd_addr': 'Mahendrapool, Pokhara', 'p_hub': 'Kalanki', 'd_hub': 'Pokhara', 'p_lat': 27.6945, 'p_lng': 85.2815, 'd_lat': 28.2180, 'd_lng': 83.9920, 'type': 'Commercial Freight', 'w': 280.0, 'l': 95.0, 'wd': 75.0, 'h': 65.0, 'fare': 2950.0, 'pay': 'Paid', 'tags': 'Bulk Cargo'},
            {'id': 'PF20261021', 's_name': 'Smart Health Diagnostic', 's_ph': '9841777444', 'r_name': 'Koteshwor Polyclinic', 'r_ph': '9801888555', 'p_addr': 'Baneshwor Chowk', 'd_addr': 'Koteshwor Mahadevsthan', 'p_hub': 'New Baneshwor', 'd_hub': 'Koteshwor', 'p_lat': 27.6910, 'p_lng': 85.3350, 'd_lat': 27.6795, 'd_lng': 85.3510, 'type': 'Medical Supplies', 'w': 3.5, 'l': 25.0, 'wd': 20.0, 'h': 15.0, 'fare': 210.0, 'pay': 'COD', 'tags': 'Temperature Sensitive'},
            {'id': 'PF20261022', 's_name': 'Apex Industrial Pumps', 's_ph': '9851777222', 'r_name': 'Annapurna Irrigation Co', 'r_ph': '9841666333', 'p_addr': 'Kalanki Cargo Depot', 'd_addr': 'Nayabazar, Pokhara', 'p_hub': 'Kalanki', 'd_hub': 'Pokhara', 'p_lat': 27.6952, 'p_lng': 85.2822, 'd_lat': 28.2140, 'd_lng': 83.9880, 'type': 'Industrial Hardware', 'w': 220.0, 'l': 85.0, 'wd': 70.0, 'h': 60.0, 'fare': 2500.0, 'pay': 'Paid', 'tags': 'Heavy Freight'},
            {'id': 'PF20261023', 's_name': 'Chabahil Organic Spices', 's_ph': '9841111888', 'r_name': 'Bhakta Bahadur Store', 'r_ph': '9801222999', 'p_addr': 'Chabahil Chowk', 'd_addr': 'Gongabu Bus Terminal', 'p_hub': 'Chabahil', 'd_hub': 'Kalanki', 'p_lat': 27.7170, 'p_lng': 85.3440, 'd_lat': 27.7300, 'd_lng': 85.3100, 'type': 'Commercial Freight', 'w': 15.0, 'l': 45.0, 'wd': 35.0, 'h': 25.0, 'fare': 380.0, 'pay': 'COD', 'tags': 'Standard Cargo'},
            {'id': 'PF20261024', 's_name': 'Koteshwor Agro Tools', 's_ph': '9841555777', 'r_name': 'Patan Green Farms', 'r_ph': '9801666888', 'p_addr': 'Koteshwor Chowk', 'd_addr': 'Lagankhel Garden', 'p_hub': 'Koteshwor', 'd_hub': 'Lagankhel', 'p_lat': 27.6790, 'p_lng': 85.3505, 'd_lat': 27.6650, 'd_lng': 85.3200, 'type': 'Industrial Hardware', 'w': 18.0, 'l': 55.0, 'wd': 40.0, 'h': 30.0, 'fare': 420.0, 'pay': 'Paid', 'tags': 'Standard Freight'},
            {'id': 'PF20261025', 's_name': 'Kathmandu Books & Media', 's_ph': '9841222444', 'r_name': 'Thamel Reader Club', 'r_ph': '9801333555', 'p_addr': 'Bagbazar, Kathmandu', 'd_addr': 'Thamel Marg', 'p_hub': 'Thamel', 'd_hub': 'Thamel', 'p_lat': 27.7050, 'p_lng': 85.3180, 'd_lat': 27.7155, 'd_lng': 85.3125, 'type': 'Documents', 'w': 4.2, 'l': 30.0, 'wd': 22.0, 'h': 15.0, 'fare': 180.0, 'pay': 'Paid', 'tags': 'Standard Delivery'}
        ]

        seeded_parcels = {}
        for ps in parcels_specs:
            p_hub_obj = seeded_hubs.get(ps['p_hub'])
            d_hub_obj = seeded_hubs.get(ps['d_hub'])
            
            parcel = Parcel(
                tracking_id=ps['id'],
                sender_name=ps['s_name'],
                sender_phone=ps['s_ph'],
                receiver_name=ps['r_name'],
                receiver_phone=ps['r_ph'],
                pickup_address=ps['p_addr'],
                delivery_address=ps['d_addr'],
                pickup_latitude=ps['p_lat'],
                pickup_longitude=ps['p_lng'],
                delivery_latitude=ps['d_lat'],
                delivery_longitude=ps['d_lng'],
                pickup_hub=ps['p_hub'],
                delivery_hub=ps['d_hub'],
                parcel_type=ps['type'],
                service_type='Express' if 'Express' in ps['tags'] else 'Standard',
                weight=ps['w'],
                length=ps['l'],
                width=ps['wd'],
                height=ps['h'],
                status='Pending',
                delivery_charge=ps['fare'],
                payment_status=ps['pay'],
                special_tags=ps['tags'],
                hub_id=p_hub_obj.id if p_hub_obj else None,
                created_at=datetime.utcnow() - timedelta(hours=random.randint(2, 24))
            )
            db.session.add(parcel)
            seeded_parcels[ps['id']] = parcel
        db.session.commit()
        print(f"Seeded {len(seeded_parcels)} Couriers/Parcels.")

        # 10. GROUP COURIERS INTO MANIFESTS & ASSIGN DRIVERS ACCORDING TO VEHICLE CAPACITY
        print("\n--- Grouping Couriers to Manifests & Assigning Drivers by Vehicle Capacity ---")

        # -------------------------------------------------------------
        # MANIFEST 1: Light / Express Inter-Hub Courier Batch (Bhaktapur -> Thamel)
        # Packages: PF20261001, PF20261004, PF20261007, PF20261011 (Documents & Fragile Crafts)
        # Total Weight: 5.8 kg, Volume: ~0.038 m3
        # Vehicle: V-BIKE-01 (Bike, Capacity: 30.0 kg, 0.20 m3) -> Driver: Suman Thapa (driver1)
        # -------------------------------------------------------------
        m1_parcel_ids = ['PF20261001', 'PF20261004', 'PF20261007', 'PF20261011']
        m1_parcels = [seeded_parcels[pid] for pid in m1_parcel_ids]
        m1_total_weight = sum(p.weight for p in m1_parcels)
        m1_total_vol = sum(p.volume_m3 for p in m1_parcels)

        driver1 = seeded_drivers['driver1']
        veh1 = seeded_vehicles['V-BIKE-01']

        assert m1_total_weight <= veh1.capacity_weight, f"Capacity exceeded! {m1_total_weight} > {veh1.capacity_weight}"
        assert m1_total_vol <= veh1.capacity_volume, f"Volume exceeded! {m1_total_vol} > {veh1.capacity_volume}"

        manifest1 = Manifest(
            manifest_number='MNF-2026-101',
            route='Bhaktapur Hub -> Thamel Hub Express',
            origin_hub_id=bhaktapur_hub.id,
            destination_hub_id=thamel_hub.id,
            assigned_driver_id=driver1.id,
            assigned_vehicle_id=veh1.id,
            total_parcels=len(m1_parcels),
            total_weight=round(m1_total_weight, 2),
            dispatch_date=datetime.utcnow() - timedelta(minutes=35),
            manifest_status='Dispatched',
            hub_id=bhaktapur_hub.id,
            created_at=datetime.utcnow() - timedelta(hours=2)
        )
        db.session.add(manifest1)
        db.session.flush()

        for p in m1_parcels:
            mi = ManifestItem(manifest_id=manifest1.id, parcel_id=p.id)
            p.manifest_id = manifest1.id
            p.status = 'In Transit'
            db.session.add(mi)
            hist = TrackingHistory(parcel_id=p.id, status='In Transit', location=f"In Transit on Manifest {manifest1.manifest_number} with Courier {driver1.name} ({veh1.vehicle_code})")
            db.session.add(hist)

        driver1.availability = 'On Delivery'
        veh1.current_status = 'Delivering'
        
        asgn1 = Assignment(
            manifest_id=manifest1.id,
            driver_id=driver1.id,
            vehicle_id=veh1.id,
            assigned_date=datetime.utcnow() - timedelta(minutes=35),
            dispatch_time=datetime.utcnow() - timedelta(minutes=35),
            expected_return=datetime.utcnow() + timedelta(hours=2),
            assignment_status='Active',
            hub_id=bhaktapur_hub.id
        )
        db.session.add(asgn1)
        print(f"Manifest 1 Created: {manifest1.manifest_number} (Weight: {manifest1.total_weight} kg / {veh1.capacity_weight} kg) -> Assigned to {driver1.name} on {veh1.vehicle_type} ({veh1.license_plate})")

        # -------------------------------------------------------------
        # MANIFEST 2: Medium Consolidated Commercial Van Batch (Kalanki -> Chabahil)
        # Packages: PF20261002, PF20261005, PF20261008, PF20261012, PF20261015, PF20261018 (Electronics & Meds)
        # Total Weight: 142.5 kg, Volume: ~1.18 m3
        # Vehicle: V-VAN-01 (Van, Capacity: 800.0 kg, 4.50 m3) -> Driver: Niranjan Shrestha (driver2)
        # -------------------------------------------------------------
        m2_parcel_ids = ['PF20261002', 'PF20261005', 'PF20261008', 'PF20261012', 'PF20261015', 'PF20261018']
        m2_parcels = [seeded_parcels[pid] for pid in m2_parcel_ids]
        m2_total_weight = sum(p.weight for p in m2_parcels)
        m2_total_vol = sum(p.volume_m3 for p in m2_parcels)

        driver2 = seeded_drivers['driver2']
        veh2 = seeded_vehicles['V-VAN-01']

        assert m2_total_weight <= veh2.capacity_weight, f"Capacity exceeded! {m2_total_weight} > {veh2.capacity_weight}"
        assert m2_total_vol <= veh2.capacity_volume, f"Volume exceeded! {m2_total_vol} > {veh2.capacity_volume}"

        manifest2 = Manifest(
            manifest_number='MNF-2026-102',
            route='Kalanki Hub -> Chabahil Hub Transshipment',
            origin_hub_id=kalanki_hub.id,
            destination_hub_id=chabahil_hub.id,
            assigned_driver_id=driver2.id,
            assigned_vehicle_id=veh2.id,
            total_parcels=len(m2_parcels),
            total_weight=round(m2_total_weight, 2),
            manifest_status='Created',
            hub_id=kalanki_hub.id,
            created_at=datetime.utcnow() - timedelta(hours=1)
        )
        db.session.add(manifest2)
        db.session.flush()

        for p in m2_parcels:
            mi = ManifestItem(manifest_id=manifest2.id, parcel_id=p.id)
            p.manifest_id = manifest2.id
            p.status = 'Manifested'
            db.session.add(mi)
            hist = TrackingHistory(parcel_id=p.id, status='Manifested', location=f"Bundled in Manifest {manifest2.manifest_number} (Van Batch: {veh2.vehicle_code})")
            db.session.add(hist)

        asgn2 = Assignment(
            manifest_id=manifest2.id,
            driver_id=driver2.id,
            vehicle_id=veh2.id,
            assigned_date=datetime.utcnow() - timedelta(hours=1),
            assignment_status='Active',
            hub_id=kalanki_hub.id
        )
        db.session.add(asgn2)
        print(f"Manifest 2 Created: {manifest2.manifest_number} (Weight: {manifest2.total_weight} kg / {veh2.capacity_weight} kg) -> Assigned to {driver2.name} on {veh2.vehicle_type} ({veh2.license_plate})")

        # -------------------------------------------------------------
        # MANIFEST 3: Heavy Freight Inter-City Cargo Batch (Kalanki -> Pokhara)
        # Packages: PF20261009, PF20261013, PF20261016, PF20261020, PF20261022 (Heavy Machinery & Industrial Tools)
        # Total Weight: 1,850.0 kg, Volume: ~11.45 m3
        # Vehicle: V-TRUCK-01 (Truck, Capacity: 4000.0 kg, 22.00 m3) -> Driver: Rajesh Gurung (driver5)
        # -------------------------------------------------------------
        gongabu_hub = seeded_hubs['Gongabu']
        m3_parcel_ids = ['PF20261009', 'PF20261013', 'PF20261016', 'PF20261020', 'PF20261022']
        m3_parcels = [seeded_parcels[pid] for pid in m3_parcel_ids]
        m3_total_weight = sum(p.weight for p in m3_parcels)
        m3_total_vol = sum(p.volume_m3 for p in m3_parcels)

        driver5 = seeded_drivers['driver5']
        veh3 = seeded_vehicles['V-TRUCK-01']

        assert m3_total_weight <= veh3.capacity_weight, f"Capacity exceeded! {m3_total_weight} > {veh3.capacity_weight}"
        assert m3_total_vol <= veh3.capacity_volume, f"Volume exceeded! {m3_total_vol} > {veh3.capacity_volume}"

        manifest3 = Manifest(
            manifest_number='MNF-2026-103',
            route='Kalanki Central -> Gongabu Cargo Terminal',
            origin_hub_id=kalanki_hub.id,
            destination_hub_id=gongabu_hub.id,
            assigned_driver_id=driver5.id,
            assigned_vehicle_id=veh3.id,
            total_parcels=len(m3_parcels),
            total_weight=round(m3_total_weight, 2),
            dispatch_date=datetime.utcnow() - timedelta(hours=2),
            manifest_status='Dispatched',
            hub_id=kalanki_hub.id,
            created_at=datetime.utcnow() - timedelta(hours=4)
        )
        db.session.add(manifest3)
        db.session.flush()

        for p in m3_parcels:
            mi = ManifestItem(manifest_id=manifest3.id, parcel_id=p.id)
            p.manifest_id = manifest3.id
            p.status = 'In Transit'
            db.session.add(mi)
            hist = TrackingHistory(parcel_id=p.id, status='In Transit', location=f"Inter-city Highway Freight on Manifest {manifest3.manifest_number} (Heavy Truck {veh3.license_plate})")
            db.session.add(hist)

        driver5.availability = 'On Delivery'
        veh3.current_status = 'Delivering'
        
        asgn3 = Assignment(
            manifest_id=manifest3.id,
            driver_id=driver5.id,
            vehicle_id=veh3.id,
            assigned_date=datetime.utcnow() - timedelta(hours=2),
            dispatch_time=datetime.utcnow() - timedelta(hours=2),
            expected_return=datetime.utcnow() + timedelta(hours=8),
            assignment_status='Active',
            hub_id=kalanki_hub.id
        )
        db.session.add(asgn3)
        print(f"Manifest 3 Created: {manifest3.manifest_number} (Weight: {manifest3.total_weight} kg / {veh3.capacity_weight} kg) -> Assigned to {driver5.name} on {veh3.vehicle_type} ({veh3.license_plate})")

        # -------------------------------------------------------------
        # MANIFEST 4: South Valley Regional Batch (Lagankhel -> New Baneshwor)
        # Packages: PF20261003, PF20261006, PF20261010, PF20261014 (Handicrafts & Apparel)
        # Total Weight: 325.0 kg, Volume: ~2.65 m3
        # Vehicle: V-PICKUP-01 (Pickup, Capacity: 1500.0 kg, 9.00 m3) -> Driver: Bikash Maharjan (driver4)
        # -------------------------------------------------------------
        m4_parcel_ids = ['PF20261003', 'PF20261006', 'PF20261010', 'PF20261014']
        m4_parcels = [seeded_parcels[pid] for pid in m4_parcel_ids]
        m4_total_weight = sum(p.weight for p in m4_parcels)
        m4_total_vol = sum(p.volume_m3 for p in m4_parcels)

        driver4 = seeded_drivers['driver4']
        veh4 = seeded_vehicles['V-PICKUP-01']

        assert m4_total_weight <= veh4.capacity_weight, f"Capacity exceeded! {m4_total_weight} > {veh4.capacity_weight}"
        assert m4_total_vol <= veh4.capacity_volume, f"Volume exceeded! {m4_total_vol} > {veh4.capacity_volume}"

        manifest4 = Manifest(
            manifest_number='MNF-2026-104',
            route='Lagankhel Hub -> New Baneshwor Hub',
            origin_hub_id=lagankhel_hub.id,
            destination_hub_id=baneshwor_hub.id,
            assigned_driver_id=driver4.id,
            assigned_vehicle_id=veh4.id,
            total_parcels=len(m4_parcels),
            total_weight=round(m4_total_weight, 2),
            dispatch_date=datetime.utcnow() - timedelta(hours=3),
            arrival_date=datetime.utcnow() - timedelta(minutes=20),
            manifest_status='Completed',
            hub_id=lagankhel_hub.id,
            created_at=datetime.utcnow() - timedelta(hours=5)
        )
        db.session.add(manifest4)
        db.session.flush()

        for p in m4_parcels:
            mi = ManifestItem(manifest_id=manifest4.id, parcel_id=p.id)
            p.manifest_id = manifest4.id
            p.status = 'Delivered'
            p.delivered_at = datetime.utcnow() - timedelta(minutes=20)
            db.session.add(mi)
            hist = TrackingHistory(parcel_id=p.id, status='Delivered', location=f"Delivered via Manifest {manifest4.manifest_number} (Courier: {driver4.name})")
            db.session.add(hist)

        driver4.availability = 'Available'
        veh4.current_status = 'Available'

        asgn4 = Assignment(
            manifest_id=manifest4.id,
            driver_id=driver4.id,
            vehicle_id=veh4.id,
            assigned_date=datetime.utcnow() - timedelta(hours=3),
            dispatch_time=datetime.utcnow() - timedelta(hours=3),
            actual_return=datetime.utcnow() - timedelta(minutes=20),
            assignment_status='Returned',
            hub_id=lagankhel_hub.id
        )
        db.session.add(asgn4)
        print(f"Manifest 4 Created: {manifest4.manifest_number} (Weight: {manifest4.total_weight} kg / {veh4.capacity_weight} kg) -> Assigned to {driver4.name} on {veh4.vehicle_type} ({veh4.license_plate})")

        # 11. Maintenance Records
        maint1 = VehicleMaintenance(
            vehicle_id=veh3.id,
            maintenance_type='Routine Inspection',
            description='Brake pads check, pneumatic tyre pressure and chassis lubrication.',
            service_date=datetime.utcnow() - timedelta(days=5),
            next_service_date=datetime.utcnow() + timedelta(days=45),
            cost=6500.0,
            workshop='Kalanki Central Garage',
            status='Completed',
            hub_id=kalanki_hub.id
        )
        db.session.add(maint1)

        db.session.commit()
        print("\nSUCCESS! Comprehensive fleet, driver, courier, and manifest dataset seeded with strict vehicle capacity enforcement!")

if __name__ == '__main__':
    seed_comprehensive_data()
