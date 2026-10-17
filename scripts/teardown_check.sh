#!/bin/bash
# After `cdk destroy`: list everything this project could have left running or costing money in ap-south-1 and print a verdict per category.
# Read-only (only list/describe calls). Usage: source scripts/aws_env.sh; scripts/teardown_check.sh
set -uo pipefail
R=ap-south-1
n() { printf "%-34s %s\n" "$1" "$2"; }
echo "== resources that cost money while they exist =="
n "EC2 instances (not terminated):"   "$(aws ec2 describe-instances --region $R --query 'length(Reservations[].Instances[?State.Name!=`terminated`][])' --output text)"
n "EBS volumes:"                      "$(aws ec2 describe-volumes --region $R --query 'length(Volumes)' --output text)"
n "Elastic IP addresses:"             "$(aws ec2 describe-addresses --region $R --query 'length(Addresses)' --output text)"
n "NAT gateways (not deleted):"       "$(aws ec2 describe-nat-gateways --region $R --query 'length(NatGateways[?State!=`deleted`])' --output text)"
n "Load balancers:"                   "$(aws elbv2 describe-load-balancers --region $R --query 'length(LoadBalancers)' --output text 2>/dev/null || echo '?')"
n "VPC endpoints (interface):"        "$(aws ec2 describe-vpc-endpoints --region $R --query 'length(VpcEndpoints[?VpcEndpointType==`Interface`])' --output text)"
echo "== our stacks and data =="
n "CloudFormation stacks (Genkart*):" "$(aws cloudformation list-stacks --region $R --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE UPDATE_ROLLBACK_COMPLETE ROLLBACK_COMPLETE DELETE_FAILED --query 'length(StackSummaries[?starts_with(StackName,`Genkart`)])' --output text)"
n "S3 buckets (all):"                 "$(aws s3api list-buckets --query 'length(Buckets)' --output text)  -> $(aws s3api list-buckets --query 'Buckets[].Name' --output text)"
n "SQS queues:"                       "$(aws sqs list-queues --region $R --query 'length(QueueUrls || `[]`)' --output text)"
n "Lambda functions:"                 "$(aws lambda list-functions --region $R --query 'length(Functions)' --output text)"
n "CloudWatch log groups:"            "$(aws logs describe-log-groups --region $R --query 'length(logGroups)' --output text)  -> $(aws logs describe-log-groups --region $R --query 'logGroups[].logGroupName' --output text)"
n "CloudWatch alarms:"                "$(aws cloudwatch describe-alarms --region $R --query 'length(MetricAlarms)' --output text)"
n "CloudWatch dashboards:"            "$(aws cloudwatch list-dashboards --region $R --query 'length(DashboardEntries)' --output text)"
n "Non-default VPCs:"                 "$(aws ec2 describe-vpcs --region $R --query 'length(Vpcs[?IsDefault==`false`])' --output text)"
n "IAM roles named *Genkart*:"        "$(aws iam list-roles --query 'length(Roles[?contains(RoleName,`Genkart`)])' --output text)"
echo
echo "Zero everywhere (except CDK's own bootstrap bucket/stack, and log groups of the auto-delete helper) = nothing of ours is left running."
