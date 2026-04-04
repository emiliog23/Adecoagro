from datetime import datetime
from pathlib import Path
from statistics import mean
from uuid import uuid4

from flask import current_app, flash, redirect, render_template, request, send_from_directory, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.utils import secure_filename

from . import db
from .models import (
    Attachment,
    Category,
    Factory,
    Machine,
    MachineParameter,
    MachineParameterReading,
    PARAMETER_REPORT_TYPES,
    ProductionLine,
    REPORT_STATUSES,
    Report,
    ReportConsolidation,
    ReportComment,
    USER_ROLES,
    User,
    report_consolidation_links,
    report_parameter_links,
)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def admin_required():
    if not current_user.is_authenticated or not current_user.can_manage_admin:
        flash("Solo administracion puede acceder a esa seccion.", "error")
        return False
    return True


def reviewer_required():
    if not current_user.is_authenticated or not current_user.can_review_reports:
        flash("Solo administracion o supervision puede realizar esa accion.", "error")
        return False
    return True


def superadmin_required():
    if not current_user.is_authenticated or not current_user.is_superadmin:
        flash("Solo un superadmin puede realizar esa accion.", "error")
        return False
    return True


def delete_report_record(report):
    db.session.execute(
        report_parameter_links.delete().where(report_parameter_links.c.report_id == report.id)
    )
    db.session.execute(
        report_consolidation_links.delete().where(report_consolidation_links.c.report_id == report.id)
    )
    delete_report_files(report)
    db.session.delete(report)


def build_accessible_reports_query():
    query = Report.query.order_by(Report.created_at.desc())
    if not current_user.can_review_reports:
        query = query.filter_by(created_by_id=current_user.id)
    return query


def build_parameter_choices():
    parameters = MachineParameter.query.join(Machine).order_by(Machine.name, MachineParameter.parameter_type, MachineParameter.name).all()
    return parameters


def purge_machine(machine):
    for report in list(machine.reports):
        delete_report_record(report)
    for parameter in list(machine.parameter_definitions):
        db.session.execute(
            report_parameter_links.delete().where(report_parameter_links.c.parameter_id == parameter.id)
        )
        db.session.delete(parameter)
    db.session.delete(machine)


def purge_user(user):
    for comment in list(user.comments):
        db.session.delete(comment)
    for reading in list(MachineParameterReading.query.filter_by(created_by_id=user.id).all()):
        db.session.delete(reading)
    for report in list(user.reports):
        delete_report_record(report)
    for consolidation in list(user.consolidations_created):
        db.session.delete(consolidation)
    db.session.delete(user)


def delete_attachment_file(filename):
    file_path = Path(current_app.config["UPLOAD_FOLDER"]) / filename
    if file_path.exists():
        file_path.unlink()


def delete_report_files(report):
    for attachment in report.attachments:
        delete_attachment_file(attachment.filename)


def attach_uploaded_files(report, files):
    for file in files:
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


def build_parameter_stats(parameter, recipe_filter=""):
    readings = sorted(parameter.readings, key=lambda item: (item.changed_at, item.created_at), reverse=True)
    if recipe_filter:
        readings = [reading for reading in readings if reading.current_recipe == recipe_filter]
    if not readings:
        return None

    latest = readings[0]
    previous = readings[1] if len(readings) > 1 else None
    values = [reading.value for reading in readings]

    if previous is None:
        trend_label = "Sin historial"
    elif latest.value > previous.value:
        trend_label = "Positivo"
    elif latest.value < previous.value:
        trend_label = "Negativo"
    else:
        trend_label = "Estable"

    return {
        "parameter": parameter,
        "latest": latest,
        "previous": previous,
        "average": mean(values),
        "highest": max(values),
        "lowest": min(values),
        "trend_label": trend_label,
        "history_count": len(readings),
        "readings": readings,
    }


