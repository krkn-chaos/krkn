# IAM Permissions for AWS S3 Replication Chaos Scenario

## Overview

This document provides detailed instructions for setting up the required IAM permissions to run the AWS S3 Replication chaos scenario.

## Required Permissions

The IAM user or role running Krkn needs two specific permissions on the **source bucket**:

1. `s3:GetReplicationConfiguration` - Read the current replication configuration
2. `s3:PutReplicationConfiguration` - Modify the replication configuration

## IAM Policy

### Minimal Policy (Recommended)

This policy grants only the required permissions for specific buckets:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "KrknS3ReplicationChaos",
      "Effect": "Allow",
      "Action": [
        "s3:GetReplicationConfiguration",
        "s3:PutReplicationConfiguration"
      ],
      "Resource": [
        "arn:aws:s3:::your-source-bucket-name"
      ]
    }
  ]
}
```

**Replace** `your-source-bucket-name` with your actual bucket name.

### Multiple Buckets

If you need to run scenarios on multiple buckets:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "KrknS3ReplicationChaosMultipleBuckets",
      "Effect": "Allow",
      "Action": [
        "s3:GetReplicationConfiguration",
        "s3:PutReplicationConfiguration"
      ],
      "Resource": [
        "arn:aws:s3:::bucket-1",
        "arn:aws:s3:::bucket-2",
        "arn:aws:s3:::bucket-3"
      ]
    }
  ]
}
```

### All Buckets (Use with Caution)

**Warning**: This grants permissions on ALL S3 buckets in your account. Only use in non-production or testing environments.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "KrknS3ReplicationChaosAllBuckets",
      "Effect": "Allow",
      "Action": [
        "s3:GetReplicationConfiguration",
        "s3:PutReplicationConfiguration"
      ],
      "Resource": "arn:aws:s3:::*"
    }
  ]
}
```

## Setup Methods

### Method 1: AWS Console (GUI)

#### Step 1: Create the Policy

1. Go to [AWS IAM Console](https://console.aws.amazon.com/iam/)
2. Click **Policies** in the left sidebar
3. Click **Create policy**
4. Click the **JSON** tab
5. Paste the policy JSON (see above)
6. Click **Next: Tags** (optional)
7. Click **Next: Review**
8. Enter policy name: `KrknS3ReplicationChaosPolicy`
9. Enter description: `Allows Krkn to pause and restore S3 replication for chaos testing`
10. Click **Create policy**

#### Step 2: Attach to User/Role

**For IAM User:**
1. Go to **Users** in the left sidebar
2. Click on your user (e.g., `krkn-user`)
3. Click **Add permissions** → **Attach policies directly**
4. Search for `KrknS3ReplicationChaosPolicy`
5. Check the box next to it
6. Click **Next** → **Add permissions**

**For IAM Role:**
1. Go to **Roles** in the left sidebar
2. Click on your role (e.g., `krkn-role`)
3. Click **Add permissions** → **Attach policies**
4. Search for `KrknS3ReplicationChaosPolicy`
5. Check the box next to it
6. Click **Add permissions**

### Method 2: AWS CLI

#### Step 1: Create Policy File

Create a file named `krkn-s3-replication-policy.json`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "KrknS3ReplicationChaos",
      "Effect": "Allow",
      "Action": [
        "s3:GetReplicationConfiguration",
        "s3:PutReplicationConfiguration"
      ],
      "Resource": [
        "arn:aws:s3:::your-source-bucket-name"
      ]
    }
  ]
}
```

#### Step 2: Create and Attach Policy

**For IAM User:**

```bash
# Create the policy
aws iam create-policy \
  --policy-name KrknS3ReplicationChaosPolicy \
  --policy-document file://krkn-s3-replication-policy.json \
  --description "Allows Krkn to pause and restore S3 replication"

# Get the policy ARN from the output, then attach it
aws iam attach-user-policy \
  --user-name krkn-user \
  --policy-arn arn:aws:iam::YOUR_ACCOUNT_ID:policy/KrknS3ReplicationChaosPolicy
```

**For IAM Role:**

```bash
# Create the policy
aws iam create-policy \
  --policy-name KrknS3ReplicationChaosPolicy \
  --policy-document file://krkn-s3-replication-policy.json

# Attach to role
aws iam attach-role-policy \
  --role-name krkn-role \
  --policy-arn arn:aws:iam::YOUR_ACCOUNT_ID:policy/KrknS3ReplicationChaosPolicy
```

**Inline Policy (Alternative):**

```bash
# Attach inline policy directly to user
aws iam put-user-policy \
  --user-name krkn-user \
  --policy-name KrknS3ReplicationChaos \
  --policy-document file://krkn-s3-replication-policy.json
```

### Method 3: Terraform

```hcl
# Define the policy
resource "aws_iam_policy" "krkn_s3_replication_chaos" {
  name        = "KrknS3ReplicationChaosPolicy"
  description = "Allows Krkn to pause and restore S3 replication for chaos testing"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "KrknS3ReplicationChaos"
        Effect = "Allow"
        Action = [
          "s3:GetReplicationConfiguration",
          "s3:PutReplicationConfiguration"
        ]
        Resource = [
          "arn:aws:s3:::your-source-bucket-name"
        ]
      }
    ]
  })
}

# Attach to IAM user
resource "aws_iam_user_policy_attachment" "krkn_user_s3_replication" {
  user       = "krkn-user"
  policy_arn = aws_iam_policy.krkn_s3_replication_chaos.arn
}

# Or attach to IAM role
resource "aws_iam_role_policy_attachment" "krkn_role_s3_replication" {
  role       = "krkn-role"
  policy_arn = aws_iam_policy.krkn_s3_replication_chaos.arn
}
```

