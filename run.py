from app import create_app
import os

app = create_app()

if __name__ == '__main__':
    # Só ativa o debug se a gente disser explicitamente que quer
    debug_mode = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(debug=debug_mode)