def uploaded_file(filename):
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)


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
    category_filter = request.args.get("category_id", type=int)
    user_filter = request.args.get("user_id", type=int)

    query = build_accessible_reports_query()
    if status_filter:
        query = query.filter_by(status=status_filter)
    if line_filter:
        query = query.join(Machine).filter(Machine.line_id == line_filter)
    if category_filter:
        query = query.filter(Report.category_id == category_filter)
    if user_filter and current_user.can_review_reports:
        query = query.filter(Report.created_by_id == user_filter)

    if not current_user.can_review_reports:
        query = query.filter_by(created_by_id=current_user.id)

    all_reports = query.all()
    lines = ProductionLine.query.order_by(ProductionLine.name).all()
    categories = Category.query.order_by(Category.name).all()
    users = User.query.order_by(User.full_name).all() if current_user.can_review_reports else []

    return render_template(
        "reports.html",
        reports=all_reports,
        statuses=REPORT_STATUSES,
        lines=lines,
        categories=categories,
        users=users,
        status_filter=status_filter,
        line_filter=line_filter,
        category_filter=category_filter,
        user_filter=user_filter,
    )


@login_required
def parameter_reports():
    recipe_filter = request.args.get("recipe", "").strip()
    machines = Machine.query.order_by(Machine.name).all()
    machine_cards = []
    available_recipes = set()

    for machine in machines:
        stats = [build_parameter_stats(parameter, recipe_filter) for parameter in machine.parameter_definitions]
        stats = [stat for stat in stats if stat]
        machine_recipes = sorted(
            {
                reading.current_recipe
                for parameter in machine.parameter_definitions
                for reading in parameter.readings
            }
        )
        available_recipes.update(machine_recipes)

        if recipe_filter and recipe_filter not in machine_recipes:
            continue

        latest_change = max((stat["latest"].changed_at for stat in stats), default=None)

        machine_cards.append(
            {
                "machine": machine,
                "parameter_count": len(stats),
                "latest_change": latest_change,
                "types": sorted({stat["parameter"].parameter_type for stat in stats}),
                "recipes": machine_recipes,
            }
        )

    return render_template(
        "parameter_reports.html",
        machine_cards=machine_cards,
        available_recipes=sorted(available_recipes),
        recipe_filter=recipe_filter,
    )


@login_required
def parameter_report_create():
    machines = Machine.query.filter_by(active=True).order_by(Machine.name).all()

    if request.method == "POST":
        machine_id = request.form.get("machine_id", type=int)
        parameter_name = request.form.get("parameter_name", "").strip()
        parameter_type = request.form.get("parameter_type", "").strip()
        current_recipe = request.form.get("current_recipe", "").strip()
        unit = request.form.get("unit", "").strip()
        value = request.form.get("value", type=float)
        changed_at_raw = request.form.get("changed_at", "").strip()

        if not machine_id or not parameter_name or parameter_type not in PARAMETER_REPORT_TYPES or not current_recipe or not unit or value is None or not changed_at_raw:
            flash("Completa maquina, tipo, nombre del parametro, receta actual, unidad, valor y fecha de cambio.", "error")
            return render_template(
                "parameter_report_form.html",
                machines=machines,
                parameter_types=PARAMETER_REPORT_TYPES,
            )

        changed_at = None
        try:
            changed_at = datetime.fromisoformat(changed_at_raw)
        except ValueError:
            flash("La fecha del cambio no es valida.", "error")
            return render_template(
                "parameter_report_form.html",
                machines=machines,
                parameter_types=PARAMETER_REPORT_TYPES,
            )

        parameter = MachineParameter.query.filter_by(
            machine_id=machine_id,
            name=parameter_name,
            parameter_type=parameter_type,
            unit=unit,
        ).first()

        if parameter is None:
            parameter = MachineParameter(
                machine_id=machine_id,
                name=parameter_name,
                parameter_type=parameter_type,
                unit=unit,
            )
            db.session.add(parameter)
            db.session.flush()

        reading = MachineParameterReading(
            parameter_id=parameter.id,
            current_recipe=current_recipe,
            value=value,
            changed_at=changed_at,
            created_by_id=current_user.id,
        )
        db.session.add(reading)
        db.session.commit()
        flash("Parametro registrado correctamente.", "success")
        return redirect(url_for("parameter_report_machine", machine_id=machine_id))

    return render_template(
        "parameter_report_form.html",
        machines=machines,
        parameter_types=PARAMETER_REPORT_TYPES,
    )


