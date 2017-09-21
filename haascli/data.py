import os
import time
import logging
import base64

import click
from executor.ssh.client import RemoteCommand
from .stack import get_ip

logger = logging.getLogger(__name__)


@click.group(context_settings=dict(help_option_names=['-h', '--help']))
@click.option('-b', '--bucket', default='hpcc_checkpoint')
@click.option('-i', '--identity', help="PEM file")
@click.option('--wait/--no-wait', default=True,
              help='Waiting for the operation to complete')
@click.pass_context
def cli(ctx, **kwargs):
    """Data related operations
    """
    ctx.obj.update(kwargs)
    if 'identity' not in kwargs:
        print(click.style('need an identity file', fg='red'))
        ctx.abort()


@cli.command()
@click.argument('stack-name')
@click.argument('resource-name',
                type=click.Choice(['dfs', 'workunit', 'dropzone']))
@click.argument('checkpoint-name')
@click.option('--regex', default='*',
              help='The regex (filename glob) to filter file path or '
              'workunit id')
@click.pass_context
def save(ctx, stack_name, resource_name, checkpoint_name, regex):
    service_output = "/tmp/haas_data.out"

    # @TODO: if the required library is installed in system, the
    # init.sh can be removed @TODO: the path to checkpoint.py needs to
    # reflect the changes in auto_hpcc.sh

    master_ip = get_ip(stack_name, "MasterASG")

    # didn't use RemoteCommand because I cannot make it work
    # base64 turns out to be an easy way to escape commands
    cmd = "source /home/osr/haas/scripts/init.sh && "\
          "$(nohup python /home/osr/haas/scripts/checkpoint.py --name {} "\
          "service_{} save --regex '{}' "\
          "> {} 2>&1 &)".format(
              checkpoint_name, resource_name, regex, service_output)
    os.system("ssh -i {} -l {} {} 'echo {} | base64 -d | bash'".format(
        ctx.obj['identity'],
        'ubuntu',
        master_ip,
        base64.b64encode(cmd.encode()).decode())
    )

    if ctx.obj['wait']:
        _wait_until_complete(master_ip, conf)


@cli.command()
@click.argument('checkpoint-name')
@click.argument('resource-name',
                type=click.Choice(['dfs', 'workunit', 'dropzone']))
@click.argument('stack-name')
@click.option('--regex', default='*',
              help='The regex (filename glob) to filter file path or workunit '
              'id')
@click.pass_context
def restore(ctx, checkpoint_name, resource_name, stack_name, regex):
    '''Restore data from S3'''
    service_output = "/tmp/haas_data.out"
    master_ip = get_ip(stack_name, "MasterASG")

    cmd = "source /home/osr/haas/scripts/init.sh && "\
          "$(nohup python /home/osr/haas/scripts/checkpoint.py "\
          "--name {} service_{} restore --regex '{}' "\
          "> {} 2>&1 &)".format(
              checkpoint_name, resource_name, regex, service_output)
    os.system("ssh {} 'echo {} | base64 -d | bash'".format(
        ctx.obj['identity'],
        'ubuntu',
        master_ip,
        base64.b64encode(cmd.encode()).decode())
    )

    if ctx.obj['wait']:
        _wait_until_complete(master_ip, ctx.obj['identity'])


@cli.command()
@click.argument('stack_name')
@click.pass_context
def progress(ctx, stack_name):
    '''Check progress of checkpointing operation'''
    master_ip = get_ip(stack_name, "MasterASG")

    cmd = RemoteCommand(master_ip,
                        'source ~/haas/scripts/init.sh; '
                        'python /home/osr/haas/scripts/checkpoint.py '
                        '--name {} available; echo $?',
                        identity_file=ctx.obj['identity'],
                        ssh_user='ubuntu',
                        capture=True)
    cmd.start()
    if cmd.output == '0':
        print("No service is running")
    else:
        print('Data service is running....')
        RemoteCommand(master_ip, "tail -f /tmp/haas_data.out",
                      identity_file=ctx.obj['identity'],
                      ssh_user='ubuntu',
                      check=False).start()


@cli.command()
@click.argument('stack-name')
@click.option('--regex', default='*', help='The regex (filename glob) to filter file path or workunit id')
@click.pass_context
def resize(ctx, stack_name, regex):
    topology = ClusterTopology.parse(stack_name)
    conf = HaasConfigurationManager().get(ctx.obj['config'])
    cmd = "python3 /opt/haas/resize.py '{}'".format(regex)

    os.system("ssh -i {} -l {} {} 'echo {} | base64 -d | bash'".format(
        conf.get(HaasConfigurationKey.HAAS_SSH_KEY),
        conf.get(HaasConfigurationKey.HAAS_SSH_USER),
        topology.get_master_ip(),
        base64.b64encode(cmd.encode()).decode())
    )


def _wait_until_complete(master_ip, identity):
    while True:
        cmd = RemoteCommand(master_ip, "pgrep -f checkpoint.py",
                            identity_file=identity,
                            ssh_user='ubuntu',
                            capture=True, check=False)
        cmd.start()
        pid_list = cmd.output
        # print(pid_list, len(pid_list.splitlines()))
        if len(pid_list.splitlines()) > 0:
            print("Data service still processing")
            time.sleep(5)
        else:
            break
