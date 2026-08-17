from app import create_app, db, Product, User


def app_client():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "SECRET_KEY": "test"})
    with app.app_context():
        db.drop_all(); db.create_all()
        owner = User(username="owner", role="owner"); owner.set_password("secret")
        employee = User(username="employee", role="employee"); employee.set_password("secret")
        product = Product(code="MART-1", name="Martillo", sale_price=1000, purchase_price=500, stock=5, minimum_stock=1)
        db.session.add_all([owner, employee, product]); db.session.commit()
    return app.test_client(), app


def login(client, username="employee"):
    return client.post("/login", data={"username": username, "password": "secret"}, follow_redirects=True)


def test_sale_updates_stock():
    client, app = app_client(); login(client)
    response = client.post("/sales", json={"items":[{"product_id":1,"quantity":2}],"payments":[{"method":"EFECTIVO","amount":"2000"}]})
    assert response.status_code == 200 and response.json["ok"]
    with app.app_context(): assert db.session.get(Product, 1).stock == 3


def test_sale_rejects_insufficient_stock():
    client, app = app_client(); login(client)
    response = client.post("/sales", json={"items":[{"product_id":1,"quantity":8}],"payments":[{"method":"EFECTIVO","amount":"8000"}]})
    assert response.status_code == 400


def test_employee_cannot_edit_products():
    client, _ = app_client(); login(client)
    assert client.get("/products/1/edit").status_code == 403