@login_required
def parameter_report_machine(machine_id):
    machine = Machine.query.get_or_404(machine_id)
    recipe_filter = request.args.get("recipe", "").strip()
    report_id = request.args.get("report_id", type=int)
    source_report = None
    selected_parameter_ids = None

    if report_id:
        source_report = Report.query.get_or_404(report_id)
        if not current_user.can_review_reports and source_report.created_by_id != current_user.id:
            flash("No tienes acceso a ese reporte.", "error")
            return redirect(url_for("reports"))
        if source_report.machine_id != machine.id:
            flash("Ese reporte no pertenece a la maquina consultada.", "error")
            return redirect(url_for("parameter_report_machine", machine_id=machine.id))
        selected_parameter_ids = {parameter.id for parameter in source_report.parameters}

    parameter_cards = [build_parameter_stats(parameter, recipe_filter) for parameter in machine.parameter_definitions]
    parameter_cards = [card for card in parameter_cards if card]
    if selected_parameter_ids is not None:
        parameter_cards = [card for card in parameter_cards if card["parameter"].id in selected_parameter_ids]
    available_recipes = sorted(
        {
            reading.current_recipe
            for parameter in machine.parameter_definitions
            for reading in parameter.readings
        }
    )
    parameter_cards.sort(key=lambda card: (card["parameter"].parameter_type, card["parameter"].name.lower()))
    return render_template(
        "parameter_report_machine.html",
        machine=machine,
        parameter_cards=parameter_cards,
        available_recipes=available_recipes,
        parameter_types=PARAMETER_REPORT_TYPES,
        recipe_filter=recipe_filter,
        source_report=source_report,
    )


@login_required
def report_consolidations():
    accessible_reports = build_accessible_reports_query().all()
    accessible_report_ids = {report.id for report in accessible_reports}
    consolidations = [
        consolidation
        for consolidation in ReportConsolidation.query.order_by(ReportConsolidation.created_at.desc()).all()
        if any(report.id in accessible_report_ids for report in consolidation.reports)
    ]

    return render_template(
        "report_consolidations.html",
        consolidations=consolidations,
    )


@login_required
def report_consolidation_new():
    return render_template(
        "report_consolidation_form.html",
        reports=build_accessible_reports_query().all(),
    )


@login_required
def parameter_delete(parameter_id):
    if not superadmin_required():
        return redirect(url_for("parameter_reports"))

    parameter = MachineParameter.query.get_or_404(parameter_id)
    machine_id = parameter.machine_id
    recipe_filter = request.form.get("recipe_filter", "").strip()
    db.session.execute(
        report_parameter_links.delete().where(report_parameter_links.c.parameter_id == parameter.id)
    )
    db.session.delete(parameter)
    db.session.commit()
    flash("Parametro eliminado junto con todo su historial.", "success")

    if recipe_filter:
        return redirect(url_for("parameter_report_machine", machine_id=machine_id, recipe=recipe_filter))
    return redirect(url_for("parameter_report_machine", machine_id=machine_id))


@login_required
def parameter_edit(parameter_id):
    if not superadmin_required():
        return redirect(url_for("parameter_reports"))

    parameter = MachineParameter.query.get_or_404(parameter_id)
    machine_id = parameter.machine_id
    recipe_filter = request.form.get("recipe_filter", "").strip()
    name = request.form.get("name", "").strip()
    parameter_type = request.form.get("parameter_type", "").strip()
    unit = request.form.get("unit", "").strip()

    if not name or parameter_type not in PARAMETER_REPORT_TYPES or not unit:
        flash("Completa nombre, tipo y unidad del parametro.", "error")
    else:
        parameter.name = name
        parameter.parameter_type = parameter_type
        parameter.unit = unit
        db.session.commit()
        flash("Parametro actualizado.", "success")

    if recipe_filter:
        return redirect(url_for("parameter_report_machine", machine_id=machine_id, recipe=recipe_filter))
    return redirect(url_for("parameter_report_machine", machine_id=machine_id))


@login_required
def parameter_reading_edit(reading_id):
    if not superadmin_required():
        return redirect(url_for("parameter_reports"))

    reading = MachineParameterReading.query.get_or_404(reading_id)
    machine_id = reading.parameter.machine_id
    recipe_filter = request.form.get("recipe_filter", "").strip()
    current_recipe = request.form.get("current_recipe", "").strip()
    value = request.form.get("value", type=float)
    changed_at_raw = request.form.get("changed_at", "").strip()

    if not current_recipe or value is None or not changed_at_raw:
        flash("Completa receta, valor y fecha de cambio.", "error")
    else:
        try:
            changed_at = datetime.fromisoformat(changed_at_raw)
        except ValueError:
            flash("La fecha del cambio no es valida.", "error")
        else:
            reading.current_recipe = current_recipe
            reading.value = value
            reading.changed_at = changed_at
            db.session.commit()
            flash("Entrada de parametro actualizada.", "success")

    if recipe_filter:
        return redirect(url_for("parameter_report_machine", machine_id=machine_id, recipe=recipe_filter))
    return redirect(url_for("parameter_report_machine", machine_id=machine_id))


