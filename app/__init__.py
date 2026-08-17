import os
from datetime import datetime
from decimal import Decimal, InvalidOperation
from functools import wraps

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
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
    category = db.relationship("Category")


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
    phone = db.Column(db.String(60), default="")
    condition = db.Column(db.String(30), default="Al dia", nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)


class Sale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    total = db.Column(db.Numeric(14, 2), nullable=False)
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
        products_query = Product.query.order_by(Product.name)
        if query:
            pattern = f"%{query}%"
            products_query = products_query.filter(db.or_(Product.name.ilike(pattern), Product.code.ilike(pattern), Product.barcode.ilike(pattern)))
        return render_template("products.html", products=products_query.all(), query=query)

    @app.route("/products/new", methods=["GET", "POST"])
    @owner_required
    def product_new():
        if request.method == "POST":
            try:
                product = Product(code=request.form["code"].strip(), barcode=request.form.get("barcode", "").strip() or None,
                    name=request.form["name"].strip(), description=request.form.get("description", "").strip(),
                    purchase_price=money(request.form.get("purchase_price", 0)), sale_price=money(request.form["sale_price"]),
                    stock=Decimal("0"), minimum_stock=Decimal(request.form.get("minimum_stock", 0)))
                db.session.add(product); db.session.flush()
                initial = Decimal(request.form.get("initial_stock", 0))
                if initial < 0: raise ValueError("El stock inicial no puede ser negativo")
                if initial:
                    product.stock = initial
                    db.session.add(InventoryMovement(product_id=product.id, user_id=current_user().id, quantity=initial, movement_type="ALTA", reason="Stock inicial", reference=None))
                audit(current_user(), "CREAR_PRODUCTO", "product", product.id, product.name)
                db.session.commit(); flash("Producto creado.", "success"); return redirect(url_for("products"))
            except Exception as exc:
                db.session.rollback(); flash(f"No se pudo crear el producto: {exc}", "error")
        return render_template("product_form.html", product=None)

    @app.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
    @owner_required
    def product_edit(product_id):
        product = db.get_or_404(Product, product_id)
        if request.method == "POST":
            try:
                old_price = product.sale_price
                product.code = request.form["code"].strip(); product.barcode = request.form.get("barcode", "").strip() or None
                product.name = request.form["name"].strip(); product.description = request.form.get("description", "").strip()
                product.purchase_price = money(request.form.get("purchase_price", 0)); product.sale_price = money(request.form["sale_price"])
                product.minimum_stock = Decimal(request.form.get("minimum_stock", 0)); product.active = "active" in request.form
                audit(current_user(), "EDITAR_PRODUCTO", "product", product.id, product.name)
                if old_price != product.sale_price: audit(current_user(), "CAMBIAR_PRECIO", "product", product.id, f"{old_price} a {product.sale_price}")
                db.session.commit(); flash("Producto actualizado.", "success"); return redirect(url_for("products"))
            except Exception as exc:
                db.session.rollback(); flash(f"No se pudo actualizar: {exc}", "error")
        return render_template("product_form.html", product=product)

    @app.route("/products/<int:product_id>/adjust", methods=["POST"])
    @owner_required
    def product_adjust(product_id):
        product = db.get_or_404(Product, product_id)
        try:
            quantity = Decimal(request.form["quantity"])
            reason = request.form["reason"].strip()
            if not quantity or not reason: raise ValueError("Cantidad y motivo son obligatorios")
            if product.stock + quantity < 0: raise ValueError("El ajuste no puede dejar stock negativo")
            product.stock += quantity
            db.session.add(InventoryMovement(product_id=product.id, user_id=current_user().id, quantity=quantity, movement_type="AJUSTE", reason=reason, reference=None))
            audit(current_user(), "AJUSTAR_STOCK", "product", product.id, f"{quantity}: {reason}")
            db.session.commit(); flash("Stock ajustado.", "success")
        except Exception as exc:
            db.session.rollback(); flash(f"No se pudo ajustar el stock: {exc}", "error")
        return redirect(url_for("products"))

    @app.route("/sales/new")
    @login_required
    def sale_new():
        return render_template("sale_new.html", products=Product.query.filter_by(active=True).order_by(Product.name).all(), customers=Customer.query.filter_by(active=True).order_by(Customer.name).all())

    @app.route("/sales", methods=["POST"])
    @login_required
    def sale_create():
        try:
            cart = request.get_json(silent=True) or {}
            lines = cart.get("items", [])
            if not lines: raise ValueError("El carrito está vacío")
            payments = cart.get("payments", [])
            if not payments: raise ValueError("Debe registrar un pago")
            sale = Sale(user_id=current_user().id, customer_id=cart.get("customer_id") or None, total=0)
            db.session.add(sale); db.session.flush()
            total = Decimal("0")
            for line in lines:
                product = db.session.get(Product, int(line["product_id"]))
                quantity = Decimal(str(line["quantity"]))
                if not product or not product.active or quantity <= 0: raise ValueError("Producto o cantidad inválida")
                if product.stock < quantity: raise ValueError(f"Stock insuficiente para {product.name}")
                subtotal = (product.sale_price * quantity).quantize(Decimal("0.01"))
                product.stock -= quantity; total += subtotal
                db.session.add(SaleItem(sale_id=sale.id, product_id=product.id, quantity=quantity, unit_price=product.sale_price, subtotal=subtotal))
                db.session.add(InventoryMovement(product_id=product.id, user_id=current_user().id, quantity=-quantity, movement_type="VENTA", reason="Venta confirmada", reference=f"V-{sale.id}"))
            paid = sum((money(p["amount"]) for p in payments), Decimal("0"))
            if paid != total: raise ValueError("La suma de pagos debe coincidir con el total")
            for payment in payments:
                method = payment["method"]
                if method not in {"EFECTIVO", "DEBITO", "CREDITO"}: raise ValueError("Medio de pago invalido")
                db.session.add(Payment(sale_id=sale.id, method=method, amount=money(payment["amount"])))
            sale.total = total
            audit(current_user(), "CONFIRMAR_VENTA", "sale", sale.id, f"Total {total}")
            db.session.commit()
            return {"ok": True, "sale_id": sale.id, "redirect": url_for("sale_receipt", sale_id=sale.id)}
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
                item.product.stock += item.quantity
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
        return render_template("report_sales.html", total=total, count=confirmed.count(), by_payment=by_payment)

    with app.app_context():
        db.create_all(); seed_data()
    return app
