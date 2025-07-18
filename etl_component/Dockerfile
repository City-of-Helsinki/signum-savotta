# Use official Python image
FROM python:3.12-slim

# Switch to root user to ensure permission for system changes
USER root

# Set working directory
WORKDIR /app

# Create app user and group
RUN groupadd -r app && \
    useradd -r -g app app

# Copy the requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application source code
COPY ./src /app

# Set permissions for the entrypoint script
RUN chmod 0755 entrypoint.sh && \
    chown -R app:app /app

# Switch to the app user for runtime
USER nobody:0

# Command to run the application
CMD ["/bin/sh", "-c", "/app/entrypoint.sh"]