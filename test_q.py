import pytest
from q import app
from flask import g
from typing import Any

import pytest
from q import app
from flask import g
from typing import Any

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False

    with app.app_context():
        # Set a dummy db connection to avoid teardown crashes
        g.db_connection = None

        with app.test_client() as client:
            yield client



def test_home_page(client: Any):
    response = client.get('/')
    assert response.status_code == 200

def test_login_invalid(client: Any):
    response = client.post('/login', json={'username': 'baduser', 'password': 'badpass'})
    assert response.status_code == 401

def test_start_order_without_login(client: Any):
    response = client.post('/api/start-order')
    assert response.status_code == 401

def test_start_order_with_login(client: Any):
    with client.session_transaction() as sess:
        sess['cid'] = 1
    response = client.post('/api/start-order')
    assert response.status_code == 200
    assert b'orderId' in response.data

def test_logout(client: Any):
    with client.session_transaction() as sess:
        sess['cid'] = 1
    client.get('/logout')
    with client.session_transaction() as sess:
        assert 'cid' not in sess
