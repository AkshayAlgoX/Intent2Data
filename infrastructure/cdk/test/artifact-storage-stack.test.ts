import * as cdk from 'aws-cdk-lib';
import { Template, Match } from 'aws-cdk-lib/assertions';
import { ArtifactStorageStack } from '../lib/artifact-storage-stack';

describe('ArtifactStorageStack', () => {
  let app: cdk.App;
  let stack: ArtifactStorageStack;
  let template: Template;

  beforeEach(() => {
    app = new cdk.App();
    stack = new ArtifactStorageStack(app, 'TestArtifactStorageStack', {
      runtimePrefix: 'runtime/',
    });
    template = Template.fromStack(stack);
  });

  test('creates a private S3 bucket with encryption, versioning, and block public access', () => {
    template.hasResourceProperties('AWS::S3::Bucket', {
      BucketEncryption: {
        ServerSideEncryptionConfiguration: [
          {
            ServerSideEncryptionByDefault: {
              SSEAlgorithm: 'AES256',
            },
          },
        ],
      },
      PublicAccessBlockConfiguration: {
        BlockPublicAcls: true,
        BlockPublicPolicy: true,
        IgnorePublicAcls: true,
        RestrictPublicBuckets: true,
      },
      VersioningConfiguration: {
        Status: 'Enabled',
      },
    });
  });

  test('enforces SSL on the bucket policy', () => {
    template.hasResourceProperties('AWS::S3::BucketPolicy', {
      PolicyDocument: {
        Statement: Match.arrayWith([
          Match.objectLike({
            Action: 's3:*',
            Condition: {
              Bool: {
                'aws:SecureTransport': 'false',
              },
            },
            Effect: 'Deny',
            Principal: {
              AWS: '*',
            },
          }),
        ]),
      },
    });
  });

  test('exports bucket name, arn, and runtime prefix outputs', () => {
    template.hasOutput('ArtifactBucketName', {});
    template.hasOutput('ArtifactBucketArn', {});
    template.hasOutput('RuntimeArtifactPrefix', {
      Value: 'runtime/',
    });
  });
});
