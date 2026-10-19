import os
from flask import Flask
from database.init_db import criar_banco
from routes.participantes import participantes_bp
from routes.admin import admin_bp

criar_banco()
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-apenas-local-troque-em-producao")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
app.register_blueprint(participantes_bp)
app.register_blueprint(admin_bp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
