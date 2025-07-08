FROM registry.access.redhat.com/ubi8/python-312 as app

# Switch to root user to ensure permission for system changes
USER root

WORKDIR /opt/app

# Create app user and group
RUN groupadd -r app && \
    useradd -r -g app app

# Copy the requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application source code
COPY ./src /opt/app

# Set permissions for the entrypoint script
RUN chmod 0755 entrypoint.sh && \
    chown -R app:app /opt/app

# Switch to the app user for runtime
USER nobody:0

# Command to run the application
CMD ["/bin/sh", "-c", "/opt/app/entrypoint.sh"]

# Expose the application port
EXPOSE 8000/TCP