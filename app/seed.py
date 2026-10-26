from .models import Asset, Technician

ASSETS = [
    ("AC-C-204", "Split AC Unit", "hvac", "Block C - Room 204"),
    ("AC-C-205", "Split AC Unit", "hvac", "Block C - Room 205"),
    ("AC-A-101", "Split AC Unit", "hvac", "Block A - Room 101"),
    ("ELEC-B-DB1", "Main Distribution Board", "electrical", "Block B - Ground Floor"),
    ("ELEC-C-204", "Lighting Circuit", "electrical", "Block C - Room 204"),
    ("PLB-A-TANK", "Overhead Water Tank", "plumbing", "Block A - Terrace"),
    ("PLB-A-WC1", "Washroom Plumbing", "plumbing", "Block A - Ground Floor"),
    ("IT-LIB-AP1", "WiFi Access Point", "it_network", "Library"),
    ("IT-C-204-PRJ", "Projector", "it_network", "Block C - Room 204"),
    ("LIFT-A-1", "Passenger Lift 1", "lift", "Block A - Ground Floor"),
    ("FIRE-B-EXT1", "Fire Extinguisher", "safety", "Block B - Ground Floor"),
    ("CIV-A-101-CEIL", "False Ceiling", "civil", "Block A - Room 101"),
]
TECHS = [
    ("Ravi", "electrician"), ("Karthik", "electrician"), ("Suresh", "plumber"), ("Mani", "plumber"),
    ("Anand", "hvac_technician"), ("Divya", "hvac_technician"), ("Prakash", "civil_technician"),
    ("Meena", "it_support"), ("Lakshmi", "housekeeping_staff"), ("Arun", "safety_officer"),
    ("Selvam", "lift_technician"), ("Bala", "general_technician"),
]


def seed_demo_data(session):
    if session.query(Asset).count() == 0:
        session.add_all(Asset(code=c, name=n, category=k, location=l) for c, n, k, l in ASSETS)
    if session.query(Technician).count() == 0:
        session.add_all(Technician(name=n, skill=s, available=True) for n, s in TECHS)
    session.commit()
