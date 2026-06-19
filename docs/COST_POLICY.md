# Cost Policy

The default project architecture runs entirely on a developer laptop with Docker and costs
`$0` in cloud charges.

## Hard Rules

- No AWS resource may be created without an explicit Terraform cost guardrail.
- Any optional AWS deployment must have an AWS Budget alert configured first.
- The maximum permitted AWS spend for this project is `$5` total.
- Avoid NAT Gateway, managed Kafka, always-on compute, and other resources with hourly charges.
- Every cloud phase must include a tested teardown command.

AWS is not required for the core project and is intentionally absent from the first release.

