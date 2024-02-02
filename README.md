# Description
Time Lord is an email/calendar tracking system. It connects with Gitlab to generate distribution lists. It caches calendar invites so when people are added to a Gitlab group they automatically receive any calendar invites relevant to that group. And it manages pages on a Gitlab wiki to list all calendar invites and distribution lists. 

**For installation, configuration, and operation, see the Timelord Standalone documentation at [standalone / docs](./standalone/docs/readme.md)**

# Configuration
## Development
For development, Time Lord includes a vscode devcontainer configuration. 

.devcontainer/devcontainer.env must exist for the devcontainer to start properly.

## Production
Docker and Docker Compose is the recommended deployment mechanism. 

```
$ cd docker
$ cp timelord.env_template timelord.env

$ nano timelord.env

$ docker-compose build
$ docker-compose up -d

```

Monitoring Docker logs:

```
docker-compose logs -t --follow --tail 10
```

# AWS Authentication
AWS likely requires MFA, therefore a script is provided to ease authentication.

1. Configure your access key and secret access key in the AWS extension in VSCode. This will allow login, but its extremely limited.
2. Open a terminal in the devcontainer
3. Run ```source AWS_USE_MFA.sh```. This will prompt for your MFA token, and then creates a new credential for AWS in vscode.
4. In the vscode extension, switch connection to the mfa connection


# Hints
When testing on a local system, switch to your MFA profile in the terminal like this:

```
$ export AWS_PROFILE=mfa

```

## Creating self-signed certificates

```
openssl req -x509 -newkey rsa:4096 -keyout keyfile.pem -out certfile.pem -days 365 -nodes

```
vscode uses the same environment for running and debugging, so AWS API calls will work through your MFA profile.

## Deploying Docker to AWS ECR

```
$ export AWS_PROFILE=mfa
$ aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 117484236981.dkr.ecr.us-east-1.amazonaws.com/timelord
$ docker build -t timelord .
$ docker tag timelord:latest 117484236981.dkr.ecr.us-east-1.amazonaws.com/timelord:latest
$ docker push 117484236981.dkr.ecr.us-east-1.amazonaws.com/timelord:latest

```

## Deploying as a systemd service

1. Download to /opt/timelord/
2. Copy timelord_server.service to /etc/systemd/system/timelord_server.service
3. Copy timelord.env to /env/timelord.env and configure it
4. Generate ssl certs:
```
$ mkdir -p /opt/timelord/certs
$ cd /opt/timelord/certs
$ openssl req -x509 -newkey rsa:4096 -keyout keyfile.pem -out certfile.pem -days 365 -nodes
```
5. Make it start on startup, and start it now
```
sudo systemctl enable timelord_server.service
sudo systemctl start timelord_server.service
```

## Monitoring
```
sudo systemctl status timelord_server.service
journalctl -u timelord_server.service
```


# Advanced Usage - Web Services
There are several custom web services which can trigger various internal functions.

## Force delete an email/invite

POST purge-email (uuid=INVITE_UUID)

This operation will completely delete a calendar invite from Timelord's internal database. It must be submitted as an HTTP POST, and requires the UUID of the invite to delete.

The use case for this is if a meeting should have been canceleded/deleted by the host (e.g. from Outlook), but Timelord still has the meeting listed.

*Note*: This does not send cancellation emails, it only deletes it from Timelord. If a meeting is deleted accidentally from Timelord, but still exists in the host's calendar, then the host can simply resend the calendar invite and it will recreate the entry in Timelord.

*Note*: This operation does NOT refresh the caledar wiki. To refresh the calendar wiki, call the refresh-wiki web service.

The UUID is the long string on the Calendar Wiki that looks like this:
040000008200E00074C5B7101A82E0080000000070D3D30FD4E0D901000000000000000010000000EDB9D9CB44D57A428FA0CEDDCB3E2921

```
$ curl -d '{"uuid":"INVITE_UUID"}' -H "Content-Type: application/json" -X POST http://localhost:8080/purge-email
```

Example usage:
```
$ curl -d '{"uuid":"040000008200E00074C5B7101A82E0080000000070D3D30FD4E0D901000000000000000010000000EDB9D9CB44D57A428FA0CEDDCB3E2921"}' -H "Content-Type: application/json" -X POST http://localhost:8080/purge-email
 ```

## Refresh Calendar Wiki
GET refresh-wiki

or

POST refresh-wiki

Refreshes the Calendar Wiki page on Gitlab to reflect the current calendar and invites.

```
$ curl http://localhost:8080/refresh-wiki
```

## Force Send Calendar Invites

POST force-resend-email **uuid**

or

POST force-resend-email **meeting_title**

Resends the email invites for the specified meeting. Using the uuid option is more reliable, since meeting titles are not guaranteed to be unique.

```
$ curl -d '{"uuid":"INVITE_UUID"}' -H "Content-Type: application/json" -X POST http://localhost:8080/force-resend-email
```

# Note - Catastrophic Data Loss Recovery

Time Lord is not the canonical source of any meetings. All meetings are created and "owned" by the originating host on their own email service. Time Lord is just a caching and routing assistant.

If the database is lost, Time Lord will not be able to send standing invites to new group members unless the original host re-sends the invite to the appropriate Time Lord / Gitlab groups. 

This just means that if there is a situation where Time Lord has to be rebuilt / redeployed, the hosts should re-send all of their meeting invites. This will be enough to repopulate Time Lord. The downside is attendees will be spammed with additional emails as Time Lord's database is rebuilt since it no longer knows who has already received them, but these will overwrite the events in their calendars. 

In other words: this will not create duplicate calendar invites, it only will temporarily increase email traffic.
