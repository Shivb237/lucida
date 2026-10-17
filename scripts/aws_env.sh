# Source this in every new Terminal window:   source scripts/aws_env.sh
# Sets the login profile and the bucket name so commands never see an empty $B. The bucket name is read from data/aws-bucket.txt (git-ignored,
# one line): it is an identifier of your account's resources and must not be published. Get it from the CDK output of GenkartData (BucketName).
export AWS_PROFILE=genkart
_f="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)/data/aws-bucket.txt"
if [ -s "$_f" ]; then
  export B="$(tr -d '[:space:]' < "$_f")"
  echo "AWS_PROFILE=$AWS_PROFILE  B=<read from data/aws-bucket.txt>"
else
  echo "missing or empty $_f: put the bucket name in it (one line), then source this again"
fi
unset _f
