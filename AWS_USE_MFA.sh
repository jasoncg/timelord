#! /bin/false
# must run this file with "source ~/AWS_Use_MFA.sh"
set -e  # This will cause the shell to exit if any command returns a non-zero exit code.

### Global Variable Declarations ###
AWS_ACCT=$(aws sts get-caller-identity | jq -r '.Account')
USER=$(aws sts get-caller-identity | jq -r '.Arn')
MFA=$(aws iam list-mfa-devices | jq -r '.MFADevices[0].SerialNumber')

### Prompt user for their virtual MFA token from Google Authenticator ###
echo "";
echo "";
echo "Multi-Factor Authentication (MFA) script -- ver 1.0"
echo "----------------------------------------------------------"
echo "";
echo "AWS Account #: $AWS_ACCT";
echo "Date: $(date "+%Y-%m-%d")"
echo "User Info: $USER";
echo "";
echo "Enter Your MFA token from Google Authenticator: ";
read TOKEN
echo "";

### Acquire session token using the user's virtual MFA and provided token ###
JSON=$(aws sts get-session-token --serial-number "$MFA" --token-code "$TOKEN")

### Export the necessary key values as required once keys are provided from aws sts get-session-token ###
export AWS_ACCESS_KEY_ID=$(jq -r .Credentials.AccessKeyId <<< "$JSON")
export AWS_SECRET_ACCESS_KEY=$(jq -r .Credentials.SecretAccessKey <<< "$JSON")
export AWS_SESSION_TOKEN=$(jq -r .Credentials.SessionToken <<< "$JSON")

echo "AWS_ACCESS_KEY_ID: $AWS_ACCESS_KEY_ID"
echo "AWS_SECRET_ACCESS_KEY: $AWS_SECRET_ACCESS_KEY"
echo "AWS_SESSION_TOKEN: $AWS_SESSION_TOKEN"

### Update the credentials file ###
AWS_CREDENTIALS_FILE="${HOME}/.aws/credentials"

# Remove the existing [mfa] section if it exists
sed -i.bak '/\[mfa\]/,/^\[/d' "$AWS_CREDENTIALS_FILE"

# Append the new [mfa] section
echo "[mfa]" >> "$AWS_CREDENTIALS_FILE"
echo "aws_access_key_id = $AWS_ACCESS_KEY_ID" >> "$AWS_CREDENTIALS_FILE"
echo "aws_secret_access_key = $AWS_SECRET_ACCESS_KEY" >> "$AWS_CREDENTIALS_FILE"
echo "aws_session_token = $AWS_SESSION_TOKEN" >> "$AWS_CREDENTIALS_FILE"