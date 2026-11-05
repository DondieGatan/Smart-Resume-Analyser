"""Server-side checks on the sign-up form: a request that skips the browser's own validation must still be refused.
register_user is replaced, so no database is touched, and the rate limiter is switched off for the test."""
import pytest

import app as app_module


@pytest.fixture
def client(monkeypatch):
    app_module.app.config['TESTING'] = True
    monkeypatch.setattr(app_module.limiter, 'enabled', False)
    created = []

    def fake_register(full_name, email, password):
        created.append(email)
        return False, 'stop here'      # a failure keeps the route from logging anyone in; we only count attempts

    monkeypatch.setattr(app_module, 'register_user', fake_register)
    c = app_module.app.test_client()
    c.created = created
    return c


def post(client, **overrides):
    data = {'full_name': 'Ada Lovelace', 'email': 'ada@example.com', 'password': 'Passw0rd!', 'confirm_password': 'Passw0rd!'}
    data.update(overrides)
    return client.post('/register', data=data)


def test_a_valid_sign_up_reaches_the_account_creation_step(client):
    post(client)
    assert client.created == ['ada@example.com']


@pytest.mark.parametrize('email', ['not-an-email', 'a@b', '@example.com', 'a b@example.com', 'two@@example.com', 'x@y.', ''])
def test_an_invalid_email_is_refused_before_anything_is_created(client, email):
    resp = post(client, email=email)
    assert client.created == []
    assert resp.status_code == 200 and ('valid email' in resp.get_data(as_text=True) or 'Email is required' in resp.get_data(as_text=True))


def test_overlong_values_are_refused(client):
    post(client, email='a' * 250 + '@example.com')
    post(client, full_name='N' * 101)
    post(client, password='p' * 129, confirm_password='p' * 129)
    assert client.created == []


def test_the_existing_password_rules_still_apply(client):
    post(client, password='short', confirm_password='short')
    post(client, confirm_password='Different1!')
    assert client.created == []
