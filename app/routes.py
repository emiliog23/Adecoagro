from pathlib import Path
from uuid import uuid4

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.utils import secure_filename

from . import db
from .models import Attachment, Category, Factory, Machine, ProductionLine, REPORT_STATUSES, Report, ReportComment, User

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def admin_required():
    if not current_user.is_authenticated or not current_user.can_review_reports:
        flash("Solo administracion o supervision puede acceder a esa seccion.", "error")
        return False
    return True


def reviewer_required():
    if not current_user.is_authenticated or not current_user.can_review_reports:
        flash("Solo administracion o supervision puede realizar esa accion.", "error")
        return False
    return True


def delete_attachment_file(filename):
    file_path = Path(current_app.config["UPLOAD_FOLDER"]) / filename
    if file_path.exists():
        file_path.unlink()


def delete_report_files(report):
    for attachment in report.attachments:
        delete_attachment_file(attachment.filename)


def index():
    if current_user.is_authenticated:
        return redirect(url_for("reports"))
    return redirect(url_for("login"))


def login():
    if current_user.is_authenticated:
        return redirect(url_for("reports"))

    users = User.query.order_by(User.full_name).all()

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            flash(f"Bienvenido, {user.full_name}.", "success")
            return redirect(url_for("reports"))
        flash("Usuario o contrasena invalidos.", "error")

    return render_template("login.html", users=users)


@login_required
def logout():
    logout_user()
    flash("Sesion cerrada.", "success")
    return redirect(url_for("login"))


@login_required
def reports():
    status_filter = request.args.get("status", "").strip()
    line_filter = request.args.get("line_id", type=int)

    query = Report.query.order_by(Report.created_at.desc())
    if status_filter:
        query = query.filter_by(status=status_filter)
    if line_filter:
        query = query.join(Machine).filter(Machine.line_id == line_filter)

    if not current_user.can_review_reports:
        query = query.filter_by(created_by_id=current_user.id)

    all_reports = query.all()
    lines = ProductionLine.query.order_by(ProductionLine.name).all()

    return render_template(
        "reports.html",
        reports=all_reports,
        statuses=REPORT_STATUSES,
        lines=lines,
        status_filter=status_filter,
        line_filter=line_filter,
    )


@login_required
def report_create():
    lines = ProductionLine.query.filter_by(active=True).order_by(ProductionLine.name).all()
    machines = Machine.query.filter_by(active=True).order_by(Machine.name).all()
    categories = Category.query.filter_by(active=True).order_by(Category.name).all()

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        actions_taken = request.form.get("actions_taken", "").strip()
        spare_parts_used = request.form.get("spare_parts_used", "").strip()
        downtime_minutes = request.form.get("downtime_minutes", type=int)
        category_id = request.form.get("category_id", type=int)
        machine_id = request.form.get("machine_id", type=int)

        if not title or not description or not category_id or not machine_id:
            flash("Completa titulo, descripcion, categoria y maquina.", "error")
            return render_template("report_form.html", lines=lines, machines=machines, categories=categories)

        report = Report(
            title=title,
            description=description,
            actions_taken=actions_taken or None,
            spare_parts_used=spare_parts_used or None,
            downtime_minutes=downtime_minutes,
            category_id=category_id,
            machine_id=machine_id,
            created_by_id=current_user.id,
        )
        db.session.add(report)
        db.session.flush()

        for file in request.files.getlist("images"):
            if not file or not file.filename:
                continue
            if not allowed_file(file.filename):
                flash(f"Archivo no permitido: {file.filename}", "error")
                continue

            original_name = secure_filename(file.filename)
            extension = original_name.rsplit(".", 1)[1].lower()
            saved_name = f"{uuid4().hex}.{extension}"
            save_path = Path(current_app.config["UPLOAD_FOLDER"]) / saved_name
            file.save(save_path)

            db.session.add(
                Attachment(
                    filename=saved_name,
                    original_name=original_name,
                    report_id=report.id,
                )
            )

        db.session.commit()
        flash("Reporte creado correctamente.", "success")
        return redirect(url_for("report_detail", report_id=report.id))

    return render_template("report_form.html", lines=lines, machines=machines, categories=categories)


