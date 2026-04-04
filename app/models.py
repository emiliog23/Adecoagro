from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from . import db, login_manager

REPORT_STATUSES = [
    "Nuevo",
    "En revision",
    "Aprobado",
    "Leido por el supervisor",
    "Resuelto",
]

PARAMETER_REPORT_TYPES = [
    "Receta",
    "Mecanico",
]

USER_ROLES = [
    "usuario",
    "supervisor",
    "admin",
    "superadmin",
]


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="usuario")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    reports = db.relationship("Report", back_populates="created_by", lazy=True)
    comments = db.relationship("ReportComment", back_populates="created_by", lazy=True)
    consolidations_created = db.relationship(
        "ReportConsolidation",
        back_populates="created_by",
        cascade="all, delete-orphan",
        lazy=True,
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method="pbkdf2:sha256")

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role in {"admin", "superadmin"}

    @property
    def is_superadmin(self):
        return self.role == "superadmin"

    @property
    def is_supervisor(self):
        return self.role in {"supervisor", "admin", "superadmin"}

    @property
    def can_review_reports(self):
        return self.role in {"supervisor", "admin", "superadmin"}

    @property
    def can_manage_admin(self):
        return self.role in {"admin", "superadmin"}


class Factory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)

    lines = db.relationship("ProductionLine", back_populates="factory", lazy=True)


