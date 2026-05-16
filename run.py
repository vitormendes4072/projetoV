from dotenv import load_dotenv
load_dotenv()

from app import create_app
app = create_app()
import os
print("ENV DATABASE_URL:", os.getenv("DATABASE_URL"))
print("CONFIG SQLALCHEMY_DATABASE_URI:", app.config.get("SQLALCHEMY_DATABASE_URI"))


if __name__ == '__main__':
    # Só ativa o debug se a gente disser explicitamente que quer
    debug_mode = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(debug=debug_mode)