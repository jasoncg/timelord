# High-level Description

Timelord is a Python-based application which acts as an email distribution list. It uses Gitlab groups for distribution list groups.

It also has an embedded sqlite database to store all calendar invites so that when new users are added to Gitlab they'll automatically receive relevant invites.

*Only members of the Gitlab instance linked to Timelord may send email to Timelord distribution lists.*

# Email

**Note** This is a simplified explanation of how email works and intended to just give a high-level overview to understand how Timelord works.

There are two main components to an email message: the envelope, and the body content.

The envelope is used for routing the email across the Internet and email servers to find recepients. It indicates who the message is from and where it needs to go. The concept is very similar to a real physical letter envelope, but not exactly the same. For example: BCC recpients will be in the envelope so that the messages can actually route to them. 

The body content is basicaly the "email" that the recepient actually sees. It has the text in the email, and any attachments. But it also has the From, To, and CC entries for the email. 

One way to think of this is imagine a physical formal letter sent to many people. You write the letter, and at the top of the letter indicate whom it is from, and the intended audience. These are similar to the From, To, and CC lines in an email. You then make many copies of this letter, and make one envelope for each person you are sending it to. You might have where the letter is from, but regardless you need to indicate where the letter needs to go. 

# Detailed Description

Timelord is a single executable with two external interfaces: an email server for receiving email on TCP port 25, and a web sever on port 80 for web hooks.

It is built with asynchronous Python APIs so that it can receive messages as quickly as possible without holding up sending email servers. When a message is received, there is a basic bit of validation to check that the sender isn't spoofing an email server. If it passes that minimal amount of validation, the message is passed to a queue (called the Action Queue) so that it can wait for the next message.

A seperate process monitors this queue. It processes each message in the queue to ensure the sender is authorized to send to a group, unroll distribution lists to the actual members of the Gitlab groups, (if relevant) store the calendar invite in the sqlite database, and forward the message to intended receipients.

The web server which is part of Timelord also adds messages to the Action Queue.

Most configuration of Timelord is done through environment variables. If **not** using Docker or some container mechanism, these variables will need to be set in the context where the Timelord Python script runs.

# Docker

To ease deployment, Timelord by default runs in a Docker container and uses docker-compose. 

## Dockerfile
The Dockerfile is based on a Python image. It installs required packages from ```requirements.txt```, copies the Timelord code into the image, generates self-signed certificates for the port 25 SMTP server, and runs Timelord.

## docker-compose.yml
The docker compose file maps the SMTP and web service ports, mounts volumes for the sqlite database file and self-signed certificates, and points to the timelord.env file for configuration.

# DNS

# Server Application

# Web Services
