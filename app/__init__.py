import os
from pathlib import Path

from flask import Flask
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.login_message = "Inicia sesion para continuar."


def create_app():
    app = Flask(__name__, instance_relative_config=True)
    data_dir = Path(os.environ.get("DATA_DIR", app.instance_path))
    upload_dir = data_dir / "uploads"

    app.config["SECRET_KEY"] = "adecoagro-esteril-2-secret"
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{data_dir / 'adecoagro.db'}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["UPLOAD_FOLDER"] = str(upload_dir)
    app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

    data_dir.mkdir(parents=True, exist_ok=True)
    upload_dir.mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)

    from . import routes

    app.add_url_rule("/", view_func=routes.index)
    app.add_url_rule("/login", view_func=routes.login, methods=["GET", "POST"])
    app.add_url_rule("/logout", view_func=routes.logout)
    app.add_url_rule("/reportes", view_func=routes.reports)
    app.add_url_rule("/reportes/nuevo", view_func=routes.report_create, methods=["GET", "POST"])
    app.add_url_rule("/reportes/<int:report_id>", view_func=routes.report_detail, methods=["GET", "POST"])
    app.add_url_rule("/reportes/<int:report_id>/estado", view_func=routes.report_status_update, methods=["POST"])
    app.add_url_rule("/reportes/<int:report_id>/eliminar", view_func=routes.report_delete, methods=["POST"])
    app.add_url_rule("/reportes/eliminar-todos", view_func=routes.report_delete_all, methods=["POST"])
    app.add_url_rule("/admin", view_func=routes.admin_dashboard)
    app.add_url_rule("/admin/lineas", view_func=routes.manage_lines, methods=["GET", "POST"])
    app.add_url_rule("/admin/lineas/<int:line_id>/editar", view_func=routes.edit_line, methods=["POST"])
    app.add_url_rule("/admin/lineas/<int:line_id>/eliminar", view_func=routes.delete_line, methods=["POST"])
    app.add_url_rule("/admin/maquinas", view_func=routes.manage_machines, methods=["GET", "POST"])
    app.add_url_rule("/admin/maquinas/<int:machine_id>/editar", view_func=routes.edit_machine, methods=["POST"])
    app.add_url_rule("/admin/maquinas/<int:machine_id>/eliminar", view_func=routes.delete_machine, methods=["POST"])
    app.add_url_rule("/admin/categorias", view_func=routes.manage_categories, methods=["GET", "POST"])
    app.add_url_rule("/admin/categorias/<int:category_id>/editar", view_func=routes.edit_category, methods=["POST"])
    app.add_url_rule("/admin/categorias/<int:category_id>/eliminar", view_func=routes.delete_category, methods=["POST"])
    app.add_url_rule("/admin/usuarios", view_func=routes.manage_users, methods=["GET", "POST"])
    app.add_url_rule("/admin/usuarios/<int:user_id>/editar", view_func=routes.edit_user, methods=["POST"])
    app.add_url_rule("/admin/usuarios/<int:user_id>/eliminar", view_func=routes.delete_user, methods=["POST"])

    with app.app_context():
        from .models import ensure_schema, seed_data

        db.create_all()
        ensure_schema()
        seed_data()

    return app
