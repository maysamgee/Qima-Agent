# Public RDS trust bundle

`rds-global-bundle.pem` is Amazon's public CA bundle downloaded from
https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem.
It contains certificates only, no private keys. ECS uses sslmode=verify-full and
this root bundle for RDS hostname and certificate validation. Refresh it as part
of AWS CA rotation maintenance, rebuild images and test before deploying.