### Method 4: CloudFormation

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: 'IAM Policy for Krkn S3 Replication Chaos Scenario'

Parameters:
  SourceBucketName:
    Type: String
    Description: Name of the S3 source bucket
    Default: your-source-bucket-name

Resources:
  KrknS3ReplicationChaosPolicy:
    Type: AWS::IAM::ManagedPolicy
    Properties:
      ManagedPolicyName: KrknS3ReplicationChaosPolicy
      Description: Allows Krkn to pause and restore S3 replication
      PolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Sid: KrknS3ReplicationChaos
            Effect: Allow
            Action:
              - s3:GetReplicationConfiguration
              - s3:PutReplicationConfiguration
            Resource:
              - !Sub 'arn:aws:s3:::${SourceBucketName}'

Outputs:
  PolicyArn:
    Description: ARN of the created policy
    Value: !Ref KrknS3ReplicationChaosPolicy
    Export:
      Name: KrknS3ReplicationChaosPolicyArn
```

## Verification

### Verify Permissions

Test if permissions are correctly configured:

```bash
# Test GetReplicationConfiguration
aws s3api get-bucket-replication --bucket your-source-bucket-name

# If successful, you'll see the replication configuration
# If access denied, permissions are not set correctly
```

### Test with AWS CLI

```bash
# Set credentials (if not already configured)
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
export AWS_DEFAULT_REGION=us-east-1

# Test get replication config
aws s3api get-bucket-replication --bucket your-source-bucket-name

# Expected output: JSON with replication configuration
# Error output: "An error occurred (AccessDenied)..." means permissions are missing
```

## Security Best Practices

### 1. Principle of Least Privilege

Only grant permissions on specific buckets you need to test:

```json
{
  "Resource": [
    "arn:aws:s3:::specific-bucket-name"
  ]
}
```

**Avoid** using wildcards unless absolutely necessary:

```json
{
  "Resource": "arn:aws:s3:::*"  // ❌ Too permissive
}
```

### 2. Use IAM Roles (Recommended)

When running Krkn on AWS infrastructure (EC2, ECS, Lambda):

- Use IAM roles instead of access keys
- Roles provide temporary credentials
- Automatically rotated by AWS
- No need to manage long-term credentials

### 3. Separate Chaos Testing User/Role

Create a dedicated IAM user or role for chaos testing:

```bash
# Create dedicated user
aws iam create-user --user-name krkn-chaos-testing

# Attach only required policies
aws iam attach-user-policy \
  --user-name krkn-chaos-testing \
  --policy-arn arn:aws:iam::YOUR_ACCOUNT_ID:policy/KrknS3ReplicationChaosPolicy
```

### 4. Use Conditions (Advanced)

Restrict when permissions can be used:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "KrknS3ReplicationChaosWithConditions",
      "Effect": "Allow",
      "Action": [
        "s3:GetReplicationConfiguration",
        "s3:PutReplicationConfiguration"
      ],
      "Resource": "arn:aws:s3:::your-source-bucket-name",
      "Condition": {
        "IpAddress": {
          "aws:SourceIp": "203.0.113.0/24"
        },
        "StringEquals": {
          "aws:RequestedRegion": "us-east-1"
        }
      }
    }
  ]
}
```

### 5. Enable CloudTrail Logging

Monitor S3 API calls:

```bash
# Enable CloudTrail for S3 data events
aws cloudtrail put-event-selectors \
  --trail-name my-trail \
  --event-selectors '[{
    "ReadWriteType": "All",
    "IncludeManagementEvents": true,
    "DataResources": [{
      "Type": "AWS::S3::Object",
      "Values": ["arn:aws:s3:::your-source-bucket-name/*"]
    }]
  }]'
```

## Troubleshooting

### Error: "Access Denied"

**Cause**: Missing IAM permissions

**Solution**:
1. Verify policy is attached to correct user/role
2. Check policy JSON for typos in bucket name
3. Ensure bucket ARN format is correct: `arn:aws:s3:::bucket-name`

```bash
# Check attached policies
aws iam list-attached-user-policies --user-name krkn-user

# Check inline policies
aws iam list-user-policies --user-name krkn-user

# Get policy details
aws iam get-user-policy --user-name krkn-user --policy-name KrknS3ReplicationChaos
```

### Error: "Invalid Principal"

**Cause**: Trying to attach policy to non-existent user/role

**Solution**: Verify user/role exists

```bash
# List users
aws iam list-users

# List roles
aws iam list-roles
```

### Error: "Policy Already Exists"

**Cause**: Policy with same name already exists

**Solution**: Use a different name or update existing policy

```bash
# List existing policies
aws iam list-policies --scope Local

# Delete existing policy (if needed)
aws iam delete-policy --policy-arn arn:aws:iam::YOUR_ACCOUNT_ID:policy/KrknS3ReplicationChaosPolicy
```

## Additional Resources

- [AWS IAM Best Practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html)
- [AWS S3 Security Best Practices](https://docs.aws.amazon.com/AmazonS3/latest/userguide/security-best-practices.html)
- [AWS IAM Policy Simulator](https://policysim.aws.amazon.com/)
- [AWS CLI Configuration](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html)

## Support

If you encounter issues with IAM permissions:

1. Check the [Troubleshooting](#troubleshooting) section above
2. Review AWS CloudTrail logs for detailed error messages
3. Open an issue on [GitHub](https://github.com/krkn-chaos/krkn/issues)
4. Ask in [#krkn on Kubernetes Slack](https://kubernetes.slack.com/messages/C05SFMHRWK1)
