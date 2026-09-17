import * as cdk from 'aws-cdk-lib';
import * as s3 from 'aws-cdk-lib/aws-s3';
import { Construct } from 'constructs';

export interface ArtifactStorageStackProps extends cdk.StackProps {
  /**
   * Deterministic prefix for runtime artifacts inside the bucket.
   * @default 'runtime/'
   */
  readonly runtimePrefix?: string;
}

export class ArtifactStorageStack extends cdk.Stack {
  public readonly artifactBucket: s3.Bucket;
  public readonly runtimePrefix: string;

  constructor(scope: Construct, id: string, props?: ArtifactStorageStackProps) {
    super(scope, id, props);

    this.runtimePrefix = props?.runtimePrefix ?? 'runtime/';

    // Dedicated private S3 bucket for Intent2Data canonical runtime artifacts
    this.artifactBucket = new s3.Bucket(this, 'ArtifactBucket', {
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      versioned: true,
      enforceSSL: true,
      // Removal policy appropriate for development/demo: allows clean teardown without orphaned buckets
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    // CloudFormation Outputs for downstream consumer reference
    new cdk.CfnOutput(this, 'ArtifactBucketName', {
      value: this.artifactBucket.bucketName,
      description: 'The name of the S3 bucket hosting Intent2Data runtime artifacts',
      exportName: `${this.stackName}-ArtifactBucketName`,
    });

    new cdk.CfnOutput(this, 'ArtifactBucketArn', {
      value: this.artifactBucket.bucketArn,
      description: 'The ARN of the S3 bucket hosting Intent2Data runtime artifacts',
      exportName: `${this.stackName}-ArtifactBucketArn`,
    });

    new cdk.CfnOutput(this, 'RuntimeArtifactPrefix', {
      value: this.runtimePrefix,
      description: 'The deterministic S3 key prefix for canonical runtime artifacts',
      exportName: `${this.stackName}-RuntimeArtifactPrefix`,
    });
  }
}
