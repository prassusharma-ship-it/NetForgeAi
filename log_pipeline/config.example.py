"""
List every client/server you want log data from. Copy this file to
config.py (which you should .gitignore, since it holds credentials) and
fill in your real hosts.
"""

SERVERS = [
    {
        "host": "1.2.3.4",
        "port": 22,
        "user": "root",
        "key_path": "~/.ssh/id_rsa",   # or use "password": "..." instead
        "remote_path": "/var/log/auth.log",   # Debian/Ubuntu. Use /var/log/secure on CentOS/RHEL
    },
    # add more servers here, e.g. a second VPS acting as a "client" in your demo
    # {
    #     "host": "5.6.7.8",
    #     "port": 22,
    #     "user": "ubuntu",
    #     "key_path": "~/.ssh/id_rsa",
    #     "remote_path": "/var/log/auth.log",
    # },
]
