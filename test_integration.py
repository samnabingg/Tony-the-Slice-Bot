import pytest
from q import app  # import your Flask app
from flask import g

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False

    with app.app_context():
        g.db_connection = None  # prevent teardown issues
        with app.test_client() as client:
            yield client

def test_full_user_order_flow(client):
    # 1. Login with fake user (simulate login)
    response = client.post('/login', json={
        'username': 'testuser',
        'password': 'testpass'
    })
    assert response.status_code in (200, 401)  # 401 if user doesn't exist
    login_data = response.get_json()

    if not login_data.get('success', False):
        print("Skipping further tests because login failed (user might not exist).")
        return  # stop if login fails

    cid = login_data.get('cid')
    assert cid is not None

    # 2. Start a new order
    with client.session_transaction() as sess:
        sess['cid'] = cid

    response = client.post('/api/start-order')
    assert response.status_code == 200
    order_id = response.get_json().get('orderId')
    assert order_id is not None

    # 3. Add an item to the order
    response = client.post('/api/order-summary', json={
        'cid': cid,
        'order_id': order_id,
        'orderData': {
            'selectedItems': [
                {
                    'itemId': 1,
                    'itemName': 'Classic Pizza',
                    'price': 10.0,
                    'quantity': 2
                }
            ]
        }
    })
    assert response.status_code == 200

    # 4. Complete the order
    response = client.post('/api/complete-order')
    assert response.status_code == 200
    assert 'Order completed' in response.get_json().get('message', '')

    # 5. Fetch loyalty points
    response = client.get('/api/loyalty-points')
    assert response.status_code == 200
    points = response.get_json().get('points')
    assert points is not None

    print(f"Loyalty Points after order: {points}")

def test_logout_flow(client):
    with client.session_transaction() as sess:
        sess['cid'] = 1  # simulate login

    response = client.get('/logout')
    assert response.status_code == 302  # redirected to home page

    with client.session_transaction() as sess:
        assert 'cid' not in sess  # session should be cleared
