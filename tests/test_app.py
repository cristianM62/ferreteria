from app import create_app, db, Customer, Product, Sale, User


def app_client():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "SECRET_KEY": "test"})
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