@login_required
def parameter_reading_delete(reading_id):
    if not superadmin_required():
        return redirect(url_for("parameter_reports"))

    reading = MachineParameterReading.query.get_or_404(reading_id)
    machine_id = reading.parameter.machine_id
    recipe_filter = request.form.get("recipe_filter", "").strip()
    db.session.delete(reading)
    db.session.commit()
    flash("Entrada de parametro eliminada.", "success")

    if recipe_filter:
        return redirect(url_for("parameter_report_machine", machine_id=machine_id, recipe=recipe_filter))
    return redirect(url_for("parameter_report_machine", machine_id=machine_id))


@login_required
def report_create():
    lines = ProductionLine.query.filter_by(active=True).order_by(ProductionLine.name).all()
    machines = Machine.query.filter_by(active=True).order_by(Machine.name).all()
    categories = Category.query.filter_by(active=True).order_by(Category.name).all()
    parameters = build_parameter_choices()

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        actions_taken = request.form.get("actions_taken", "").strip()
        spare_parts_used = request.form.get("spare_parts_used", "").strip()
        downtime_minutes = request.form.get("downtime_minutes", type=int)
        category_id = request.form.get("category_id", type=int)
        machine_id = request.form.get("machine_id", type=int)
        parameter_ids = {parameter_id for parameter_id in request.form.getlist("parameter_ids") if parameter_id}

        if not title or not description or not category_id or not machine_id:
            flash("Completa titulo, descripcion, categoria y maquina.", "error")
            return render_template(
                "report_form.html",
                lines=lines,
                machines=machines,
                categories=categories,
                parameters=parameters,
            )

        selected_parameters = []
        if parameter_ids:
            selected_parameters = MachineParameter.query.filter(MachineParameter.id.in_(parameter_ids)).all()
            selected_parameter_ids = {str(parameter.id) for parameter in selected_parameters}
            if selected_parameter_ids != parameter_ids:
                flash("Se seleccionaron parametros invalidos.", "error")
                return render_template(
                    "report_form.html",
                    lines=lines,
                    machines=machines,
                    categories=categories,
                    parameters=parameters,
                )
            if any(parameter.machine_id != machine_id for parameter in selected_parameters):
                flash("Solo puedes vincular parametros de la maquina seleccionada.", "error")
                return render_template(
                    "report_form.html",
                    lines=lines,
                    machines=machines,
                    categories=categories,
                    parameters=parameters,
                )

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
        report.parameters = selected_parameters

        attach_uploaded_files(report, request.files.getlist("images"))

        db.session.commit()
        flash("Reporte creado correctamente.", "success")
        return redirect(url_for("report_detail", report_id=report.id))

    return render_template(
        "report_form.html",
        lines=lines,
        machines=machines,
        categories=categories,
        parameters=parameters,
    )


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

    return render_template(
        "report_detail.html",
        report=report,
        statuses=REPORT_STATUSES,
        users=User.query.order_by(User.full_name).all(),
        categories=Category.query.order_by(Category.name).all(),
        machines=Machine.query.order_by(Machine.name).all(),
        parameters=build_parameter_choices(),
    )


