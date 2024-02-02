# Use Python 3.10 as the base image
FROM python:3.10

# Set the working directory
WORKDIR /app

# Copy requirements file and install dependencies
COPY ./requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire package
COPY ./standalone /app

# Copy the certificate generation script
COPY ./generate_certs.sh /app/

# Generate certs if they do not exist
RUN chmod +x /app/generate_certs.sh
#&& /app/generate_certs.sh

# Expose port 25 for your email server
EXPOSE 25
EXPOSE 8080

# Run the certificate generation script and the application
CMD ["/bin/bash", "-c", "/app/generate_certs.sh && python ./main.py"]
