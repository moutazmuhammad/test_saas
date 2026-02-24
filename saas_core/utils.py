import base64
import logging
import os
import stat
import tempfile

import paramiko

_logger = logging.getLogger(__name__)

SSH_COMMAND_TIMEOUT = 120  # seconds
SSH_CONNECT_TIMEOUT = 30  # seconds


class SSHConnection:
    """Context manager for SSH connections using paramiko.

    Usage::

        with SSHConnection(host, port, user, private_key_b64, key_type) as ssh:
            exit_code, stdout, stderr = ssh.execute('ls -la')
            ssh.write_file('/remote/path/file.txt', 'file contents')
    """

    def __init__(self, host, port, user, private_key_b64, key_type='rsa',
                 timeout=SSH_COMMAND_TIMEOUT):
        self.host = host
        self.port = port
        self.user = user
        self.private_key_b64 = private_key_b64
        self.key_type = key_type
        self.timeout = timeout
        self._client = None
        self._key_tmpfile = None

    def __enter__(self):
        self._connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._disconnect()
        return False

    def _connect(self):
        """Decode the Binary field, write to temp file, connect via paramiko."""
        key_bytes = base64.b64decode(self.private_key_b64)

        fd, self._key_tmpfile = tempfile.mkstemp(prefix='saas_ssh_', suffix='.pem')
        try:
            os.write(fd, key_bytes)
        finally:
            os.close(fd)
        os.chmod(self._key_tmpfile, stat.S_IRUSR)

        key_class_map = {
            'rsa': paramiko.RSAKey,
            'dsa': paramiko.DSSKey,
            'ecdsa': paramiko.ECDSAKey,
            'ed25519': paramiko.Ed25519Key,
        }
        key_class = key_class_map.get(self.key_type, paramiko.RSAKey)
        pkey = key_class.from_private_key_file(self._key_tmpfile)

        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self._client.connect(
            hostname=self.host,
            port=self.port,
            username=self.user,
            pkey=pkey,
            timeout=SSH_CONNECT_TIMEOUT,
            look_for_keys=False,
            allow_agent=False,
        )

    def _disconnect(self):
        """Close SSH client and remove temp key file."""
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
        if self._key_tmpfile and os.path.exists(self._key_tmpfile):
            try:
                os.unlink(self._key_tmpfile)
            except Exception:
                pass
            self._key_tmpfile = None

    def execute(self, command):
        """Execute a command over SSH.

        Returns:
            tuple: (exit_code, stdout_str, stderr_str)
        """
        _logger.info("SSH [%s@%s:%s] executing command", self.user, self.host, self.port)
        stdin, stdout, stderr = self._client.exec_command(
            command, timeout=self.timeout,
        )
        exit_code = stdout.channel.recv_exit_status()
        stdout_str = stdout.read().decode('utf-8', errors='replace')
        stderr_str = stderr.read().decode('utf-8', errors='replace')
        return exit_code, stdout_str, stderr_str

    def write_file(self, remote_path, content):
        """Write string content to a remote file via SFTP."""
        sftp = self._client.open_sftp()
        try:
            with sftp.file(remote_path, 'w') as f:
                f.write(content)
        finally:
            sftp.close()
