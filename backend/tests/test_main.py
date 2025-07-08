import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_read_main():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Hello World"}  # Adjust based on your actual response structure

def test_another_endpoint():
    response = client.get("/another-endpoint")  # Replace with your actual endpoint
    assert response.status_code == 200
    assert "expected_key" in response.json()  # Adjust based on your actual response structure