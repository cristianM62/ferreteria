import os
from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps
from uuid import uuid4

from flask import Flask, abort, current_app, flash, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, inspect, text
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()


def money(value):
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise ValueError("Importe invalido")


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(60), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # owner | employee
    active = db.Column(db.Boolean, default=True, nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)


class Subcategory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"), nullable=False)
    category = db.relationship("Category")
    __table_args__ = (db.UniqueConstraint("name", "category_id", name="uq_subcategory_category"),)


class Supplier(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), unique=True, nullable=False)
    company_name = db.Column(db.String(160), default="")
    phone = db.Column(db.String(60), default="")
    email = db.Column(db.String(160), default="")
    notes = db.Column(db.String(500), default="")
    active = db.Column(db.Boolean, default=True, nullable=False)


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(60), unique=True, nullable=False)
    barcode = db.Column(db.String(80), unique=True, nullable=True)
    name = db.Column(db.String(160), nullable=False)
    description = db.Column(db.String(500), default="")
    purchase_price = db.Column(db.Numeric(14, 2), default=0, nullable=False)
    sale_price = db.Column(db.Numeric(14, 2), nullable=False)
    stock = db.Column(db.Numeric(14, 3), default=0, nullable=False)
    minimum_stock = db.Column(db.Numeric(14, 3), default=0, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"), nullable=True)
    subcategory_id = db.Column(db.Integer, db.ForeignKey("subcategory.id"), nullable=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey("supplier.id"), nullable=True)
    units_per_box = db.Column(db.Integer, default=1, nullable=False)
    closed_boxes = db.Column(db.Integer, default=0, nullable=False)
    loose_units = db.Column(db.Integer, default=0, nullable=False)
    box_price = db.Column(db.Numeric(14, 2), default=0, nullable=False)
    unit_price = db.Column(db.Numeric(14, 2), default=0, nullable=False)
    has_box_presentation = db.Column(db.Boolean, default=False, nullable=False)
    image_filename = db.Column(db.String(100), nullable=True)
    category = db.relationship("Category")
    subcategory = db.relationship("Subcategory")
    supplier = db.relationship("Supplier", backref="products")

    @property
    def available_units(self):
        return self.closed_boxes * self.units_per_box + self.loose_units

    def sync_stock(self):
        self.stock = Decimal(self.available_units)


class InventoryMovement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    quantity = db.Column(db.Numeric(14, 3), nullable=False)
    movement_type = db.Column(db.String(30), nullable=False)
    reason = db.Column(db.String(300), nullable=False)
    reference = db.Column(db.String(80), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    product = db.relationship("Product")
    user = db.relationship("User")


class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    first_name = db.Column(db.String(100), default="", nullable=False)
    last_name = db.Column(db.String(100), default="", nullable=False)
    dni = db.Column(db.String(30), unique=True, nullable=True)
    phone = db.Column(db.String(60), default="")
    address = db.Column(db.String(250), default="")
    debt_balance = db.Column(db.Numeric(14, 2), default=0, nullable=False)
    condition = db.Column(db.String(30), default="Al dia", nullable=False)
    discount_percent = db.Column(db.Numeric(5, 2), default=0, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)


class Sale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    total = db.Column(db.Numeric(14, 2), nullable=False)
    cash_received = db.Column(db.Numeric(14, 2), default=0, nullable=False)
    change_due = db.Column(db.Numeric(14, 2), default=0, nullable=False)
    status = db.Column(db.String(20), default="CONFIRMADA", nullable=False)
    cancelled_at = db.Column(db.DateTime, nullable=True)
    cancellation_reason = db.Column(db.String(300), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    customer = db.relationship("Customer")
    user = db.relationship("User")
    items = db.relationship("SaleItem", back_populates="sale", cascade="all, delete-orphan")
    payments = db.relationship("Payment", back_populates="sale", cascade="all, delete-orphan")


class SaleItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("sale.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    quantity = db.Column(db.Numeric(14, 3), nullable=False)
    unit_price = db.Column(db.Numeric(14, 2), nullable=False)
    subtotal = db.Column(db.Numeric(14, 2), nullable=False)
    presentation = db.Column(db.String(20), nullable=True)
    sale_quantity = db.Column(db.Numeric(14, 3), nullable=True)
    discount_percent = db.Column(db.Numeric(5, 2), default=0, nullable=False)
    sale = db.relationship("Sale", back_populates="items")
    product = db.relationship("Product")


class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("sale.id"), nullable=False)
    method = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Numeric(14, 2), nullable=False)
    sale = db.relationship("Sale", back_populates="payments")


class AuditEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    action = db.Column(db.String(100), nullable=False)
    entity = db.Column(db.String(60), nullable=False)
    entity_id = db.Column(db.String(60), nullable=False)
    details = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    user = db.relationship("User")


def current_user():
    uid = session.get("user_id")
    return db.session.get(User, uid) if uid else None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def owner_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user() or current_user().role != "owner":
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def audit(user, action, entity, entity_id, details):
    db.session.add(AuditEvent(user_id=user.id, action=action, entity=entity, entity_id=str(entity_id), details=details))


def save_product_image(upload):
    """Valida y guarda una imagen con un nombre aleatorio seguro."""
    if not upload or not upload.filename:
        return None
    data = upload.read(5 * 1024 * 1024 + 1)
    if len(data) > 5 * 1024 * 1024:
        raise ValueError("La imagen no puede superar los 5 MB.")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        extension = "png"
    elif data.startswith(b"\xff\xd8\xff"):
        extension = "jpg"
    elif len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        extension = "webp"
    else:
        raise ValueError("La imagen debe estar en formato JPG, PNG o WebP.")
    upload_folder = current_app.config["PRODUCT_IMAGE_UPLOAD_FOLDER"]
    os.makedirs(upload_folder, exist_ok=True)
    filename = f"{uuid4().hex}.{extension}"
    with open(os.path.join(upload_folder, filename), "wb") as image_file:
        image_file.write(data)
    return filename


def delete_product_image(filename):
    if not filename:
        return
    safe_filename = os.path.basename(filename)
    image_path = os.path.join(current_app.config["PRODUCT_IMAGE_UPLOAD_FOLDER"], safe_filename)
    if os.path.isfile(image_path):
        os.remove(image_path)


def ensure_schema():
    """Actualiza instalaciones SQLite anteriores sin borrar ventas ni stock."""
    additions = {
        "product": {
            "subcategory_id": "INTEGER", "supplier_id": "INTEGER", "units_per_box": "INTEGER NOT NULL DEFAULT 1",
            "closed_boxes": "INTEGER NOT NULL DEFAULT 0", "loose_units": "INTEGER NOT NULL DEFAULT 0",
            "box_price": "NUMERIC(14,2) NOT NULL DEFAULT 0", "unit_price": "NUMERIC(14,2) NOT NULL DEFAULT 0",
            "has_box_presentation": "BOOLEAN NOT NULL DEFAULT 0",
            "image_filename": "VARCHAR(100)",
        },
        "customer": {"discount_percent": "NUMERIC(5,2) NOT NULL DEFAULT 0", "first_name": "VARCHAR(100) NOT NULL DEFAULT ''", "last_name": "VARCHAR(100) NOT NULL DEFAULT ''", "dni": "VARCHAR(30)", "address": "VARCHAR(250) NOT NULL DEFAULT ''", "debt_balance": "NUMERIC(14,2) NOT NULL DEFAULT 0"},
        "supplier": {"company_name": "VARCHAR(160) NOT NULL DEFAULT ''"},
        "sale_item": {"presentation": "VARCHAR(20)", "sale_quantity": "NUMERIC(14,3)", "discount_percent": "NUMERIC(5,2) NOT NULL DEFAULT 0"},
        "sale": {"cash_received": "NUMERIC(14,2) NOT NULL DEFAULT 0", "change_due": "NUMERIC(14,2) NOT NULL DEFAULT 0"},
    }
    inspector = inspect(db.engine)
    existing_tables = set(inspector.get_table_names())
    for table, columns in additions.items():
        if table not in existing_tables:
            continue
        existing_columns = {column["name"] for column in inspector.get_columns(table)}
        for name, definition in columns.items():
            if name not in existing_columns:
                db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))
    # Productos creados antes de esta actualización se conservan como unidades sueltas.
    db.session.execute(text("UPDATE product SET units_per_box = 1 WHERE units_per_box IS NULL OR units_per_box < 1"))
    db.session.execute(text("UPDATE product SET has_box_presentation = 1 WHERE units_per_box > 1 AND has_box_presentation = 0"))
    db.session.execute(text("UPDATE product SET closed_boxes = CAST(stock AS INTEGER), loose_units = 0, box_price = sale_price, unit_price = sale_price WHERE closed_boxes = 0 AND loose_units = 0 AND stock > 0"))
    db.session.commit()


