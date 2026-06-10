from fastapi.testclient import TestClient
from main import app
import pytest

client = TestClient(app)

def test_list_subjects_no_school():
    response = client.get("/subjects/")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

# Note: Further tests would require a mock DB or test Supabase instance.
# These are representative of the checks performed manually.
