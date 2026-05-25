import requests
import time
import json

BASE_URL = "http://localhost:8000/api/v1"

def test_timer_flow():
    # 1. Create/Login User
    user_data = {
        "email": "test_timer@example.com",
        "password": "testpassword",
        "full_name": "Timer Tester"
    }
    
    print("--- 1. Login ---")
    login_resp = requests.post(f"{BASE_URL}/auth/login", data={
        "username": user_data["email"],
        "password": user_data["password"]
    })
    if login_resp.status_code != 200:
        print(f"Login failed: {login_resp.text}")
        assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("Logged in successfully.")

    # 2. Mark Attendance (Gating)
    print("\n--- 2. Mark Attendance ---")
    att_resp = requests.post(f"{BASE_URL}/attendance/mark", headers=headers)
    print(f"Attendance: {att_resp.status_code}")

    # 3. Check Initial Status
    print("\n--- 3. Check Timer Status (Initial) ---")
    status_resp = requests.get(f"{BASE_URL}/timesheets/timer/status", headers=headers)
    print(f"Status: {status_resp.json()}")

    # 4. Start Timer
    print("\n--- 4. Start Timer ---")
    start_data = {
        "project_name": "Testing Vertical Slice",
        "task_description": "Local API Validation"
    }
    start_resp = requests.post(f"{BASE_URL}/timesheets/timer/start", json=start_data, headers=headers)
    assert start_resp.status_code == 200
    print(f"Started: {start_resp.json()}")

    # 5. Pause Timer
    print("\n--- 5. Pause Timer ---")
    time.sleep(2)  # Simulate some work
    pause_resp = requests.post(f"{BASE_URL}/timesheets/timer/pause", headers=headers)
    if pause_resp.status_code != 200:
        print(f"Pause failed: {pause_resp.status_code} - {pause_resp.text}")
    assert pause_resp.status_code == 200
    print(f"Paused: {pause_resp.json()}")

    # 6. Resume Timer
    print("\n--- 6. Resume Timer ---")
    resume_resp = requests.post(f"{BASE_URL}/timesheets/timer/resume", headers=headers)
    assert resume_resp.status_code == 200
    print(f"Resumed: {resume_resp.json()}")

    # 7. Stop Timer
    print("\n--- 7. Stop Timer ---")
    time.sleep(2)  # Simulate more work
    stop_resp = requests.post(f"{BASE_URL}/timesheets/timer/stop", headers=headers)
    assert stop_resp.status_code == 200
    print(f"Stopped: {stop_resp.json()}")

    # 8. Fetch Weekly Data
    print("\n--- 8. Weekly Data ---")
    weekly_resp = requests.get(f"{BASE_URL}/timesheets/weekly", headers=headers)
    assert weekly_resp.status_code == 200
    data = weekly_resp.json()
    print(f"Weekly Total Seconds: {data['total_weekly_seconds']}")
    print(f"Days with data: {len(data['daily_data'])}")
    
    for day in data['daily_data']:
        if day['total_seconds'] > 0:
            print(f"Day {day['day']}: {day['total_seconds']}s across {len(day['entries'])} entries")

if __name__ == "__main__":
    try:
        test_timer_flow()
        print("\n✅ ALL LOCAL API TESTS PASSED")
    except Exception as e:
        print(f"\n❌ TEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
