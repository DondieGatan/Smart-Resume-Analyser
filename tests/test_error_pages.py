"""The error pages: browsers get a styled page, /api/ calls keep getting small JSON bodies. No database is touched
(these routes do not exist or are rejected before any query)."""
import pytest

from app import app


@pytest.fixture
def client():
    app.config['TESTING'] = True
    return app.test_client()


def test_an_unknown_page_returns_the_styled_404_not_the_plain_default(client):
    resp = client.get('/no-such-page')
    body = resp.get_data(as_text=True)
    assert resp.status_code == 404
    assert 'Page not found' in body and 'error-card' in body
    assert 'The requested URL was not found on the server' not in body   # the unstyled Flask text


def test_the_error_page_offers_a_way_back(client):
    body = client.get('/no-such-page').get_data(as_text=True)
    assert 'Go back' in body and 'Go to the start' in body


def test_an_unknown_api_path_gets_json_not_html(client):
    resp = client.post('/api/ai-tools/nope', json={})
    # not signed in, so this may be a redirect to the login page; if it is answered it must be JSON
    if resp.status_code != 302:
        assert resp.is_json


def test_a_wrong_method_is_a_styled_405(client):
    resp = client.post('/login-does-not-exist')
    assert resp.status_code == 404
    resp = client.delete('/health')
    assert resp.status_code == 405 and 'That action is not allowed' in resp.get_data(as_text=True)


def test_every_response_carries_the_basic_security_headers(client):
    for path in ('/login', '/no-such-page', '/static/css/style.css'):
        h = client.get(path).headers
        assert h['X-Content-Type-Options'] == 'nosniff', path
        assert h['X-Frame-Options'] == 'DENY', path
        assert 'strict-origin' in h['Referrer-Policy'], path
        csp = h['Content-Security-Policy']
        assert "frame-ancestors 'none'" in csp and "form-action 'self'" in csp, path
        assert 'script-src' not in csp      # deliberately not set: pages use inline scripts and CDN libraries


def test_hsts_is_only_sent_when_the_site_is_served_over_https(client, monkeypatch):
    from app import Config
    monkeypatch.setattr(Config, 'SESSION_COOKIE_SECURE', False)
    assert 'Strict-Transport-Security' not in client.get('/login').headers
    monkeypatch.setattr(Config, 'SESSION_COOKIE_SECURE', True)
    assert 'max-age=' in client.get('/login').headers['Strict-Transport-Security']