@login_required
def report_detail(report_id):
    report = Report.query.get_or_404(report_id)
    if not current_user.can_review_reports and report.created_by_id != current_user.id:
        flash("No tienes acceso a este reporte.", "error")
        return redirect(url_for("reports"))

    if request.method == "POST":
        comment = request.form.get("comment", "").strip()
        if current_user.can_review_reports and comment:
            db.session.add(ReportComment(content=comment, report_id=report.id, created_by_id=current_user.id))
            db.session.commit()
            flash("Comentario agregado.", "success")
            return redirect(url_for("report_detail", report_id=report.id))
        else:
            flash("Escribe un comentario para guardarlo.", "error")

    return render_template("report_detail.html", report=report, statuses=REPORT_STATUSES)


@login_required
def report_status_update(report_id):
    if not reviewer_required():
        return redirect(url_for("reports"))

    report = Report.query.get_or_404(report_id)
    new_status = request.form.get("status", "").strip()
    if new_status not in REPORT_STATUSES:
        flash("Estado invalido.", "error")
        return redirect(url_for("report_detail", report_id=report.id))

    report.status = new_status
    db.session.commit()
    flash("Estado actualizado.", "success")
    return redirect(url_for("report_detail", report_id=report.id))


@login_required
def report_delete(report_id):
    if not admin_required():
        return redirect(url_for("reports"))

    report = Report.query.get_or_404(report_id)
    delete_report_files(report)
    db.session.delete(report)
    db.session.commit()
    flash("Reporte eliminado.", "success")
    return redirect(url_for("reports"))


@login_required
def report_delete_all():
    if not admin_required():
        return redirect(url_for("reports"))

    all_reports = Report.query.all()
    deleted_count = len(all_reports)
    for report in all_reports:
        delete_report_files(report)
        db.session.delete(report)
    db.session.commit()
    flash(f"Se eliminaron {deleted_count} reportes.", "success")
    return redirect(url_for("admin_dashboard"))


@login_required
def admin_dashboard():
    if not admin_required():
        return redirect(url_for("reports"))

    return render_template(
        "admin_dashboard.html",
        factories=Factory.query.order_by(Factory.name).all(),
        lines=ProductionLine.query.order_by(ProductionLine.name).all(),
        machines=Machine.query.order_by(Machine.name).all(),
        categories=Category.query.order_by(Category.name).all(),
        users=User.query.order_by(User.full_name).all(),
        reports=Report.query.order_by(Report.created_at.desc()).limit(10).all(),
    )


@login_required
def manage_lines():
    if not admin_required():
        return redirect(url_for("reports"))

    factories = Factory.query.order_by(Factory.name).all()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        factory_id = request.form.get("factory_id", type=int)
        active = request.form.get("active") == "on"
        if not name or not factory_id:
            flash("Completa nombre y fabrica.", "error")
        else:
            db.session.add(ProductionLine(name=name, factory_id=factory_id, active=active))
            db.session.commit()
            flash("Linea creada.", "success")
        return redirect(url_for("manage_lines"))

    return render_template("manage_lines.html", factories=factories, lines=ProductionLine.query.order_by(ProductionLine.name).all())


@login_required
def edit_line(line_id):
    if not admin_required():
        return redirect(url_for("reports"))

    line = ProductionLine.query.get_or_404(line_id)
    line.name = request.form.get("name", line.name).strip() or line.name
    line.active = request.form.get("active") == "on"
    db.session.commit()
    flash("Linea actualizada.", "success")
    return redirect(url_for("manage_lines"))


@login_required
def delete_line(line_id):
    if not admin_required():
        return redirect(url_for("reports"))

    line = ProductionLine.query.get_or_404(line_id)
    if line.machines:
        flash("No puedes eliminar una linea que todavia tiene maquinas asociadas.", "error")
    else:
        db.session.delete(line)
        db.session.commit()
        flash("Linea eliminada.", "success")
    return redirect(url_for("manage_lines"))


