from api_client.client import MavunoClient
from api_client.models.auth import LoginRequest, RegisterRequest

# Point directly to your active FastAPI backend
client = MavunoClient("http://127.0.0.1:8000")

# 1. Prepare registration payload matching the DB schema
farmer_reg = RegisterRequest(
    phone_e164="+254712345678",
    password="StrongPassword123!",
    display_name="Mercy Too",
    role="farmer",
    farm_name="Mavuno Ridge Farm",
    county="Uasin Gishu",
)

print("--- 1. Testing Registration Endpoint ---")
reg_res = client.auth.register(farmer_reg)
print(f"Status Code: {reg_res.status_code}")
print(f"Success: {reg_res.success}")

if reg_res.success and reg_res.data:
    print(f"Access Token: {reg_res.data.access_token[:25]}...")
    client.set_auth_token(reg_res.data.access_token)
else:
    print(f"Registration response/error: {reg_res.error}")

# 2. Test Login
print("\n--- 2. Testing Login Endpoint ---")
login_req = LoginRequest(
    phone_e164="+254712345678",
    password="StrongPassword123!",
)

login_res = client.auth.login(login_req)
print(f"Status Code: {login_res.status_code}")
print(f"Success: {login_res.success}")

if login_res.success and login_res.data:
    print("Login successful! Token saved to client session.")
    client.set_auth_token(login_res.data.access_token)
else:
    print(f"Login failed: {login_res.error}")