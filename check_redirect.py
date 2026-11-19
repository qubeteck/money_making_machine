from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app, raise_server_exceptions=False, follow_redirects=False)

# Login
login_resp = client.post('/auth/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=False)
print(f'Login: Status={login_resp.status_code}, Location={login_resp.headers.get("location")}')

# Get set-cookie header
set_cookie = login_resp.headers.get('set-cookie', '')
print(f'Set-Cookie: {set_cookie[:150]}')

# Now make a request to / with the cookie
print()
print('Testing with cookie...')
# The TestClient cookies attribute
print(f'login_resp.cookies: {login_resp.cookies}')
print(f'login_resp.cookies.get: {login_resp.cookies.get("money_machine_token", "") if hasattr(login_resp, "cookies") and login_resp.cookies else "N/A"}')