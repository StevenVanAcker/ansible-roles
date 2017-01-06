This role configures a host to use AWS resources
by installing some AWS specific tools (awscli, ecrtool, ...)
If the "credentialsfile" option is specified, it indicates the path of a file with credentials used by awscli
and is copied to the host.
If the host is an Amazon EC2 host with an IAM role, the credentials are not copied since they are already present.
