from flask import Blueprint, render_template
from services.data_loader import get_eastcoast_ports, get_foreign_ports, get_vessels

home_bp = Blueprint('home', __name__)

@home_bp.route('/')
def index():
    eastcoast_ports = get_eastcoast_ports()
    foreign_ports = get_foreign_ports()
    vessels = get_vessels()
    return render_template('home/index.html', 
                           eastcoast_ports=eastcoast_ports, 
                           foreign_ports=foreign_ports, 
                           vessels=vessels)
