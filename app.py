from flask import Flask
import os

from routes.participantes import participantes_bp
from routes.admin import admin_bp

app = Flask(__name__)
app.secret_key = os.environ["SECRET_KEY"]
app.register_blueprint(participantes_bp)
app.register_blueprint(admin_bp)


if __name__ == "__main__":
    app.run(debug=True)