class ProductionLine(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    factory_id = db.Column(db.Integer, db.ForeignKey("factory.id"), nullable=False)

    factory = db.relationship("Factory", back_populates="lines")
    machines = db.relationship("Machine", back_populates="line", lazy=True)


class Machine(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    line_id = db.Column(db.Integer, db.ForeignKey("production_line.id"), nullable=False)

    line = db.relationship("ProductionLine", back_populates="machines")
    reports = db.relationship("Report", back_populates="machine", lazy=True)
    parameter_definitions = db.relationship("MachineParameter", back_populates="machine", lazy=True)


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)

    reports = db.relationship("Report", back_populates="category", lazy=True)


report_parameter_links = db.Table(
    "report_parameter_link",
    db.Column("report_id", db.Integer, db.ForeignKey("report.id"), primary_key=True),
    db.Column("parameter_id", db.Integer, db.ForeignKey("machine_parameter.id"), primary_key=True),
)


report_consolidation_links = db.Table(
    "report_consolidation_link",
    db.Column("consolidation_id", db.Integer, db.ForeignKey("report_consolidation.id"), primary_key=True),
    db.Column("report_id", db.Integer, db.ForeignKey("report.id"), primary_key=True),
)


class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    actions_taken = db.Column(db.Text, nullable=True)
    spare_parts_used = db.Column(db.Text, nullable=True)
    downtime_minutes = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(40), nullable=False, default="Nuevo")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    category_id = db.Column(db.Integer, db.ForeignKey("category.id"), nullable=False)
    machine_id = db.Column(db.Integer, db.ForeignKey("machine.id"), nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    category = db.relationship("Category", back_populates="reports")
    machine = db.relationship("Machine", back_populates="reports")
    created_by = db.relationship("User", back_populates="reports")
    attachments = db.relationship("Attachment", back_populates="report", cascade="all, delete-orphan", lazy=True)
    comments = db.relationship("ReportComment", back_populates="report", cascade="all, delete-orphan", lazy=True)
    parameters = db.relationship(
        "MachineParameter",
        secondary=report_parameter_links,
        back_populates="reports",
        lazy=True,
    )
    consolidations = db.relationship(
        "ReportConsolidation",
        secondary=report_consolidation_links,
        back_populates="reports",
        lazy=True,
    )


class ReportConsolidation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    created_by = db.relationship("User", back_populates="consolidations_created")
    reports = db.relationship(
        "Report",
        secondary=report_consolidation_links,
        back_populates="consolidations",
        lazy=True,
    )


class Attachment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    report_id = db.Column(db.Integer, db.ForeignKey("report.id"), nullable=False)

    report = db.relationship("Report", back_populates="attachments")


class ReportComment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    report_id = db.Column(db.Integer, db.ForeignKey("report.id"), nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    report = db.relationship("Report", back_populates="comments")
    created_by = db.relationship("User", back_populates="comments")


class MachineParameter(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    parameter_type = db.Column(db.String(30), nullable=False)
    unit = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    machine_id = db.Column(db.Integer, db.ForeignKey("machine.id"), nullable=False)

    machine = db.relationship("Machine", back_populates="parameter_definitions")
    readings = db.relationship(
        "MachineParameterReading",
        back_populates="parameter",
        cascade="all, delete-orphan",
        lazy=True,
        order_by="MachineParameterReading.changed_at.desc()",
    )
    reports = db.relationship(
        "Report",
        secondary=report_parameter_links,
        back_populates="parameters",
        lazy=True,
    )


class MachineParameterReading(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    current_recipe = db.Column(db.String(150), nullable=False)
    value = db.Column(db.Float, nullable=False)
    changed_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    parameter_id = db.Column(db.Integer, db.ForeignKey("machine_parameter.id"), nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    parameter = db.relationship("MachineParameter", back_populates="readings")
    created_by = db.relationship("User")


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def seed_data():
    if not Factory.query.filter_by(name="Esteril 2").first():
        factory = Factory(name="Esteril 2")
        db.session.add(factory)
        db.session.flush()

        line_a = ProductionLine(name="Linea A", factory_id=factory.id)
        line_c = ProductionLine(name="Linea C", factory_id=factory.id)
        db.session.add_all([line_a, line_c])
        db.session.flush()

        default_machines = [
            Machine(name="Llenadora A1", line_id=line_a.id),
            Machine(name="Tapadora A2", line_id=line_a.id),
            Machine(name="Etiquetadora C1", line_id=line_c.id),
            Machine(name="Empaquetadora C2", line_id=line_c.id),
        ]
        db.session.add_all(default_machines)

    if Category.query.count() == 0:
        db.session.add_all(
            [
                Category(name="Mecanico"),
                Category(name="Electrico"),
                Category(name="Calidad"),
                Category(name="Seguridad"),
                Category(name="Produccion"),
            ]
        )

    if not User.query.filter_by(username="admin").first():
        admin = User(username="admin", full_name="Administrador General", role="admin")
        admin.set_password("admin123")
        db.session.add(admin)

    if not User.query.filter_by(username="superadmin").first():
        superadmin = User(username="superadmin", full_name="Super Administrador", role="superadmin")
        superadmin.set_password("superadmin123")
        db.session.add(superadmin)

    if not User.query.filter_by(username="supervisor").first():
        supervisor = User(username="supervisor", full_name="Supervisor Turno", role="supervisor")
        supervisor.set_password("supervisor123")
        db.session.add(supervisor)

    if not User.query.filter_by(username="operador").first():
        operator = User(username="operador", full_name="Operador Planta", role="usuario")
        operator.set_password("operador123")
        db.session.add(operator)

    default_users = [
        ("alcides.dominguez", "Alcides Dominguez", "usuario", "alcides123"),
        ("juan.burgueno", "Juan Burgueño", "usuario", "juan123"),
        ("sergio.dabi", "Sergio Dabi", "usuario", "sergio123"),
        ("gustavo.enecoiz", "Gustavo Enecoiz", "usuario", "gustavo123"),
    ]

    for username, full_name, role, password in default_users:
        if not User.query.filter_by(username=username).first():
            user = User(username=username, full_name=full_name, role=role)
            user.set_password(password)
            db.session.add(user)

    db.session.commit()


def ensure_schema():
    columns = {column["name"] for column in db.session.execute(db.text("PRAGMA table_info(report)")).mappings()}
    migrations = []

    if "actions_taken" not in columns:
        migrations.append("ALTER TABLE report ADD COLUMN actions_taken TEXT")
    if "spare_parts_used" not in columns:
        migrations.append("ALTER TABLE report ADD COLUMN spare_parts_used TEXT")
    if "downtime_minutes" not in columns:
        migrations.append("ALTER TABLE report ADD COLUMN downtime_minutes INTEGER")

    for statement in migrations:
        db.session.execute(db.text(statement))

    if migrations:
        db.session.commit()