@login_required
def manage_machines():
    if not admin_required():
        return redirect(url_for("reports"))

    lines = ProductionLine.query.order_by(ProductionLine.name).all()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        line_id = request.form.get("line_id", type=int)
        active = request.form.get("active") == "on"
        if not name or not line_id:
            flash("Completa nombre y linea.", "error")
        else:
            db.session.add(Machine(name=name, line_id=line_id, active=active))
            db.session.commit()
            flash("Maquina creada.", "success")
        return redirect(url_for("manage_machines"))

    return render_template("manage_machines.html", lines=lines, machines=Machine.query.order_by(Machine.name).all())


@login_required
def edit_machine(machine_id):
    if not admin_required():
        return redirect(url_for("reports"))

    machine = Machine.query.get_or_404(machine_id)
    machine.name = request.form.get("name", machine.name).strip() or machine.name
    machine.line_id = request.form.get("line_id", type=int) or machine.line_id
    machine.active = request.form.get("active") == "on"
    db.session.commit()
    flash("Maquina actualizada.", "success")
    return redirect(url_for("manage_machines"))


@login_required
def delete_machine(machine_id):
    if not admin_required():
        return redirect(url_for("reports"))

    machine = Machine.query.get_or_404(machine_id)
    if machine.reports:
        flash("No puedes eliminar una maquina que tiene reportes asociados.", "error")
    else:
        db.session.delete(machine)
        db.session.commit()
        flash("Maquina eliminada.", "success")
    return redirect(url_for("manage_machines"))


@login_required
def manage_categories():
    if not admin_required():
        return redirect(url_for("reports"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        active = request.form.get("active") == "on"
        if not name:
            flash("Completa el nombre de la categoria.", "error")
        else:
            db.session.add(Category(name=name, active=active))
            db.session.commit()
            flash("Categoria creada.", "success")
        return redirect(url_for("manage_categories"))

    return render_template("manage_categories.html", categories=Category.query.order_by(Category.name).all())


@login_required
def edit_category(category_id):
    if not admin_required():
        return redirect(url_for("reports"))

    category = Category.query.get_or_404(category_id)
    category.name = request.form.get("name", category.name).strip() or category.name
    category.active = request.form.get("active") == "on"
    db.session.commit()
    flash("Categoria actualizada.", "success")
    return redirect(url_for("manage_categories"))


@login_required
def delete_category(category_id):
    if not admin_required():
        return redirect(url_for("reports"))

    category = Category.query.get_or_404(category_id)
    if category.reports:
        flash("No puedes eliminar una categoria que tiene reportes asociados.", "error")
    else:
        db.session.delete(category)
        db.session.commit()
        flash("Categoria eliminada.", "success")
    return redirect(url_for("manage_categories"))


@login_required
def manage_users():
    if not admin_required():
        return redirect(url_for("reports"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        full_name = request.form.get("full_name", "").strip()
        password = request.form.get("password", "").strip()
        role = request.form.get("role", "usuario").strip()

        if not username or not full_name or not password or role not in {"admin", "supervisor", "usuario"}:
            flash("Completa usuario, nombre, clave y rol validos.", "error")
        elif User.query.filter_by(username=username).first():
            flash("Ese usuario ya existe.", "error")
        else:
            user = User(username=username, full_name=full_name, role=role)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash("Usuario creado.", "success")
        return redirect(url_for("manage_users"))

    return render_template("manage_users.html", users=User.query.order_by(User.full_name).all())


@login_required
def edit_user(user_id):
    if not admin_required():
        return redirect(url_for("reports"))

    user = User.query.get_or_404(user_id)
    user.full_name = request.form.get("full_name", user.full_name).strip() or user.full_name
    role = request.form.get("role", user.role).strip()
    if role in {"admin", "supervisor", "usuario"}:
        user.role = role
    new_password = request.form.get("password", "").strip()
    if new_password:
        user.set_password(new_password)
    db.session.commit()
    flash("Usuario actualizado.", "success")
    return redirect(url_for("manage_users"))


@login_required
def delete_user(user_id):
    if not admin_required():
        return redirect(url_for("reports"))

    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("No puedes eliminar tu propio usuario mientras estas conectado.", "error")
    elif user.reports:
        flash("No puedes eliminar un usuario que tiene reportes asociados.", "error")
    else:
        db.session.delete(user)
        db.session.commit()
        flash("Usuario eliminado.", "success")
    return redirect(url_for("manage_users"))
