# Intent2Data Infrastructure (AWS CDK)

AWS Cloud Development Kit (CDK) TypeScript project managing infrastructure for the Intent2Data service.

This initial foundation provisions the dedicated, private Amazon S3 bucket used to store and distribute canonical runtime index artifacts.

---

## Prerequisites

- **Node.js**: `v18.x` or later (tested on `v20.x`)
- **npm**: `v9.x` or later
- **AWS CLI**: configured with appropriate IAM credentials (`aws configure`)
- **AWS CDK CLI**: installed globally (`npm install -g aws-cdk`) or executed via `npx cdk`

---

## Setup & Commands

### 1. Install Dependencies
```bash
cd infrastructure/cdk
npm install
```

### 2. Build TypeScript Code
```bash
npm run build
```

### 3. Run CDK Tests
```bash
npm test
```

### 4. Synthesize CloudFormation Template
```bash
npx cdk synth
```

### 5. Deploy Stack
```bash
# Bootstrap CDK (only required once per AWS account/region)
npx cdk bootstrap

# Deploy the artifact storage stack
npx cdk deploy
```

---

## Resources Provisioned

The `Intent2Data-ArtifactStorageStack` provisions:

1. **Private S3 Bucket (`AWS::S3::Bucket`)**:
   - **Encryption**: Server-Side Encryption enabled by default (`AES256` / `S3_MANAGED`).
   - **Public Access Block**: `BLOCK_ALL` (all 4 flags active: BlockPublicAcls, BlockPublicPolicy, IgnorePublicAcls, RestrictPublicBuckets).
   - **Versioning**: Enabled to protect artifact integrity and history across pipeline updates.
   - **SSL Enforcement**: Denies non-HTTPS transport via bucket policy (`aws:SecureTransport: false`).
   - **Removal Policy**: `DESTROY` with `autoDeleteObjects: true` for clean demo/development environment teardown.
2. **CloudFormation Stack Outputs**:
   - `ArtifactBucketName`: The physical generated bucket name.
   - `ArtifactBucketArn`: The Amazon Resource Name (ARN) of the bucket.
   - `RuntimeArtifactPrefix`: The canonical object key prefix (`runtime/`).

---

## Runtime Artifact Management

- The canonical runtime artifact (`runtime_index.json.gz`) recorded in [`infrastructure/artifact/manifest.json`](../artifact/manifest.json) is **not** uploaded directly during CDK stack synthesis.
- Artifact publishing to `s3://<ArtifactBucketName>/runtime/runtime_index.json.gz` will be handled separately via a dedicated artifact publishing/CI step.
- The raw `benchmark/HRS_metadata/metadata.jsonl` data is strictly excluded from Git, Docker images, and cloud deployments.
