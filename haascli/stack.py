import os
# import json

import click
import boto3
import yaml
import requests
from botocore.exceptions import ClientError


@click.group(context_settings=dict(help_option_names=['-h', '--help']))
@click.option('-c', '--config', default='.')
@click.pass_context
def cli(ctx, **kwargs):
    """Stack related operations
    """


@cli.command()
@click.argument('stack_name')
@click.option('-f', '--config_file')
@click.option('-p', '--parameter', multiple=True)
@click.pass_context
def create(ctx, stack_name, config_file, parameter):
    debug = ctx.obj['debug']
    execute = ctx.obj['exec']
    if debug:
        click.echo('haas stack create stack_name={}'.format(stack_name))
        if not execute:
            click.echo(click.style('no exec mode', fg='yellow'))

    parameters = {}
    if config_file:
        config_path = os.path.join(ctx.obj['config_dir'], config_file)
        try:
            f = open(config_path, 'r')
            # @TODO: assuming all files are yaml
            parameters = yaml.load(f)
        except IOError as e:
            click.echo(click.style(str(e), fg='red'))
            ctx.abort()
    else:
        for param in parameter:
            try:
                key, val = param.split('=')
            except IndexError:
                val = True
            if key in parameters:
                click.echo(click.style('overwriting {} to {} was {}'.format(
                    key, val, parameters[key]), fg='red'))
            parameters[key] = val

    try:
        # template_url MUST be defined; but it isn't a parameter
        template_url = parameters['template_url']
        del parameters['template_url']
    except KeyError as e:
        click.echo(click.style('must define template_url', fg='red'))
        ctx.abort()

    if debug:
        click.echo('template url is {}'.format(template_url))

        for k, v in parameters.items():
            click.echo('parameter {} is {}'.format(k, v))

    stack_id = None
    if execute:
        try:
            client = boto3.client('cloudformation')
        except ClientError as e:
            click.echo(click.style('ERROR(boto): ' + str(e), fg='red'))
            ctx.abort()

    # prepare parameters for boto call
    parameter_list = []
    for param in parameters:
        parameter_list.append(dict(ParameterKey=param,
                                   ParameterValue=parameters[param]))
    try:
        if template_url.startswith('http'):
            if 's3' in template_url:
                if not execute:
                    click.echo(click.style('not executing', fg='yellow'))
                    response = {}
                else:
                    response = client.create_stack(
                        StackName=stack_name,
                        TemplateUrl=template_url,
                        Parameters=parameter_list,
                        Capabilities=['CAPABILITY_IAM'],
                    )
                    # so that we can have one clause for TemplateBody version
                body = False
            else:
                # fetch url contents
                r = requests.get(template_url, timeout=5.0)
                body = r.text
        else:
            if template_url.startswith('file:'):
                f = template_url[5].strip('/')
            else:
                f = template_url
            body = open(f, 'r').read()

        if body:
            if not execute:
                click.echo(click.style('not executing', fg='yellow'))
                response = {}
            else:
                # if body is false create_stack was called above
                response = client.create_stack(
                    StackName=stack_name,
                    TemplateBody=body,
                    Parameters=parameter_list,
                    Capabilities=['CAPABILITY_IAM'],
                )

        if debug:
            msg = '\tStackName={}\n\tTemplateUrl={}\n'\
                  '\tParameters={}\n'\
                  '\tCapabilities=[\'CAPABILITY_IAM\']'\
                  .format(stack_name, template_url, parameter_list)
            click.echo(msg)

        stack_id = response['StackId'] if 'StackId' in response else None
        click.echo("StackId:", str(stack_id))

    except IOError as e:
        # @TODO: needs better exception handling
        click.echo(click.style(str(e), fg='red'))
        ctx.abort()
    except requests.exceptions.RequestException as e:
        click.echo(click.style(str(e), fg='red'))
        ctx.abort()
    except ClientError as e:
        click.echo(click.style('ERROR(boto): ' + str(e), fg='red'))
        ctx.abort()


@cli.command()
@click.option('-l', '--long', is_flag=True)
@click.option('-f', '--filter', multiple=True)
@click.pass_context
def list(ctx, long, filter):
    if ctx.obj['debug']:
        click.echo('haas stack list long={} filter={}'.format(long, filter))

    if not ctx.obj['exec']:
        click.echo(click.style('not executing', fg='yellow'))
        return

    try:
        client = boto3.client('cloudformation')
        if filter:
            response = client.list_stacks(StackStatusFilter=filter)
        else:
            response = client.list_stacks()

        for stack in response['StackSummaries']:
            print(stack['StackName'], 'status:', stack['StackStatus'])
            if long:
                print('\tTemplate:', stack['TemplateDescription'])
                print('\tId:', stack['StackId'])
                print('\tCreated:', str(stack['CreationTime']))
                if 'DeletionTime' in stack:
                    print('\tDeleted:', str(stack['DeletionTime']))
    except ClientError as e:
        click.echo(click.style('ERROR(boto): ' + str(e), fg='red'))
        ctx.abort()


@cli.command()
@click.argument('stack-name')
@click.pass_context
def delete(ctx, stack_name):
    if ctx.obj['debug']:
        click.echo('haas stack delete stack_name={}'.format(stack_name))

    if ctx.obj['exec']:
        try:
            client = boto3.client('cloudformation')
            response = client.delete_stack(StackName=stack_name)
            print(response)
        except ClientError as e:
            click.echo(click.style('ERROR(boto): ' + str(e), fg='red'))
            ctx.abort()
    else:
        click.echo(click.style('not executing', fg='yellow'))
        return


@cli.command()
@click.pass_context
def update(ctx):
    pass