def seed_data():
    if not User.query.first():
        owner = User(username="dueno", role="owner")
        owner.set_password("Cambiar123!")
        employee = User(username="empleado", role="employee")
        employee.set_password("Empleado123!")
        db.session.add_all([owner, employee])
        db.session.commit()


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", "desarrollo-cambiar-antes-de-produccion"),
        SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL", "sqlite:///ferresoft.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        MAX_CONTENT_LENGTH=6 * 1024 * 1024,
        PRODUCT_IMAGE_UPLOAD_FOLDER=os.path.join(app.static_folder, "uploads", "products"),
    )
    if test_config:
        app.config.update(test_config)
    db.init_app(app)

    @app.context_processor
    def inject_globals():
        return {"current_user": current_user(), "today": datetime.now()}

    @app.template_filter("ars")
    def ars_filter(value):
        return f"$ {Decimal(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    @app.route("/")
    @login_required
    def dashboard():
        confirmed = Sale.query.filter_by(status="CONFIRMADA")
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        daily_total = confirmed.filter(Sale.created_at >= today_start).with_entities(func.coalesce(func.sum(Sale.total), 0)).scalar()
        critical = Product.query.filter(Product.active.is_(True), Product.stock <= Product.minimum_stock).count()
        return render_template("dashboard.html", daily_total=daily_total, critical=critical, sale_count=confirmed.count())

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            user = User.query.filter_by(username=request.form.get("username", "").strip()).first()
            if user and user.active and user.verify_password(request.form.get("password", "")):
                session.clear(); session["user_id"] = user.id
                return redirect(url_for("dashboard"))
            flash("Usuario o contraseña incorrectos.", "error")
        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear(); return redirect(url_for("login"))

    @app.route("/products")
    @login_required
    def products():
        query = request.args.get("q", "").strip()
        products_query = Product.query.filter_by(active=True).order_by(Product.name)
        if query:
            pattern = f"%{query}%"
            products_query = products_query.filter(db.or_(Product.name.ilike(pattern), Product.code.ilike(pattern), Product.barcode.ilike(pattern)))
        return render_template("products.html", products=products_query.all(), query=query)

    @app.route("/products/new", methods=["GET", "POST"])
    @owner_required
    def product_new():
        form_data, field_errors = {}, {}
        if request.method == "POST":
            form_data = request.form.to_dict()
            new_image_filename = None
            try:
                code = request.form.get("code", "").strip(); barcode = request.form.get("barcode", "").strip() or None
                if Product.query.filter_by(code=code).first(): field_errors["code"] = "Ya existe un producto con este código."
                if barcode and Product.query.filter_by(barcode=barcode).first(): field_errors["barcode"] = "Ya existe un producto con este código de barras."
                if field_errors: raise ValueError("Revise los campos marcados.")
                units_per_box = int(request.form.get("units_per_box") or 1)
                closed_boxes = int(request.form.get("closed_boxes") or 0)
                loose_units = int(request.form.get("loose_units") or 0)
                if units_per_box < 1 or closed_boxes < 0 or loose_units < 0: raise ValueError("Las cantidades no pueden ser negativas")
                has_box_presentation = "has_box_presentation" in request.form
                box_price = money(request.form.get("box_price") or 0)
                unit_price = money(request.form["unit_price"])
                if has_box_presentation and box_price <= 0: raise ValueError("Debe indicar el precio por caja")
                new_image_filename = save_product_image(request.files.get("image"))
                product = Product(code=code, barcode=barcode,
                    name=request.form["name"].strip(), description=request.form.get("description", "").strip(),
                    purchase_price=money(request.form.get("purchase_price") or 0), sale_price=box_price if has_box_presentation else unit_price,
                    box_price=box_price, unit_price=unit_price, has_box_presentation=has_box_presentation,
                    units_per_box=units_per_box, closed_boxes=closed_boxes, loose_units=loose_units,
                    category_id=request.form.get("category_id") or None, subcategory_id=request.form.get("subcategory_id") or None,
                    supplier_id=request.form.get("supplier_id") or None, stock=Decimal("0"), minimum_stock=Decimal(request.form.get("minimum_stock", 0)),
                    image_filename=new_image_filename)
                product.sync_stock()
                db.session.add(product); db.session.flush()
                if product.stock:
                    db.session.add(InventoryMovement(product_id=product.id, user_id=current_user().id, quantity=product.stock, movement_type="ALTA", reason="Stock inicial", reference=None))
                audit(current_user(), "CREAR_PRODUCTO", "product", product.id, product.name)
                db.session.commit(); flash("Producto creado.", "success"); return redirect(url_for("products"))
            except Exception as exc:
                db.session.rollback()
                if new_image_filename: delete_product_image(new_image_filename)
                flash(f"No se pudo crear el producto: {exc}", "error")
        return render_template("product_form.html", product=None, form_data=form_data, field_errors=field_errors, categories=Category.query.order_by(Category.name).all(), subcategories=Subcategory.query.order_by(Subcategory.name).all(), suppliers=Supplier.query.filter_by(active=True).order_by(Supplier.name).all())

    @app.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
    @owner_required
    def product_edit(product_id):
        product = db.get_or_404(Product, product_id)
        if request.method == "POST":
            new_image_filename = None
            old_image_filename = product.image_filename
            try:
                old_price = product.box_price
                product.code = request.form["code"].strip(); product.barcode = request.form.get("barcode", "").strip() or None
                product.name = request.form["name"].strip(); product.description = request.form.get("description", "").strip()
                product.purchase_price = money(request.form.get("purchase_price") or 0); product.box_price = money(request.form.get("box_price") or 0); product.unit_price = money(request.form["unit_price"]); product.has_box_presentation = "has_box_presentation" in request.form; product.sale_price = product.box_price or product.unit_price
                product.minimum_stock = Decimal(request.form.get("minimum_stock", 0)); product.active = "active" in request.form
                product.category_id = request.form.get("category_id") or None; product.subcategory_id = request.form.get("subcategory_id") or None; product.supplier_id = request.form.get("supplier_id") or None
                if int(request.form.get("units_per_box") or 1) < 1: raise ValueError("Unidades por caja debe ser mayor a cero")
                product.units_per_box = int(request.form.get("units_per_box") or 1)
                if not product.has_box_presentation:
                    product.loose_units += product.closed_boxes * product.units_per_box
                    product.closed_boxes = 0
                    product.units_per_box = 1
                    product.box_price = Decimal("0")
                if request.files.get("image") and request.files["image"].filename:
                    new_image_filename = save_product_image(request.files["image"])
                    product.image_filename = new_image_filename
                product.sync_stock()
                audit(current_user(), "EDITAR_PRODUCTO", "product", product.id, product.name)
                if old_price != product.box_price: audit(current_user(), "CAMBIAR_PRECIO", "product", product.id, f"{old_price} a {product.box_price}")
                db.session.commit()
                if new_image_filename and old_image_filename: delete_product_image(old_image_filename)
                flash("Producto actualizado.", "success"); return redirect(url_for("products"))
            except Exception as exc:
                db.session.rollback()
                if new_image_filename: delete_product_image(new_image_filename)
                flash(f"No se pudo actualizar: {exc}", "error")
        return render_template("product_form.html", product=product, form_data={}, field_errors={}, categories=Category.query.order_by(Category.name).all(), subcategories=Subcategory.query.order_by(Subcategory.name).all(), suppliers=Supplier.query.filter_by(active=True).order_by(Supplier.name).all())

    @app.route("/products/<int:product_id>/adjust", methods=["POST"])
    @owner_required
    def product_adjust(product_id):
        product = db.get_or_404(Product, product_id)
        try:
            quantity = int(request.form["quantity"])
            reason = request.form["reason"].strip()
            if not quantity or not reason: raise ValueError("Cantidad y motivo son obligatorios")
            if product.available_units + quantity < 0: raise ValueError("El ajuste no puede dejar stock negativo")
            product.loose_units += quantity
            if product.loose_units < 0:
                boxes_to_open = (-product.loose_units + product.units_per_box - 1) // product.units_per_box
                if product.closed_boxes < boxes_to_open: raise ValueError("No hay cajas suficientes")
                product.closed_boxes -= boxes_to_open; product.loose_units += boxes_to_open * product.units_per_box
            product.sync_stock()
            db.session.add(InventoryMovement(product_id=product.id, user_id=current_user().id, quantity=quantity, movement_type="AJUSTE", reason=reason, reference=None))
            audit(current_user(), "AJUSTAR_STOCK", "product", product.id, f"{quantity}: {reason}")
            db.session.commit(); flash("Stock ajustado.", "success")
        except Exception as exc:
            db.session.rollback(); flash(f"No se pudo ajustar el stock: {exc}", "error")
        return redirect(url_for("products"))

    @app.route("/products/<int:product_id>/restock", methods=["GET", "POST"])
    @owner_required
    def product_restock(product_id):
        product = db.get_or_404(Product, product_id)
        form_data = {}
        if request.method == "POST":
            form_data = request.form.to_dict()
            try:
                add_boxes = int(request.form.get("add_boxes") or 0)
                add_units = int(request.form.get("add_units") or 0)
                if add_boxes < 0 or add_units < 0: raise ValueError("La reposición no puede ser negativa")
                added = add_units
                if product.has_box_presentation:
                    added += add_boxes * product.units_per_box
                    product.closed_boxes += add_boxes
                product.loose_units += add_units
                if added <= 0: raise ValueError("Indique una cantidad a reponer")
                old_purchase, old_unit, old_box = product.purchase_price, product.unit_price, product.box_price
                product.purchase_price = money(request.form.get("purchase_price") or 0)
                product.unit_price = money(request.form["unit_price"])
                if product.has_box_presentation:
                    product.box_price = money(request.form["box_price"])
                    if product.box_price <= 0: raise ValueError("El precio por caja debe ser mayor a cero")
                product.sale_price = product.box_price if product.has_box_presentation else product.unit_price
                product.sync_stock()
                db.session.add(InventoryMovement(product_id=product.id, user_id=current_user().id, quantity=added, movement_type="REPOSICION", reason="Reposición de mercadería", reference=None))
                audit(current_user(), "REPOSICION", "product", product.id, f"+{added} unidades; compra {old_purchase}->{product.purchase_price}; venta unidad {old_unit}->{product.unit_price}; venta caja {old_box}->{product.box_price}")
                db.session.commit(); flash("Reposición y precios actualizados.", "success"); return redirect(url_for("products"))
            except Exception as exc:
                db.session.rollback(); flash(f"No se pudo registrar la reposición: {exc}", "error")
        return render_template("restock_form.html", product=product, form_data=form_data)

    @app.route("/products/<int:product_id>/delete", methods=["POST"])
    @owner_required
    def product_delete(product_id):
        product = db.get_or_404(Product, product_id)
        try:
            # Baja lógica: preserva el historial de ventas, remitos y auditoría.
            product.active = False
            audit(current_user(), "ELIMINAR_PRODUCTO", "product", product.id, f"Baja lógica: {product.name}")
            db.session.commit()
            flash("Producto eliminado del catálogo. Su historial se conserva.", "success")
        except Exception as exc:
            db.session.rollback(); flash(f"No se pudo eliminar el producto: {exc}", "error")
        return redirect(url_for("products"))

    @app.route("/sales/new")
    @login_required
    def sale_new():
        return render_template("sale_new.html", products=Product.query.filter_by(active=True).order_by(Product.name).all(), customers=Customer.query.filter_by(active=True).order_by(Customer.name).all())

    @app.route("/suppliers", methods=["GET", "POST"])
    @owner_required
    def suppliers():
        form_data, field_errors = {}, {}
        if request.method == "POST":
            form_data = request.form.to_dict()
            try:
                name = request.form.get("name", "").strip()
                if Supplier.query.filter_by(name=name).first(): field_errors["name"] = "Ya existe un proveedor con este nombre."
                if field_errors: raise ValueError("Revise los campos marcados.")
                supplier = Supplier(name=name, company_name=request.form.get("company_name", "").strip(), phone=request.form.get("phone", "").strip(), email=request.form.get("email", "").strip(), notes=request.form.get("notes", "").strip())
                db.session.add(supplier); db.session.flush(); audit(current_user(), "CREAR_PROVEEDOR", "supplier", supplier.id, supplier.name)
                db.session.commit(); flash("Proveedor agregado.", "success")
            except Exception as exc:
                db.session.rollback(); flash(f"No se pudo agregar el proveedor: {exc}", "error")
        return render_template("suppliers.html", suppliers=Supplier.query.order_by(Supplier.name).all(), form_data=form_data, field_errors=field_errors)

    @app.route("/suppliers/<int:supplier_id>/edit", methods=["GET", "POST"])
    @owner_required
    def supplier_edit(supplier_id):
        supplier = db.get_or_404(Supplier, supplier_id)
        if request.method == "POST":
            try:
                supplier.name = request.form["name"].strip(); supplier.company_name = request.form.get("company_name", "").strip()
                supplier.phone = request.form.get("phone", "").strip(); supplier.email = request.form.get("email", "").strip(); supplier.notes = request.form.get("notes", "").strip()
                audit(current_user(), "EDITAR_PROVEEDOR", "supplier", supplier.id, supplier.name); db.session.commit(); flash("Proveedor actualizado.", "success")
                return redirect(url_for("suppliers"))
            except Exception as exc:
                db.session.rollback(); flash(f"No se pudo actualizar: {exc}", "error")
        return render_template("supplier_form.html", supplier=supplier)

    @app.route("/suppliers/<int:supplier_id>")
    @owner_required
    def supplier_detail(supplier_id):
        supplier = db.get_or_404(Supplier, supplier_id)
        products = Product.query.filter_by(supplier_id=supplier.id, active=True).order_by(Product.name).all()
        return render_template("supplier_detail.html", supplier=supplier, products=products)

    @app.route("/suppliers/<int:supplier_id>/products/<int:product_id>/remove", methods=["POST"])
    @owner_required
    def supplier_remove_product(supplier_id, product_id):
        supplier = db.get_or_404(Supplier, supplier_id)
        product = db.get_or_404(Product, product_id)
        if product.supplier_id != supplier.id:
            abort(404)
        product.supplier_id = None
        audit(current_user(), "QUITAR_PRODUCTO_PROVEEDOR", "product", product.id, f"Producto quitado de {supplier.name}")
        db.session.commit()
        flash("Producto quitado del proveedor. El producto continúa disponible en el catálogo.", "success")
        return redirect(url_for("supplier_detail", supplier_id=supplier.id))

    @app.route("/catalog", methods=["GET", "POST"])
    @owner_required
    def catalog():
        try:
            if request.method == "POST":
                action = request.form.get("action")
                if action == "category":
                    category = Category(name=request.form["name"].strip())
                    db.session.add(category); db.session.flush(); audit(current_user(), "CREAR_CATEGORIA", "category", category.id, category.name)
                elif action == "subcategory":
                    subcategory = Subcategory(name=request.form["name"].strip(), category_id=int(request.form["category_id"]))
                    db.session.add(subcategory); db.session.flush(); audit(current_user(), "CREAR_SUBCATEGORIA", "subcategory", subcategory.id, subcategory.name)
                else: raise ValueError("Acción no válida")
                db.session.commit(); flash("Catálogo actualizado.", "success")
            return render_template("catalog.html", categories=Category.query.order_by(Category.name).all(), subcategories=Subcategory.query.order_by(Subcategory.name).all())
        except Exception as exc:
            db.session.rollback(); flash(f"No se pudo actualizar el catálogo: {exc}", "error")
            return redirect(url_for("catalog"))

    @app.route("/customers", methods=["GET", "POST"])
    @login_required
    def customers():
        form_data, field_errors = {}, {}
        if request.method == "POST":
            form_data = request.form.to_dict()
            try:
                discount = Decimal(request.form.get("discount_percent", 0))
                if not 0 <= discount <= 100: raise ValueError("El descuento debe estar entre 0 y 100")
                first_name = request.form["first_name"].strip()
                last_name = request.form["last_name"].strip()
                dni = request.form.get("dni", "").strip() or None
                if not first_name or not last_name: raise ValueError("Nombre y apellido son obligatorios")
                if dni and Customer.query.filter_by(dni=dni).first(): field_errors["dni"] = "Ya existe un cliente con este DNI."
                if field_errors: raise ValueError("Revise los campos marcados.")
                customer = Customer(name=f"{last_name}, {first_name}", first_name=first_name, last_name=last_name, dni=dni, phone=request.form.get("phone", "").strip(), address=request.form.get("address", "").strip(), condition=request.form.get("condition", "Al dia"), discount_percent=discount)
                db.session.add(customer); db.session.flush(); audit(current_user(), "CREAR_CLIENTE", "customer", customer.id, customer.name)
                db.session.commit(); flash("Cliente agregado.", "success")
            except Exception as exc:
                db.session.rollback(); flash(f"No se pudo agregar el cliente: {exc}", "error")
        return render_template("customers.html", customers=Customer.query.order_by(Customer.name).all(), form_data=form_data, field_errors=field_errors)

    @app.route("/customers/<int:customer_id>/edit", methods=["GET", "POST"])
    @owner_required
    def customer_edit(customer_id):
        customer = db.get_or_404(Customer, customer_id)
        if request.method == "POST":
            try:
                customer.first_name = request.form["first_name"].strip(); customer.last_name = request.form["last_name"].strip()
                customer.name = f"{customer.last_name}, {customer.first_name}"; customer.phone = request.form.get("phone", "").strip(); customer.address = request.form.get("address", "").strip()
                discount = Decimal(request.form.get("discount_percent") or 0)
                if not 0 <= discount <= 100: raise ValueError("El descuento debe estar entre 0 y 100")
                customer.discount_percent = discount; audit(current_user(), "EDITAR_CLIENTE", "customer", customer.id, customer.name)
                db.session.commit(); flash("Cliente actualizado.", "success"); return redirect(url_for("customers"))
            except Exception as exc:
                db.session.rollback(); flash(f"No se pudo actualizar: {exc}", "error")
        return render_template("customer_form.html", customer=customer)

    @app.route("/sales", methods=["POST"])
    @login_required
    def sale_create():
        try:
            cart = request.get_json(silent=True) or {}
            lines = cart.get("items", [])
            if not lines: raise ValueError("El carrito está vacío")
            payments = cart.get("payments", [])
            if not payments: raise ValueError("Debe registrar un pago")
            customer = db.session.get(Customer, int(cart["customer_id"])) if cart.get("customer_id") else None
            sale = Sale(user_id=current_user().id, customer_id=customer.id if customer else None, total=0)
            db.session.add(sale); db.session.flush()
            total = Decimal("0")
            for line in lines:
                product_id = line.get("product_id", line.get("id"))
                if not product_id: raise ValueError("El carrito contiene un producto sin identificador")
                product = db.session.get(Product, int(product_id))
                if not product or not product.active: raise ValueError("Producto inválido o inactivo")
                presentation = line.get("presentation")
                sale_quantity = Decimal(str(line["quantity"]))
                quantity = sale_quantity * product.units_per_box if presentation == "CAJA" else sale_quantity
                if quantity <= 0: raise ValueError("Cantidad inválida")
                if presentation not in {"CAJA", "UNIDAD"}: raise ValueError("Debe seleccionar caja o unidad")
                if presentation == "CAJA" and not product.has_box_presentation: raise ValueError(f"{product.name} se vende sólo por unidad")
                if product.available_units < quantity: raise ValueError(f"Stock insuficiente para {product.name}")
                if presentation == "CAJA":
                    if sale_quantity != int(sale_quantity) or product.closed_boxes < int(sale_quantity): raise ValueError(f"No hay cajas cerradas suficientes para {product.name}")
                    product.closed_boxes -= int(sale_quantity); base_price = product.box_price
                else:
                    units = int(sale_quantity)
                    if sale_quantity != units: raise ValueError("Las unidades deben ser enteras")
                    if product.loose_units < units:
                        boxes_to_open = (units - product.loose_units + product.units_per_box - 1) // product.units_per_box
                        product.closed_boxes -= boxes_to_open; product.loose_units += boxes_to_open * product.units_per_box
                    product.loose_units -= units; base_price = product.unit_price
                product.sync_stock()
                discount = Decimal(customer.discount_percent if customer else 0)
                unit_price = (base_price * (Decimal("1") - discount / Decimal("100"))).quantize(Decimal("0.01"))
                subtotal = (unit_price * sale_quantity).quantize(Decimal("0.01")); total += subtotal
                db.session.add(SaleItem(sale_id=sale.id, product_id=product.id, quantity=quantity, sale_quantity=sale_quantity, presentation=presentation, discount_percent=discount, unit_price=unit_price, subtotal=subtotal))
                db.session.add(InventoryMovement(product_id=product.id, user_id=current_user().id, quantity=-quantity, movement_type="VENTA", reason=f"Venta {presentation.lower()}", reference=f"V-{sale.id}"))
            allowed_methods = {"EFECTIVO", "DEBITO", "CREDITO", "TRANSFERENCIA", "QR"}
            parsed_payments = []
            for payment in payments:
                method = payment["method"]
                amount = money(payment["amount"])
                if method not in allowed_methods: raise ValueError("Medio de pago inválido")
                if amount <= 0: raise ValueError("Los importes de pago deben ser mayores a cero")
                parsed_payments.append([method, amount])
            paid = sum((amount for _, amount in parsed_payments), Decimal("0"))
            if paid < total: raise ValueError(f"Pago insuficiente. Faltan {(total - paid):.2f}")
            change_due = (paid - total).quantize(Decimal("0.01"))
            cash_received = sum((amount for method, amount in parsed_payments if method == "EFECTIVO"), Decimal("0"))
            if change_due > cash_received: raise ValueError("El importe excedente sólo puede corresponder a un pago en efectivo")
            remaining_change = change_due
            for method, amount in parsed_payments:
                applied_amount = amount
                if method == "EFECTIVO" and remaining_change > 0:
                    reduction = min(applied_amount, remaining_change)
                    applied_amount -= reduction; remaining_change -= reduction
                if applied_amount > 0:
                    db.session.add(Payment(sale_id=sale.id, method=method, amount=applied_amount))
            sale.total = total
            sale.cash_received = cash_received
            sale.change_due = change_due
            audit(current_user(), "CONFIRMAR_VENTA", "sale", sale.id, f"Total {total}")
            db.session.commit()
            return {"ok": True, "sale_id": sale.id, "change_due": str(change_due), "redirect": url_for("sale_receipt", sale_id=sale.id)}
        except Exception as exc:
            db.session.rollback(); return {"ok": False, "error": str(exc)}, 400

    @app.route("/sales")
    @login_required
    def sales():
        sales = Sale.query.order_by(Sale.created_at.desc()).limit(100).all()
        return render_template("sales.html", sales=sales)

    @app.route("/sales/<int:sale_id>/receipt")
    @login_required
    def sale_receipt(sale_id):
        return render_template("receipt.html", sale=db.get_or_404(Sale, sale_id))

    @app.route("/sales/<int:sale_id>/cancel", methods=["POST"])
    @login_required
    def sale_cancel(sale_id):
        sale = db.get_or_404(Sale, sale_id)
        try:
            if sale.status != "CONFIRMADA": raise ValueError("La venta ya fue anulada")
            reason = request.form.get("reason", "").strip()
            if not reason: raise ValueError("Debe indicar un motivo")
            for item in sale.items:
                if item.presentation == "CAJA": item.product.closed_boxes += int(item.sale_quantity)
                else: item.product.loose_units += int(item.sale_quantity or item.quantity)
                item.product.sync_stock()
                db.session.add(InventoryMovement(product_id=item.product_id, user_id=current_user().id, quantity=item.quantity, movement_type="ANULACION", reason=reason, reference=f"V-{sale.id}"))
            sale.status = "ANULADA"; sale.cancelled_at = datetime.now(); sale.cancellation_reason = reason
            audit(current_user(), "ANULAR_VENTA", "sale", sale.id, reason)
            db.session.commit(); flash("Ticket anulado y stock restituido.", "success")
        except Exception as exc:
            db.session.rollback(); flash(f"No se pudo anular: {exc}", "error")
        return redirect(url_for("sales"))

    @app.route("/reports/sales")
    @login_required
    def sales_report():
        confirmed = Sale.query.filter_by(status="CONFIRMADA")
        total = confirmed.with_entities(func.coalesce(func.sum(Sale.total), 0)).scalar()
        by_payment = db.session.query(Payment.method, func.sum(Payment.amount)).join(Sale).filter(Sale.status == "CONFIRMADA").group_by(Payment.method).all()
        sales = confirmed.order_by(Sale.created_at.desc()).all()
        return render_template(
            "report_sales.html",
            total=total,
            count=confirmed.count(),
            by_payment=by_payment,
            daily_summaries=build_daily_sales_summaries(sales),
            today=datetime.now().strftime("%Y-%m-%d"),
        )

    @app.route("/reports/sales/daily/<report_date>")
    @login_required
    def daily_sales_report(report_date):
        try:
            selected_date = datetime.strptime(report_date, "%Y-%m-%d").date()
        except ValueError:
            abort(404)
        start = datetime.combine(selected_date, time.min)
        end = start + timedelta(days=1)
        sales = Sale.query.filter(
            Sale.status == "CONFIRMADA",
            Sale.created_at >= start,
            Sale.created_at < end,
        ).order_by(Sale.created_at).all()
        summaries = build_daily_sales_summaries(sales)
        day = summaries[0] if summaries else {
            "date": selected_date,
            "sales": [],
            "sale_count": 0,
            "total": Decimal("0"),
            "products": [],
            "payments": [],
        }
        return render_template("daily_close.html", day=day, generated_at=datetime.now())

    @app.route("/reports/sales/range")
    @login_required
    def sales_range_report():
        try:
            start_date = datetime.strptime(request.args["start_date"], "%Y-%m-%d").date()
            end_date = datetime.strptime(request.args["end_date"], "%Y-%m-%d").date()
            if start_date > end_date:
                raise ValueError("La fecha desde no puede ser posterior a la fecha hasta.")
        except KeyError:
            flash("Seleccione la fecha desde y la fecha hasta.", "error")
            return redirect(url_for("sales_report"))
        except ValueError as exc:
            message = str(exc) if "posterior" in str(exc) else "Las fechas seleccionadas no son válidas."
            flash(message, "error")
            return redirect(url_for("sales_report"))

        start = datetime.combine(start_date, time.min)
        end = datetime.combine(end_date, time.min) + timedelta(days=1)
        sales = Sale.query.filter(
            Sale.status == "CONFIRMADA",
            Sale.created_at >= start,
            Sale.created_at < end,
        ).order_by(Sale.created_at.desc()).all()
        daily_summaries = build_daily_sales_summaries(sales)
        total = sum((Decimal(sale.total) for sale in sales), Decimal("0"))
        payments = {}
        for sale in sales:
            for payment in sale.payments:
                payments[payment.method] = payments.get(payment.method, Decimal("0")) + Decimal(payment.amount)
        return render_template(
            "range_sales_report.html",
            start_date=start_date,
            end_date=end_date,
            sales=sales,
            total=total,
            payments=sorted(payments.items()),
            daily_summaries=daily_summaries,
            generated_at=datetime.now(),
        )

    with app.app_context():
        db.create_all(); ensure_schema(); seed_data()
    return app


