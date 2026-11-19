from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app, raise_server_exceptions=False, follow_redirects=False)

# Login and get the set cookie
login_resp = client.post('/auth/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=False)
token = login_resp.cookies.get('money_machine_token')
print(f'Token: {token}')

# Now access dashboard with the cookie
response = client.get('/', cookies={'money_machine_token': token})
print(f'Dashboard status: {response.status_code}')
print(f'Dashboard length: {len(response.text)}')
print(f'Contains admin: {"admin" in response.text.lower()}')
print(f'Contains logout: {"logout" in response.text.lower()}')
print(f'First 200 chars: {response.text[:200]}')