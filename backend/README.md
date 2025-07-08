# Signum-savotta backend application

## Setup Instructions

1. **Create a virtual environment**:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

2. **Install dependencies**:
   ```
   pip install -r requirements.txt
   ```

## Running the Application

To run the FastAPI application, execute the following command:

```
uvicorn app.main:app --reload
```

This will start the server at `http://127.0.0.1:8000`.

## API Documentation

The automatically generated API documentation can be accessed at:

- Swagger UI: `http://127.0.0.1:8000/docs`
- Redoc: `http://127.0.0.1:8000/redoc`