@login_required
def report_edit(report_id):
    if not superadmin_required():
        return redirect(url_for("reports"))

    report = Report.query.get_or_404(report_id)
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    actions_taken = request.form.get("actions_taken", "").strip()
    spare_parts_used = request.form.get("spare_parts_used", "").strip()
    downtime_minutes = request.form.get("downtime_minutes", type=int)
    category_id = request.form.get("category_id", type=int)
    machine_id = request.form.get("machine_id", type=int)
    created_by_id = request.form.get("created_by_id", type=int)
    status = request.form.get("status", "").strip()
    created_at_raw = request.form.get("created_at", "").strip()
    parameter_ids = {parameter_id for parameter_id in request.form.getlist("parameter_ids") if parameter_id}

    if not title or not description or not category_id or not machine_id or not created_by_id or status not in REPORT_STATUSES or not created_at_raw:
        flash("Completa todos los campos obligatorios del reporte.", "error")
        return redirect(url_for("report_detail", report_id=report.id))

    try:
        created_at = datetime.fromisoformat(created_at_raw)
    except ValueError:
        flash("La fecha de creacion del reporte no es valida.", "error")
        return redirect(url_for("report_detail", report_id=report.id))

    selected_parameters = MachineParameter.query.filter(MachineParameter.id.in_(parameter_ids)).all() if parameter_ids else []
    if any(parameter.machine_id != machine_id for parameter in selected_parameters):
        flash("Solo puedes vincular parametros de la maquina seleccionada.", "error")
        return redirect(url_for("report_detail", report_id=report.id))

    report.title = title
    report.description = description
    report.actions_taken = actions_taken or None
    report.spare_parts_used = spare_parts_used or None
    report.downtime_minutes = downtime_minutes
    report.category_id = category_id
    report.machine_id = machine_id
    report.created_by_id = created_by_id
    report.status = status
    report.created_at = created_at
    report.parameters = selected_parameters
    attach_uploaded_files(report, request.files.getlist("images"))
    db.session.commit()
    flash("Reporte actualizado.", "success")
    return redirect(url_for("report_detail", report_id=report.id))


@login_required
def report_attachment_delete(attachment_id):
    if not superadmin_required():
        return redirect(url_for("reports"))

    attachment = Attachment.query.get_or_404(attachment_id)
    report_id = attachment.report_id
    delete_attachment_file(attachment.filename)
    db.session.delete(attachment)
    db.session.commit()
    flash("Adjunto eliminado.", "success")
    return redirect(url_for("report_detail", report_id=report_id))


@login_required
def report_comment_edit(comment_id):
    if not superadmin_required():
        return redirect(url_for("reports"))

    comment = ReportComment.query.get_or_404(comment_id)
    report_id = comment.report_id
    content = request.form.get("content", "").strip()
    created_by_id = request.form.get("created_by_id", type=int)
    created_at_raw = request.form.get("created_at", "").strip()
    if not content or not created_by_id or not created_at_raw:
        flash("Completa comentario, usuario y fecha.", "error")
    else:
        try:
            created_at = datetime.fromisoformat(created_at_raw)
        except ValueError:
            flash("La fecha del comentario no es valida.", "error")
            return redirect(url_for("report_detail", report_id=report_id))
        comment.content = content
        comment.created_by_id = created_by_id
        comment.created_at = created_at
        db.session.commit()
        flash("Comentario actualizado.", "success")
    return redirect(url_for("report_detail", report_id=report_id))


@login_required
def report_comment_delete(comment_id):
    if not superadmin_required():
        return redirect(url_for("reports"))

    comment = ReportComment.query.get_or_404(comment_id)
    report_id = comment.report_id
    db.session.delete(comment)
    db.session.commit()
    flash("Comentario eliminado.", "success")
    return redirect(url_for("report_detail", report_id=report_id))


@login_required
def report_consolidation_create():
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    report_ids = {report_id for report_id in request.form.getlist("report_ids") if report_id}

    if not title:
        flash("Completa el titulo de la consolidacion.", "error")
        return redirect(url_for("report_consolidation_new"))

    if len(report_ids) < 2:
        flash("Selecciona al menos dos reportes para consolidar.", "error")
        return redirect(url_for("report_consolidation_new"))

    accessible_reports = build_accessible_reports_query().all()
    accessible_report_map = {str(report.id): report for report in accessible_reports}
    if any(report_id not in accessible_report_map for report_id in report_ids):
        flash("Hay reportes seleccionados a los que no tienes acceso.", "error")
        return redirect(url_for("report_consolidation_new"))

    consolidation = ReportConsolidation(
        title=title,
        description=description or None,
        created_by_id=current_user.id,
    )
    consolidation.reports = [accessible_report_map[report_id] for report_id in sorted(report_ids, key=int)]
    db.session.add(consolidation)
    db.session.commit()
    flash("Consolidacion creada correctamente.", "success")
    return redirect(url_for("report_consolidation_detail", consolidation_id=consolidation.id))


