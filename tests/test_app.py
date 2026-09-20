from datetime import datetime
from io import BytesIO

from app import create_app, db, Customer, Payment, Product, Sale, SaleItem, User


def app_client(extra_config=None):
    config = {"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "SECRET_KEY": "test"}
    if extra_config: config.update(extra_config)
    app = create_app(config)
    with app.app_context():
        db.drop_all(); db.create_all()
        owner = User(username="owner", role="owner"); owner.set_password("secret")
        employee = User(username="employee", role="employee"); employee.set_password("secret")
        product = Product(code="MART-1", name="Martillo", sale_price=1000, box_price=1000, unit_price=100, purchase_price=500, stock=5, closed_boxes=5, loose_units=0, units_per_box=1, has_box_presentation=True, minimum_stock=1)
        db.session.add_all([owner, employee, product]); db.session.commit()
    return app.test_client(), app


def login(client, username="employee"):
    return client.post("/login", data={"username": username, "password": "secret"}, follow_redirects=True)


def test_sale_updates_stock():
    client, app = app_client(); login(client)
    response = client.post("/sales", json={"items":[{"product_id":1,"presentation":"CAJA","quantity":2}],"payments":[{"method":"EFECTIVO","amount":"2000"}]})
    assert response.status_code == 200 and response.json["ok"]
    with app.app_context(): assert db.session.get(Product, 1).stock == 3


def test_sale_rejects_insufficient_stock():
    client, app = app_client(); login(client)
    response = client.post("/sales", json={"items":[{"product_id":1,"presentation":"CAJA","quantity":8}],"payments":[{"method":"EFECTIVO","amount":"8000"}]})
    assert response.status_code == 400


def test_employee_cannot_edit_products():
    client, _ = app_client(); login(client)
    assert client.get("/products/1/edit").status_code == 403


def test_unit_sale_opens_a_box_and_keeps_loose_units():
    client, app = app_client(); login(client)
    with app.app_context():
        product = db.session.get(Product, 1)
        product.units_per_box = 10; product.closed_boxes = 5; product.loose_units = 0; product.box_price = 1000; product.unit_price = 120; product.sync_stock(); db.session.commit()
    response = client.post("/sales", json={"items":[{"product_id":1,"presentation":"UNIDAD","quantity":3}],"payments":[{"method":"EFECTIVO","amount":"360"}]})
    assert response.status_code == 200
    with app.app_context():
        product = db.session.get(Product, 1)
        assert (product.closed_boxes, product.loose_units, product.available_units) == (4, 7, 47)


def test_customer_discount_is_calculated_on_the_server():
    client, app = app_client(); login(client)
    with app.app_context():
        product = db.session.get(Product, 1)
        product.units_per_box = 10; product.closed_boxes = 1; product.unit_price = 120; product.sync_stock()
        customer = Customer(name="Cliente descuento", discount_percent=10)
        db.session.add(customer); db.session.commit()
    response = client.post("/sales", json={"customer_id": 1, "items":[{"product_id":1,"presentation":"UNIDAD","quantity":2}],"payments":[{"method":"DEBITO","amount":"216"}]})
    assert response.status_code == 200
    with app.app_context(): assert db.session.get(Sale, 1).total == 216


def test_unit_only_product_can_be_sold_without_box_presentation():
    client, app = app_client(); login(client)
    with app.app_context():
        product = db.session.get(Product, 1)
        product.has_box_presentation = False; product.closed_boxes = 0; product.loose_units = 5; product.units_per_box = 1; product.unit_price = 250; product.sync_stock()
        db.session.commit()
    response = client.post("/sales", json={"items":[{"product_id":1,"presentation":"UNIDAD","quantity":2}],"payments":[{"method":"EFECTIVO","amount":"500"}]})
    assert response.status_code == 200 and response.json["ok"]
    with app.app_context(): assert db.session.get(Product, 1).loose_units == 3


def test_owner_can_create_a_unit_only_product_without_box_price():
    client, app = app_client(); login(client, "owner")
    response = client.post("/products/new", data={"code":"TOR-1", "name":"Tornillo", "unit_price":"50", "loose_units":"20"}, follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        product = Product.query.filter_by(code="TOR-1").one()
        assert not product.has_box_presentation and product.sale_price == 50


def test_owner_deletes_product_from_catalog_without_erasing_history():
    client, app = app_client(); login(client, "owner")
    response = client.post("/products/1/delete", follow_redirects=True)
    assert response.status_code == 200
    with app.app_context(): assert not db.session.get(Product, 1).active
    response = client.get("/products")
    assert b"Martillo" not in response.data


def test_sale_form_marks_unit_only_products_as_not_sold_by_box():
    client, app = app_client(); login(client)
    with app.app_context():
        product = db.session.get(Product, 1)
        product.has_box_presentation = False; db.session.commit()
    response = client.get("/sales/new")
    assert b'data-has-box="0"' in response.data


def test_customer_accepts_identity_data_and_optional_discount():
    client, app = app_client(); login(client)
    response = client.post("/customers", data={"first_name":"Ana", "last_name":"Perez", "dni":"30111222", "phone":"11 5555 1234", "discount_percent":"12.5"}, follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        customer = Customer.query.filter_by(dni="30111222").one()
        assert (customer.name, customer.discount_percent) == ("Perez, Ana", 12.5)


def test_duplicate_product_keeps_values_and_marks_code():
    client, _ = app_client(); login(client, "owner")
    response = client.post("/products/new", data={"code":"MART-1", "name":"Otro martillo", "unit_price":"100", "purchase_price":"55", "minimum_stock":"8"})
    assert response.status_code == 200
    assert b'Ya existe un producto con este c' in response.data
    assert b'value="Otro martillo"' in response.data
    assert b'value="55"' in response.data and b'value="8"' in response.data


def test_restock_increases_stock_and_updates_prices():
    client, app = app_client(); login(client, "owner")
    response = client.post("/products/1/restock", data={"add_units":"3", "purchase_price":"600", "unit_price":"120", "box_price":"1200"})
    assert response.status_code == 302
    with app.app_context():
        product = db.session.get(Product, 1)
        assert (product.loose_units, product.purchase_price, product.unit_price) == (3, 600, 120)


def test_supplier_detail_lists_associated_products():
    client, app = app_client(); login(client, "owner")
    with app.app_context():
        from app import Supplier
        supplier = Supplier(name="Proveedor prueba", company_name="Empresa SA")
        db.session.add(supplier); db.session.flush()
        db.session.get(Product, 1).supplier_id = supplier.id
        db.session.commit()
    response = client.get("/suppliers/1")
    assert response.status_code == 200
    assert b"Proveedor prueba" in response.data and b"Martillo" in response.data


def test_owner_can_remove_product_from_supplier_without_deleting_product():
    client, app = app_client(); login(client, "owner")
    with app.app_context():
        from app import Supplier
        supplier = Supplier(name="Proveedor removible")
        db.session.add(supplier); db.session.flush()
        db.session.get(Product, 1).supplier_id = supplier.id
        supplier_id = supplier.id; db.session.commit()
    response = client.post(f"/suppliers/{supplier_id}/products/1/remove")
    assert response.status_code == 302
    with app.app_context():
        product = db.session.get(Product, 1)
        assert product.supplier_id is None and product.active


def test_mixed_payment_is_rejected_when_total_is_insufficient():
    client, app = app_client(); login(client)
    response = client.post("/sales", json={"items":[{"product_id":1,"presentation":"UNIDAD","quantity":1}],"payments":[{"method":"TRANSFERENCIA","amount":"40"},{"method":"QR","amount":"50"}]})
    assert response.status_code == 400
    assert "Faltan" in response.json["error"]
    with app.app_context(): assert Sale.query.count() == 0


def test_cash_payment_calculates_change_and_records_sale():
    client, app = app_client(); login(client)
    response = client.post("/sales", json={"items":[{"product_id":1,"presentation":"UNIDAD","quantity":1}],"payments":[{"method":"EFECTIVO","amount":"150"}]})
    assert response.status_code == 200 and response.json["change_due"] == "50.00"
    with app.app_context():
        sale = Sale.query.one()
        assert sale.change_due == 50 and sale.cash_received == 150


def test_transfer_and_qr_are_valid_payment_methods():
    client, app = app_client(); login(client)
    response = client.post("/sales", json={"items":[{"product_id":1,"presentation":"UNIDAD","quantity":1}],"payments":[{"method":"TRANSFERENCIA","amount":"40"},{"method":"QR","amount":"60"}]})
    assert response.status_code == 200


def test_browser_cart_payload_with_id_records_sale_and_change():
    client, app = app_client(); login(client)
    response = client.post("/sales", json={"items":[{"id":"1","presentation":"UNIDAD","qty":1,"quantity":1}],"payments":[{"method":"EFECTIVO","amount":"1000"}]})
    assert response.status_code == 200
    assert response.json["change_due"] == "900.00"
    with app.app_context(): assert Sale.query.count() == 1


def test_sales_summary_is_grouped_by_day_and_product():
    client, app = app_client(); login(client)
    with app.app_context():
        sale_one = Sale(user_id=2, total=200, status="CONFIRMADA", created_at=datetime(2026, 9, 19, 10, 0))
        sale_two = Sale(user_id=2, total=100, status="CONFIRMADA", created_at=datetime(2026, 9, 20, 11, 0))
        db.session.add_all([sale_one, sale_two]); db.session.flush()
        db.session.add_all([
            SaleItem(sale_id=sale_one.id, product_id=1, quantity=2, sale_quantity=2, presentation="UNIDAD", unit_price=100, subtotal=200),
            SaleItem(sale_id=sale_two.id, product_id=1, quantity=1, sale_quantity=1, presentation="UNIDAD", unit_price=100, subtotal=100),
            Payment(sale_id=sale_one.id, method="EFECTIVO", amount=200),
            Payment(sale_id=sale_two.id, method="QR", amount=100),
        ])
        db.session.commit()
    response = client.get("/reports/sales")
    assert response.status_code == 200
    assert b"20/09/2026" in response.data and b"19/09/2026" in response.data
    assert b"Cantidad vendida" in response.data and b"Martillo" in response.data


def test_daily_close_contains_products_payments_and_total():
    client, app = app_client(); login(client)
    with app.app_context():
        sale = Sale(user_id=2, total=200, status="CONFIRMADA", created_at=datetime(2026, 9, 20, 17, 30))
        db.session.add(sale); db.session.flush()
        db.session.add(SaleItem(sale_id=sale.id, product_id=1, quantity=2, sale_quantity=2, presentation="UNIDAD", unit_price=100, subtotal=200))
        db.session.add(Payment(sale_id=sale.id, method="TRANSFERENCIA", amount=200))
        db.session.commit()
    response = client.get("/reports/sales/daily/2026-09-20")
    assert response.status_code == 200
    assert b"CIERRE DIARIO" in response.data
    assert b"Martillo" in response.data and b"Transferencia" in response.data
    assert b"Imprimir cierre diario" in response.data


def test_sales_report_has_date_range_selector():
    client, _ = app_client(); login(client)
    response = client.get("/reports/sales")
    assert response.status_code == 200
    assert b'name="start_date"' in response.data
    assert b'name="end_date"' in response.data
    assert b"Imprimir resumen por fecha" in response.data
    assert b"Imprimir cierre de hoy" not in response.data


def test_range_report_only_includes_sales_between_selected_dates():
    client, app = app_client(); login(client)
    with app.app_context():
        included = Sale(user_id=2, total=200, status="CONFIRMADA", created_at=datetime(2026, 9, 15, 12, 0))
        excluded = Sale(user_id=2, total=100, status="CONFIRMADA", created_at=datetime(2026, 9, 20, 12, 0))
        db.session.add_all([included, excluded]); db.session.flush()
        db.session.add_all([
            SaleItem(sale_id=included.id, product_id=1, quantity=2, sale_quantity=2, presentation="UNIDAD", unit_price=100, subtotal=200),
            SaleItem(sale_id=excluded.id, product_id=1, quantity=1, sale_quantity=1, presentation="UNIDAD", unit_price=100, subtotal=100),
            Payment(sale_id=included.id, method="EFECTIVO", amount=200),
            Payment(sale_id=excluded.id, method="QR", amount=100),
        ])
        db.session.commit()
    response = client.get("/reports/sales/range?start_date=2026-09-14&end_date=2026-09-16")
    assert response.status_code == 200
    assert b"14/09/2026" in response.data and b"16/09/2026" in response.data
    assert b"15/09/2026" in response.data
    assert b"Efectivo" in response.data and b">QR<" not in response.data


def test_range_report_rejects_reversed_dates():
    client, _ = app_client(); login(client)
    response = client.get("/reports/sales/range?start_date=2026-09-20&end_date=2026-09-10", follow_redirects=True)
    assert response.status_code == 200
    assert b"fecha desde no puede ser posterior" in response.data


def test_owner_can_add_product_with_image(tmp_path):
    client, app = app_client({"PRODUCT_IMAGE_UPLOAD_FOLDER": str(tmp_path)}); login(client, "owner")
    png = b"\x89PNG\r\n\x1a\n" + b"test-image"
    response = client.post("/products/new", data={
        "code": "IMG-1", "name": "Producto con imagen", "unit_price": "100", "loose_units": "4",
        "image": (BytesIO(png), "producto.png"),
    }, content_type="multipart/form-data", follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        product = Product.query.filter_by(code="IMG-1").one()
        assert product.image_filename.endswith(".png")
        assert (tmp_path / product.image_filename).exists()


def test_product_rejects_non_image_upload(tmp_path):
    client, app = app_client({"PRODUCT_IMAGE_UPLOAD_FOLDER": str(tmp_path)}); login(client, "owner")
    response = client.post("/products/new", data={
        "code": "BAD-IMG", "name": "Producto inválido", "unit_price": "100", "loose_units": "4",
        "image": (BytesIO(b"not-an-image"), "archivo.jpg"),
    }, content_type="multipart/form-data")
    assert response.status_code == 200
    assert b"JPG, PNG o WebP" in response.data
    with app.app_context(): assert Product.query.filter_by(code="BAD-IMG").first() is None
