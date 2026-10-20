import * as cdk from 'aws-cdk-lib/core';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as sqs from 'aws-cdk-lib/aws-sqs';
import { Construct } from 'constructs';

/**
 * Where GenKart keeps its data.
 *  - S3 bucket: the shard files (about 334 MB). Private, encrypted, https only. Deleted with the stack, so teardown is one command.
 *  - SQS FIFO queue "ingest": new-product jobs. FIFO because it has the 5-minute duplicate guard our laptop queue had.
 *  - SQS FIFO queue "ingest-dlq": the failed-jobs tray. A job moves here after 8 failed tries (same number as the laptop worker).
 *  - the four log groups /genkart/{router,encoder,ingest,shard}, kept 7 days. They live HERE, not in the monitoring stack, because of the
 *    order: the CloudWatch agent on a machine creates a missing log group on its own (with no expiry) a few minutes after boot, and the
 *    monitoring stack can only be deployed after the machines (it names them). A stack that then tries to create the same group fails
 *    with "already exists". This stack is deployed before the machines (they read its bucket), so the groups always exist, with their
 *    expiry, before any agent starts. If an agent made them anyway, deploy with -c logGroupsExist=true: they are then looked up by name.
 *    Never use that flag to move from the older layout (the monitoring stack owned the groups, delete on removal): updating it would delete
 *    the groups and their metric filters. Tear the old stacks down first (infra/README.md).
 */
export interface DataStackProps extends cdk.StackProps {
  /** true = the /genkart/* log groups already exist in the account: refer to them by name, do not create them. */
  readonly logGroupsExist?: boolean;
}

export const LOG_GROUPS = ['router', 'encoder', 'ingest', 'shard'] as const;

export class DataStack extends cdk.Stack {
  public readonly bucket: s3.Bucket;
  public readonly ingestQueue: sqs.Queue;
  public readonly deadLetterQueue: sqs.Queue;
  public readonly logGroups: Record<string, logs.ILogGroup> = {};

  constructor(scope: Construct, id: string, props?: DataStackProps) {
    super(scope, id, props);

    for (const g of LOG_GROUPS) {
      this.logGroups[g] = props?.logGroupsExist
        ? logs.LogGroup.fromLogGroupName(this, `Logs-${g}`, `/genkart/${g}`)
        : new logs.LogGroup(this, `Logs-${g}`, {
          logGroupName: `/genkart/${g}`,
          retention: logs.RetentionDays.ONE_WEEK,
          removalPolicy: cdk.RemovalPolicy.DESTROY,   // a learning project: destroying the stack removes the logs too
        });
    }

    this.bucket = new s3.Bucket(this, 'ShardBucket', {
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      enforceSSL: true,
      removalPolicy: cdk.RemovalPolicy.DESTROY, // a learning project: `cdk destroy` must leave nothing behind
      autoDeleteObjects: true,                  // empties the bucket first, otherwise AWS refuses to delete a non-empty bucket
    });

    this.deadLetterQueue = new sqs.Queue(this, 'IngestDlq', {
      fifo: true,
      retentionPeriod: cdk.Duration.days(14), // failed jobs stay long enough to be looked at
      enforceSSL: true,
    });

    this.ingestQueue = new sqs.Queue(this, 'IngestQueue', {
      fifo: true,
      contentBasedDeduplication: false,       // the sender gives an explicit dedup id (the product id); same id within 5 minutes = ignored
      visibilityTimeout: cdk.Duration.seconds(60), // how long a worker has to finish before the job reappears for another worker
      retentionPeriod: cdk.Duration.days(4),
      enforceSSL: true,
      deadLetterQueue: { queue: this.deadLetterQueue, maxReceiveCount: 8 },
    });

    new cdk.CfnOutput(this, 'BucketName', { value: this.bucket.bucketName });
    new cdk.CfnOutput(this, 'IngestQueueUrl', { value: this.ingestQueue.queueUrl });
    new cdk.CfnOutput(this, 'IngestDlqUrl', { value: this.deadLetterQueue.queueUrl });
  }
}