@login_required
def report_consolidation_detail(consolidation_id):
    consolidation = ReportConsolidation.query.get_or_404(consolidation_id)
    accessible_report_ids = {report.id for report in build_accessible_reports_query().all()}
    visible_reports = [report for report in consolidation.reports if report.id in accessible_report_ids]

    if not visible_reports:
        flash("No tienes acceso a esta consolidacion.", "error")
        return redirect(url_for("reports"))

    return render_template(
        "report_consolidation_detail.html",
        consolidation=consolidation,
        visible_reports=sorted(visible_reports, key=lambda report: report.created_at, reverse=True),
        users=User.query.order_by(User.full_name).all(),
        reports=build_accessible_reports_query().all(),
    )


@login_required
def report_consolidation_edit(consolidation_id):
    if not superadmin_required():
        return redirect(url_for("report_consolidations"))

    consolidation = ReportConsolidation.query.get_or_404(consolidation_id)
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    created_by_id = request.form.get("created_by_id", type=int)
    created_at_raw = request.form.get("created_at", "").strip()
    report_ids = {report_id for report_id in request.form.getlist("report_ids") if report_id}

    if not title or not created_by_id or not created_at_raw or len(report_ids) < 2:
        flash("Completa titulo, creador, fecha y al menos dos reportes.", "error")
        return redirect(url_for("report_consolidation_detail", consolidation_id=consolidation.id))

    try:
        created_at = datetime.fromisoformat(created_at_raw)
    except ValueError:
        flash("La fecha de la consolidacion no es valida.", "error")
        return redirect(url_for("report_consolidation_detail", consolidation_id=consolidation.id))

    accessible_reports = build_accessible_reports_query().all()
    accessible_report_map = {str(report.id): report for report in accessible_reports}
    if any(report_id not in accessible_report_map for report_id in report_ids):
        flash("Hay reportes seleccionados invalidos.", "error")
        return redirect(url_for("report_consolidation_detail", consolidation_id=consolidation.id))

    consolidation.title = title
    consolidation.description = description or None
    consolidation.created_by_id = created_by_id
    consolidation.created_at = created_at
    consolidation.reports = [accessible_report_map[report_id] for report_id in sorted(report_ids, key=int)]
    db.session.commit()
    flash("Consolidacion actualizada.", "success")
    return redirect(url_for("report_consolidation_detail", consolidation_id=consolidation.id))


@login_required
def report_consolidation_delete(consolidation_id):
    if not superadmin_required():
        return redirect(url_for("report_consolidations"))

    consolidation = ReportConsolidation.query.get_or_404(consolidation_id)
    db.session.delete(consolidation)
    db.session.commit()
    flash("Consolidacion eliminada.", "success")
    return redirect(url_for("report_consolidations"))


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
    if not current_user.is_authenticated or not current_user.is_superadmin:
        flash("Solo un superadmin puede eliminar reportes.", "error")
        return redirect(url_for("reports"))

    report = Report.query.get_or_404(report_id)
    delete_report_record(report)
    db.session.commit()
    flash("Reporte eliminado.", "success")
    return redirect(url_for("reports"))


@login_required
def report_delete_all():
    if not current_user.is_authenticated or not current_user.is_superadmin:
        flash("Solo un superadmin puede eliminar todos los reportes.", "error")
        return redirect(url_for("reports"))

    all_reports = Report.query.all()
    deleted_count = len(all_reports)
    for report in all_reports:
        delete_report_record(report)
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
def manage_factories():
    if not superadmin_required():
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Completa el nombre de la fabrica.", "error")
        elif Factory.query.filter_by(name=name).first():
            flash("Esa fabrica ya existe.", "error")
        else:
            db.session.add(Factory(name=name))
            db.session.commit()
            flash("Fabrica creada.", "success")
        return redirect(url_for("manage_factories"))

    return render_template("manage_factories.html", factories=Factory.query.order_by(Factory.name).all())


@login_required
def edit_factory(factory_id):
    if not superadmin_required():
        return redirect(url_for("admin_dashboard"))

    factory = Factory.query.get_or_404(factory_id)
    name = request.form.get("name", "").strip()
    if not name:
        flash("Completa el nombre de la fabrica.", "error")
    elif Factory.query.filter(Factory.name == name, Factory.id != factory.id).first():
        flash("Ese nombre ya esta en uso.", "error")
    else:
        factory.name = name
        db.session.commit()
        flash("Fabrica actualizada.", "success")
    return redirect(url_for("manage_factories"))


