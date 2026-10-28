from pathlib import Path

from flask import Flask

from config import Config
from routes.image_routes import image_bp
from routes.main_routes import main_bp
from routes.pdf_routes import pdf_bp


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    asset_paths = (
        Path(app.static_folder) / "css" / "style.css",
        Path(app.static_folder) / "js" / "app.js",
    )
    app.config["STATIC_ASSET_VERSION"] = str(
        max(path.stat().st_mtime_ns for path in asset_paths)
    )
    app.register_blueprint(main_bp)
    app.register_blueprint(image_bp)
    app.register_blueprint(pdf_bp)
    return app


if __name__ == "__main__":
    create_app().run()