def build_daily_sales_summaries(sales):
    """Agrupa ventas confirmadas por fecha, producto y medio de pago."""
    days = {}
    for sale in sales:
        sale_date = sale.created_at.date()
        day = days.setdefault(sale_date, {
            "date": sale_date,
            "sales": [],
            "sale_count": 0,
            "total": Decimal("0"),
            "products_map": {},
            "payments_map": {},
        })
        day["sales"].append(sale)
        day["sale_count"] += 1
        day["total"] += Decimal(sale.total)
        for item in sale.items:
            presentation = item.presentation or "UNIDAD"
            key = (item.product_id, presentation)
            product = day["products_map"].setdefault(key, {
                "name": item.product.name,
                "code": item.product.code,
                "presentation": presentation,
                "quantity": Decimal("0"),
                "amount": Decimal("0"),
            })
            product["quantity"] += Decimal(item.sale_quantity if item.sale_quantity is not None else item.quantity)
            product["amount"] += Decimal(item.subtotal)
        for payment in sale.payments:
            current_amount = day["payments_map"].get(payment.method, Decimal("0"))
            day["payments_map"][payment.method] = current_amount + Decimal(payment.amount)

    result = []
    for day in days.values():
        day["products"] = sorted(day.pop("products_map").values(), key=lambda product: (product["name"].lower(), product["presentation"]))
        day["payments"] = sorted(day.pop("payments_map").items())
        result.append(day)
    return sorted(result, key=lambda day: day["date"], reverse=True)
