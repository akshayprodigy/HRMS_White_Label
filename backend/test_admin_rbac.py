import requests
import json

BASE_URL = "http://localhost:8000/api/v1"

def test_admin_rbac():
    # 1. Login as standard user (User 2)
    user2_data = {
        "username": "user2@gmail.com",
        "password": "password123"
    }
    
    print("--- 1. Login as Standard User ---")
    login_resp = requests.post(f"{BASE_URL}/auth/login", data=user2_data)
    if login_resp.status_code != 200:
        print(f"Login failed: {login_resp.text}")
        return
        
    token_user2 = login_resp.json()["access_token"]
    headers_user2 = {"Authorization": f"Bearer {token_user2}"}

    # 2. Try to access admin endpoint (Should fail 403)
    print("\n--- 2. Access Admin (Unauthorized) ---")
    admin_resp = requests.get(f"{BASE_URL}/admin/users", headers=headers_user2)
    print(f"Status: {admin_resp.status_code}")
    if admin_resp.status_code == 403:
        print("✅ Access denied as expected.")
    else:
        print(f"❌ Unexpected status: {admin_resp.status_code}")
        print(admin_resp.json())

    # 3. Login as Super Admin (User 1)
    user1_data = {
        "username": "user1@gmail.com",
        "password": "password123"
    }
    
    print("\n--- 3. Login as Super Admin ---")
    login_resp_admin = requests.post(f"{BASE_URL}/auth/login", data=user1_data)
    if login_resp_admin.status_code != 200:
        print(f"Login failed: {login_resp_admin.text}")
        return
        
    token_admin = login_resp_admin.json()["access_token"]
    headers_admin = {"Authorization": f"Bearer {token_admin}"}

    # 4. Access admin endpoint (Should succeed 200)
    print("\n--- 4. Access Admin (Authorized) ---")
    admin_resp_ok = requests.get(f"{BASE_URL}/admin/users", headers=headers_admin)
    print(f"Status: {admin_resp_ok.status_code}")
    if admin_resp_ok.status_code == 200:
        users = admin_resp_ok.json()
        print(f"✅ Access granted. Found {len(users)} users.")
        # Verify user2 is in the list
        has_user2 = any(u['email'] == 'user2@gmail.com' for u in users)
        if has_user2:
            print("✅ User list validation passed.")
    else:
        print(f"❌ Unexpected status: {admin_resp_ok.status_code}")
        print(admin_resp_ok.json())

    # 5. Check Roles and Permissions
    print("\n--- 5. Check Roles and Permissions ---")
    roles_resp = requests.get(f"{BASE_URL}/admin/roles", headers=headers_admin)
    perms_resp = requests.get(f"{BASE_URL}/admin/permissions", headers=headers_admin)
    
    if roles_resp.status_code == 200 and perms_resp.status_code == 200:
        print(f"✅ Found {len(roles_resp.json())} roles and {len(perms_resp.json())} permissions.")
    else:
        print("❌ Failed to fetch roles/permissions")

if __name__ == "__main__":
    test_admin_rbac()