@login_required
def delete_factory(factory_id):
    if not superadmin_required():
        return redirect(url_for("admin_dashboard"))

    factory = Factory.query.get_or_404(factory_id)
    if factory.lines:
        for line in list(factory.lines):
            for machine in list(line.machines):
                purge_machine(machine)
            db.session.delete(line)
        db.session.delete(factory)
        db.session.commit()
        flash("Fabrica eliminada junto con sus lineas, maquinas y datos asociados.", "success")
        return redirect(url_for("manage_factories"))

    db.session.delete(factory)
    db.session.commit()
    flash("Fabrica eliminada.", "success")
    return redirect(url_for("manage_factories"))


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
    line.factory_id = request.form.get("factory_id", type=int) or line.factory_id
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
        if current_user.is_superadmin:
            for machine in list(line.machines):
                purge_machine(machine)
            db.session.delete(line)
            db.session.commit()
            flash("Linea eliminada junto con sus maquinas y datos asociados.", "success")
            return redirect(url_for("manage_lines"))
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
    if machine.reports or machine.parameter_definitions:
        if current_user.is_superadmin:
            purge_machine(machine)
            db.session.commit()
            flash("Maquina eliminada junto con sus reportes y parametros.", "success")
            return redirect(url_for("manage_machines"))
        flash("No puedes eliminar una maquina que tiene reportes o parametros asociados.", "error")
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
        if current_user.is_superadmin:
            for report in list(category.reports):
                delete_report_record(report)
            db.session.delete(category)
            db.session.commit()
            flash("Categoria eliminada junto con sus reportes.", "success")
            return redirect(url_for("manage_categories"))
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

        if not username or not full_name or not password or role not in USER_ROLES:
            flash("Completa usuario, nombre, clave y rol validos.", "error")
        elif role == "superadmin" and not current_user.is_superadmin:
            flash("Solo un superadmin puede crear otro superadmin.", "error")
        elif User.query.filter_by(username=username).first():
            flash("Ese usuario ya existe.", "error")
        else:
            user = User(username=username, full_name=full_name, role=role)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash("Usuario creado.", "success")
        return redirect(url_for("manage_users"))

    assignable_roles = USER_ROLES if current_user.is_superadmin else [role for role in USER_ROLES if role != "superadmin"]
    return render_template("manage_users.html", users=User.query.order_by(User.full_name).all(), assignable_roles=assignable_roles)


@login_required
def edit_user(user_id):
    if not admin_required():
        return redirect(url_for("reports"))

    user = User.query.get_or_404(user_id)
    username = request.form.get("username", user.username).strip()
    user.full_name = request.form.get("full_name", user.full_name).strip() or user.full_name
    role = request.form.get("role", user.role).strip()
    if not username:
        flash("Completa el usuario.", "error")
        return redirect(url_for("manage_users"))
    if User.query.filter(User.username == username, User.id != user.id).first():
        flash("Ese usuario ya existe.", "error")
        return redirect(url_for("manage_users"))
    user.username = username
    if user.role == "superadmin" and not current_user.is_superadmin:
        flash("Solo un superadmin puede editar a otro superadmin.", "error")
        return redirect(url_for("manage_users"))
    if role == "superadmin" and not current_user.is_superadmin:
        flash("Solo un superadmin puede asignar ese rol.", "error")
        return redirect(url_for("manage_users"))
    if role in USER_ROLES:
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
    elif user.role == "superadmin" and not current_user.is_superadmin:
        flash("Solo un superadmin puede eliminar a otro superadmin.", "error")
    elif user.reports or MachineParameterReading.query.filter_by(created_by_id=user.id).first():
        if current_user.is_superadmin:
            purge_user(user)
            db.session.commit()
            flash("Usuario eliminado junto con todos sus datos asociados.", "success")
            return redirect(url_for("manage_users"))
        flash("No puedes eliminar un usuario que tiene reportes o parametros asociados.", "error")
    else:
        db.session.delete(user)
        db.session.commit()
        flash("Usuario eliminado.", "success")
    return redirect(url_for("manage_users"))
