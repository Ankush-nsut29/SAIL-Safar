import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from flask import Flask
from model import db
from blueprints.auth import auth_bp
from blueprints.home import home_bp
from blueprints.dashboard import dashboard_bp

app = Flask(__name__)
app.secret_key = "antigrav_secret_key"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///data.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

app.register_blueprint(auth_bp)
app.register_blueprint(home_bp)
app.register_blueprint(dashboard_bp)

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
