"""
============================================================
  Sanjeevani.AI – Every Second Saves a Life
  Main Application File (app.py)
  
  This is the entry point of the Flask web application.
  It contains:
    - Database initialization
    - REST API endpoints
    - Route optimization logic
    - SMS alert system (mock)
    - Page rendering routes
============================================================
"""

# ── Import Required Libraries ──────────────────────────────
from flask import Flask, render_template, request, jsonify, redirect, url_for, send_from_directory
from models import db, EmergencyRequest, Ambulance, Hospital, SMSLog
from datetime import datetime
import math
import random
import json
import os

# ── Get the base directory (where app.py lives) ───────────
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# ── Initialize Flask App ───────────────────────────────────
app = Flask(__name__, instance_path=os.path.join(BASE_DIR, 'instance'))

# Configure SQLite database (absolute path to avoid permission errors)
db_path = os.path.join(BASE_DIR, 'instance', 'sanjeevani.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'sanjeevani-secret-key-2026'

# Initialize database with the app
db.init_app(app)


# ============================================================
#  UTILITY FUNCTIONS
# ============================================================

def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the distance (in km) between two GPS coordinates
    using the Haversine formula.
    
    This is a well-known formula for calculating the shortest 
    distance between two points on a sphere (Earth).
    
    Parameters:
        lat1, lon1 – Latitude & Longitude of point 1
        lat2, lon2 – Latitude & Longitude of point 2
    
    Returns:
        Distance in kilometers (float)
    """
    R = 6371  # Radius of Earth in kilometers

    # Convert degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))

    return R * c


def calculate_eta(distance_km):
    """
    Calculate Estimated Time of Arrival (ETA) based on distance.
    
    Assumes an average ambulance speed of 40 km/h in city traffic.
    
    Parameters:
        distance_km – Distance in kilometers
    
    Returns:
        ETA in minutes (int)
    """
    avg_speed_kmh = 40  # Average speed for ambulance in city
    time_hours = distance_km / avg_speed_kmh
    time_minutes = max(1, int(time_hours * 60))  # At least 1 minute
    return time_minutes


def find_nearest_ambulance(patient_lat, patient_lon):
    """
    Find the nearest AVAILABLE ambulance to the patient location.
    
    Steps:
        1. Query all ambulances with status 'Available'
        2. Calculate distance from each to the patient
        3. Return the closest one
    
    Parameters:
        patient_lat – Patient's latitude
        patient_lon – Patient's longitude
    
    Returns:
        Tuple of (ambulance_object, distance_km) or (None, None)
    """
    available_ambulances = Ambulance.query.filter_by(status='Available').all()

    if not available_ambulances:
        return None, None

    nearest = None
    min_distance = float('inf')

    for ambulance in available_ambulances:
        dist = haversine_distance(
            patient_lat, patient_lon,
            ambulance.latitude, ambulance.longitude
        )
        if dist < min_distance:
            min_distance = dist
            nearest = ambulance

    return nearest, min_distance


def find_nearest_hospital(patient_lat, patient_lon):
    """
    Find the nearest hospital to the patient's location.
    
    Parameters:
        patient_lat – Patient's latitude
        patient_lon – Patient's longitude
    
    Returns:
        Tuple of (hospital_object, distance_km) or (None, None)
    """
    hospitals = Hospital.query.all()

    if not hospitals:
        return None, None

    nearest = None
    min_distance = float('inf')

    for hospital in hospitals:
        dist = haversine_distance(
            patient_lat, patient_lon,
            hospital.latitude, hospital.longitude
        )
        if dist < min_distance:
            min_distance = dist
            nearest = hospital

    return nearest, min_distance


def send_mock_sms(phone_number, message):
    """
    Mock SMS sending function.
    
    In a production environment, this would integrate with
    a real SMS API like Twilio or Fast2SMS.
    
    For this project, we simulate SMS by logging it to the database.
    
    Parameters:
        phone_number – Recipient's phone number
        message      – SMS content
    
    Returns:
        True (always succeeds in mock mode)
    """
    # Create SMS log entry in database
    sms_log = SMSLog(
        phone_number=phone_number,
        message=message,
        status='Sent (Mock)',
        sent_at=datetime.utcnow()
    )
    db.session.add(sms_log)
    db.session.commit()

    # Print to console for debugging
    print(f"\n{'='*50}")
    print(f"[SMS] MOCK SMS SENT")
    print(f"To: {phone_number}")
    print(f"Message: {message}")
    print(f"{'='*50}\n")

    return True


# ============================================================
#  PAGE ROUTES (Render HTML templates)
# ============================================================

@app.route('/')
def home():
    """Render the Home Page with the emergency request form."""
    return render_template('index.html')


@app.route('/admin')
def admin_dashboard():
    """
    Render the Admin Dashboard page.
    Fetches all emergency requests and ambulance data.
    """
    requests_list = EmergencyRequest.query.order_by(
        EmergencyRequest.created_at.desc()
    ).all()
    ambulances = Ambulance.query.all()
    hospitals = Hospital.query.all()
    sms_logs = SMSLog.query.order_by(SMSLog.sent_at.desc()).limit(20).all()

    return render_template(
        'admin.html',
        requests=requests_list,
        ambulances=ambulances,
        hospitals=hospitals,
        sms_logs=sms_logs
    )


# ── PWA Routes (Service Worker & Manifest) ─────────────────
@app.route('/sw.js')
def service_worker():
    """Serve the service worker from root scope."""
    return send_from_directory(app.static_folder, 'sw.js',
                               mimetype='application/javascript')

@app.route('/manifest.json')
def manifest():
    """Serve the PWA manifest from root."""
    return send_from_directory(app.static_folder, 'manifest.json',
                               mimetype='application/manifest+json')


# ============================================================
#  REST API ENDPOINTS
# ============================================================

@app.route('/request-ambulance', methods=['POST'])
def request_ambulance():
    """
    API Endpoint: /request-ambulance
    Method: POST
    
    Handles a new emergency ambulance request.
    
    Expected JSON body:
    {
        "patient_name": "John Doe",
        "contact_number": "9876543210",
        "emergency_type": "Cardiac Arrest",
        "latitude": 28.6139,
        "longitude": 77.2090,
        "address": "Connaught Place, New Delhi"
    }
    
    Process:
        1. Validate input data
        2. Find nearest available ambulance
        3. Find nearest hospital
        4. Calculate ETA
        5. Save request to database
        6. Send SMS alerts
        7. Return confirmation with details
    """
    try:
        # Step 1: Get data from the request
        data = request.get_json()

        # Validate required fields
        required_fields = ['patient_name', 'contact_number', 'emergency_type', 'latitude', 'longitude']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({
                    'success': False,
                    'error': f'Missing required field: {field}'
                }), 400

        patient_name = data['patient_name']
        contact_number = data['contact_number']
        emergency_type = data['emergency_type']
        patient_lat = float(data['latitude'])
        patient_lon = float(data['longitude'])
        address = data.get('address', 'Not provided')

        # Step 2: Find nearest available ambulance
        nearest_amb, amb_distance = find_nearest_ambulance(patient_lat, patient_lon)

        if not nearest_amb:
            return jsonify({
                'success': False,
                'error': 'No ambulances currently available. Please try again.'
            }), 503

        # Step 3: Find nearest hospital
        nearest_hosp, hosp_distance = find_nearest_hospital(patient_lat, patient_lon)

        # Step 4: Calculate ETA
        eta_minutes = calculate_eta(amb_distance)

        # Step 5: Save emergency request to database
        emergency = EmergencyRequest(
            patient_name=patient_name,
            contact_number=contact_number,
            emergency_type=emergency_type,
            latitude=patient_lat,
            longitude=patient_lon,
            address=address,
            assigned_ambulance_id=nearest_amb.id,
            assigned_hospital_id=nearest_hosp.id if nearest_hosp else None,
            eta_minutes=eta_minutes,
            distance_km=round(amb_distance, 2),
            status='Dispatched',
            created_at=datetime.utcnow()
        )
        db.session.add(emergency)

        # Update ambulance status to 'Busy'
        nearest_amb.status = 'Busy'
        db.session.commit()

        # Step 6: Send SMS alerts
        # SMS to emergency contact
        sms_patient = (
            f"SANJEEVANI.AI ALERT: Ambulance {nearest_amb.vehicle_number} "
            f"has been dispatched for {patient_name}. "
            f"ETA: {eta_minutes} minutes. "
            f"Hospital: {nearest_hosp.name if nearest_hosp else 'N/A'}. "
            f"Stay calm, help is on the way!"
        )
        send_mock_sms(contact_number, sms_patient)

        # SMS to hospital
        if nearest_hosp:
            sms_hospital = (
                f"INCOMING PATIENT ALERT: {patient_name}, "
                f"Emergency: {emergency_type}. "
                f"Ambulance: {nearest_amb.vehicle_number}. "
                f"ETA: {eta_minutes} min. "
                f"Please prepare for arrival."
            )
            send_mock_sms(nearest_hosp.phone, sms_hospital)

        # Step 7: Return success response
        return jsonify({
            'success': True,
            'message': 'Ambulance dispatched successfully!',
            'data': {
                'request_id': emergency.id,
                'patient_name': patient_name,
                'ambulance': {
                    'id': nearest_amb.id,
                    'vehicle_number': nearest_amb.vehicle_number,
                    'driver_name': nearest_amb.driver_name,
                    'driver_phone': nearest_amb.driver_phone,
                    'latitude': nearest_amb.latitude,
                    'longitude': nearest_amb.longitude
                },
                'hospital': {
                    'name': nearest_hosp.name if nearest_hosp else 'N/A',
                    'address': nearest_hosp.address if nearest_hosp else 'N/A',
                    'phone': nearest_hosp.phone if nearest_hosp else 'N/A',
                    'latitude': nearest_hosp.latitude if nearest_hosp else None,
                    'longitude': nearest_hosp.longitude if nearest_hosp else None
                },
                'eta_minutes': eta_minutes,
                'distance_km': round(amb_distance, 2),
                'status': 'Dispatched'
            }
        }), 200

    except Exception as e:
        # Handle any unexpected errors
        return jsonify({
            'success': False,
            'error': f'An error occurred: {str(e)}'
        }), 500


@app.route('/ambulance-status', methods=['GET'])
def ambulance_status():
    """
    API Endpoint: /ambulance-status
    Method: GET
    
    Returns the current status of all ambulances.
    
    Optional query parameter:
        ?id=1  →  Get status of a specific ambulance
    """
    try:
        ambulance_id = request.args.get('id')

        if ambulance_id:
            # Get specific ambulance
            ambulance = Ambulance.query.get(ambulance_id)
            if not ambulance:
                return jsonify({
                    'success': False,
                    'error': 'Ambulance not found'
                }), 404

            return jsonify({
                'success': True,
                'data': {
                    'id': ambulance.id,
                    'vehicle_number': ambulance.vehicle_number,
                    'driver_name': ambulance.driver_name,
                    'driver_phone': ambulance.driver_phone,
                    'status': ambulance.status,
                    'latitude': ambulance.latitude,
                    'longitude': ambulance.longitude,
                    'ambulance_type': ambulance.ambulance_type
                }
            })
        else:
            # Get all ambulances
            ambulances = Ambulance.query.all()
            ambulance_list = []
            for amb in ambulances:
                ambulance_list.append({
                    'id': amb.id,
                    'vehicle_number': amb.vehicle_number,
                    'driver_name': amb.driver_name,
                    'driver_phone': amb.driver_phone,
                    'status': amb.status,
                    'latitude': amb.latitude,
                    'longitude': amb.longitude,
                    'ambulance_type': amb.ambulance_type
                })

            return jsonify({
                'success': True,
                'data': ambulance_list,
                'total': len(ambulance_list),
                'available': sum(1 for a in ambulance_list if a['status'] == 'Available'),
                'busy': sum(1 for a in ambulance_list if a['status'] == 'Busy')
            })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'An error occurred: {str(e)}'
        }), 500


@app.route('/send-alert', methods=['POST'])
def send_alert():
    """
    API Endpoint: /send-alert
    Method: POST
    
    Sends an SMS alert to a specified phone number.
    
    Expected JSON body:
    {
        "phone_number": "9876543210",
        "message": "Emergency alert message here"
    }
    """
    try:
        data = request.get_json()

        phone_number = data.get('phone_number')
        message = data.get('message')

        if not phone_number or not message:
            return jsonify({
                'success': False,
                'error': 'Phone number and message are required'
            }), 400

        # Send the mock SMS
        result = send_mock_sms(phone_number, message)

        return jsonify({
            'success': True,
            'message': 'Alert sent successfully!',
            'data': {
                'phone_number': phone_number,
                'sms_message': message,
                'status': 'Sent (Mock Mode)'
            }
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'An error occurred: {str(e)}'
        }), 500


@app.route('/api/requests', methods=['GET'])
def get_all_requests():
    """
    API Endpoint: /api/requests
    Method: GET
    
    Returns all emergency requests (used by the admin dashboard
    for live status updates via JavaScript fetch).
    """
    try:
        requests_list = EmergencyRequest.query.order_by(
            EmergencyRequest.created_at.desc()
        ).all()

        result = []
        for req in requests_list:
            # Get assigned ambulance info
            ambulance = Ambulance.query.get(req.assigned_ambulance_id) if req.assigned_ambulance_id else None
            hospital = Hospital.query.get(req.assigned_hospital_id) if req.assigned_hospital_id else None

            result.append({
                'id': req.id,
                'patient_name': req.patient_name,
                'contact_number': req.contact_number,
                'emergency_type': req.emergency_type,
                'latitude': req.latitude,
                'longitude': req.longitude,
                'address': req.address,
                'ambulance': ambulance.vehicle_number if ambulance else 'N/A',
                'hospital': hospital.name if hospital else 'N/A',
                'eta_minutes': req.eta_minutes,
                'distance_km': req.distance_km,
                'status': req.status,
                'created_at': req.created_at.strftime('%Y-%m-%d %H:%M:%S') if req.created_at else 'N/A'
            })

        return jsonify({
            'success': True,
            'data': result,
            'total': len(result)
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/update-status/<int:request_id>', methods=['PUT'])
def update_request_status(request_id):
    """
    API Endpoint: /api/update-status/<id>
    Method: PUT
    
    Update the status of an emergency request.
    Used by admin to mark requests as Completed, etc.
    """
    try:
        data = request.get_json()
        new_status = data.get('status')

        emergency = EmergencyRequest.query.get(request_id)
        if not emergency:
            return jsonify({
                'success': False,
                'error': 'Request not found'
            }), 404

        emergency.status = new_status

        # If completed, free up the ambulance
        if new_status == 'Completed' and emergency.assigned_ambulance_id:
            ambulance = Ambulance.query.get(emergency.assigned_ambulance_id)
            if ambulance:
                ambulance.status = 'Available'

        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Status updated to {new_status}'
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/sms-logs', methods=['GET'])
def get_sms_logs():
    """
    API Endpoint: /api/sms-logs
    Method: GET
    
    Returns all SMS logs for monitoring.
    """
    try:
        logs = SMSLog.query.order_by(SMSLog.sent_at.desc()).limit(50).all()
        result = []
        for log in logs:
            result.append({
                'id': log.id,
                'phone_number': log.phone_number,
                'message': log.message,
                'status': log.status,
                'sent_at': log.sent_at.strftime('%Y-%m-%d %H:%M:%S') if log.sent_at else 'N/A'
            })

        return jsonify({'success': True, 'data': result})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
#  DATABASE SEEDING – Sample Data
# ============================================================

def seed_database():
    """
    Populate the database with sample data for testing.
    
    This function adds:
        - 6 sample ambulances at various locations in Delhi
        - 4 sample hospitals
    
    This only runs if the database is empty.
    """
    # Check if data already exists
    if Ambulance.query.first():
        print("[OK] Database already seeded. Skipping.")
        return

    print("[SEED] Seeding database with sample data...")

    # ── Sample Ambulances (Delhi NCR area) ──
    ambulances = [
        Ambulance(
            vehicle_number='DL-01-AB-1234',
            driver_name='Rajesh Kumar',
            driver_phone='9876543201',
            ambulance_type='Advanced Life Support',
            status='Available',
            latitude=28.6139,
            longitude=77.2090
        ),
        Ambulance(
            vehicle_number='DL-02-CD-5678',
            driver_name='Suresh Sharma',
            driver_phone='9876543202',
            ambulance_type='Basic Life Support',
            status='Available',
            latitude=28.5355,
            longitude=77.3910
        ),
        Ambulance(
            vehicle_number='DL-03-EF-9012',
            driver_name='Amit Singh',
            driver_phone='9876543203',
            ambulance_type='Advanced Life Support',
            status='Available',
            latitude=28.7041,
            longitude=77.1025
        ),
        Ambulance(
            vehicle_number='DL-04-GH-3456',
            driver_name='Vikram Patel',
            driver_phone='9876543204',
            ambulance_type='Patient Transport',
            status='Available',
            latitude=28.4595,
            longitude=77.0266
        ),
        Ambulance(
            vehicle_number='DL-05-IJ-7890',
            driver_name='Manoj Verma',
            driver_phone='9876543205',
            ambulance_type='Advanced Life Support',
            status='Available',
            latitude=28.6304,
            longitude=77.2177
        ),
        Ambulance(
            vehicle_number='DL-06-KL-2345',
            driver_name='Deepak Yadav',
            driver_phone='9876543206',
            ambulance_type='Basic Life Support',
            status='Available',
            latitude=28.5672,
            longitude=77.3211
        ),
    ]

    # ── Sample Hospitals (Delhi NCR) ──
    hospitals = [
        Hospital(
            name='AIIMS Delhi',
            address='Sri Aurobindo Marg, Ansari Nagar, New Delhi',
            phone='011-26588500',
            latitude=28.5672,
            longitude=77.2100,
            speciality='Multi-Speciality'
        ),
        Hospital(
            name='Safdarjung Hospital',
            address='Ansari Nagar West, New Delhi',
            phone='011-26707437',
            latitude=28.5685,
            longitude=77.2065,
            speciality='General & Emergency'
        ),
        Hospital(
            name='Max Super Speciality Hospital',
            address='Saket, New Delhi',
            phone='011-26515050',
            latitude=28.5278,
            longitude=77.2148,
            speciality='Cardiac Care'
        ),
        Hospital(
            name='Fortis Hospital',
            address='Vasant Kunj, New Delhi',
            phone='011-42776222',
            latitude=28.5200,
            longitude=77.1580,
            speciality='Trauma & Emergency'
        ),
    ]

    # Add all records to database
    db.session.add_all(ambulances)
    db.session.add_all(hospitals)
    db.session.commit()

    print("[OK] Sample data added successfully!")
    print(f"   -> {len(ambulances)} Ambulances")
    print(f"   -> {len(hospitals)} Hospitals")


# ============================================================
#  APPLICATION ENTRY POINT
# ============================================================

if __name__ == '__main__':
    # Ensure instance directory exists for the SQLite database
    os.makedirs(os.path.join(BASE_DIR, 'instance'), exist_ok=True)

    # Create all database tables
    with app.app_context():
        db.create_all()
        seed_database()

    print("\n" + "=" * 60)
    print("  SANJEEVANI.AI - Every Second Saves a Life")
    print("=" * 60)
    print("  Home Page  : http://127.0.0.1:5000/")
    print("  Admin Panel : http://127.0.0.1:5000/admin")
    print("=" * 60 + "\n")

    # Run the Flask development server
    app.run(debug=True, port=5000)
