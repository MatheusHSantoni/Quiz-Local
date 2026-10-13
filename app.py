from flask import Flask
import os
from routes.participantes import participantes_bp

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "chave-temporaria-do-quiz")

app.register_blueprint(participantes_bp)

if __name__ == "__main__":
    app.run(debug=True)