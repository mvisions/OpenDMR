"""The Pi-Star hotspot with pistar-signal-gen (E:/exam/pistar-signal-gen) over ssh: run a command, upload a file.

  python nxdn/py/pi.py run "command"
  python nxdn/py/pi.py put local remote

The address and password come from the environment (PISTAR_HOST, PISTAR_USER, PISTAR_PASS), never from the
repository.
"""
import os
import sys

import paramiko


def connect():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(os.environ['PISTAR_HOST'], username=os.environ.get('PISTAR_USER', 'pi-star'),
              password=os.environ['PISTAR_PASS'], timeout=10)
    return c


def run(c, cmd):
    _, out, err = c.exec_command(cmd, timeout=60)
    o = out.read().decode(errors='replace')
    e = err.read().decode(errors='replace')
    return o + e


def put(c, local, remote):
    """through cat (the sftp server of Pi-Star does not reach /tmp)"""
    i, o, _ = c.exec_command('cat > %s' % remote)
    i.write(open(local, 'rb').read())
    i.channel.shutdown_write()
    o.channel.recv_exit_status()


def main():
    c = connect()
    if sys.argv[1] == 'run':
        sys.stdout.write(run(c, sys.argv[2]))
    elif sys.argv[1] == 'put':
        put(c, sys.argv[2], sys.argv[3])
        print('put', sys.argv[3])


if __name__ == '__main__':
    main()
