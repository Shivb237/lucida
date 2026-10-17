import * as cdk from 'aws-cdk-lib/core';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as sqs from 'aws-cdk-lib/aws-sqs';
import { Construct } from 'constructs';

/**
 * Where GenKart keeps its data.
 *  - S3 bucket: the shard files (about 334 MB). Private, encrypted, https only. Deleted with the stack, so teardown is one command.
 *  - SQS FIFO queue "ingest": new-product jobs. FIFO because it has the 5-minute duplicate guard our laptop queue had.
 *  - SQS FIFO queue "ingest-dlq": the failed-jobs tray. A job moves here after 8 failed tries (same number as the laptop worker).
 */
export class DataStack extends cdk.Stack {
  public readonly bucket: s3.Bucket;
  public readonly ingestQueue: sqs.Queue;
  public readonly deadLetterQueue: sqs.Queue;

  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

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
