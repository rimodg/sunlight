"""Hosted personal access must protect both the app and its API."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from access_gate import configure_access_gate


def application(env):
    app = FastAPI()
    configure_access_gate(app, env)

    @app.get('/health')
    def health():
        return {'status': 'ok'}

    @app.get('/watch/')
    def workspace():
        return {'workspace': True}

    @app.post('/analyze')
    def analyze():
        return {'analysis': True}

    return TestClient(app)


@pytest.fixture
def protected():
    return application({'SUNLIGHT_AUTH_REQUIRED': '1', 'SUNLIGHT_ACCESS_USER': 'sunlight',
                        'SUNLIGHT_ACCESS_PASSWORD': 'test-only-password'})


def test_hosting_cannot_start_without_required_password():
    with pytest.raises(RuntimeError, match='SUNLIGHT_ACCESS_PASSWORD'):
        application({'SUNLIGHT_AUTH_REQUIRED': '1'})


def test_workspace_and_api_require_sign_in(protected):
    for response in [protected.get('/watch/'), protected.post('/analyze')]:
        assert response.status_code == 401
        assert response.headers['www-authenticate'].startswith('Basic ')


def test_health_remains_available_to_hosting_platform(protected):
    assert protected.get('/health').json() == {'status': 'ok'}


def test_correct_credentials_allow_workspace_and_analysis(protected):
    auth = ('sunlight', 'test-only-password')
    assert protected.get('/watch/', auth=auth).status_code == 200
    response = protected.post('/analyze', auth=auth)
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'


def test_wrong_or_malformed_credentials_do_not_pass(protected):
    assert protected.get('/watch/', auth=('sunlight', 'incorrect')).status_code == 401
    for header in ['Basic invalid', 'Bearer token', 'Basic dXNlcg==']:
        assert protected.get('/watch/', headers={'Authorization': header}).status_code == 401


def test_local_mode_is_unchanged_without_password():
    assert application({}).get('/watch/').status_code == 200


def test_hosted_root_redirects_to_actual_workspace(monkeypatch):
    from api import app
    monkeypatch.setenv('SUNLIGHT_DEFAULT_WORKSPACE', '1')
    response = TestClient(app).get('/', follow_redirects=False)
    assert response.status_code == 307
    assert response.headers['location'] == '/watch/'
