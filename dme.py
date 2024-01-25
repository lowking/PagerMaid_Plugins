""" Module to automate message deletion. """
from pagermaid import version
from pagermaid.listener import listener
from pagermaid.utils import lang
from pagermaid.modules.prune import selfprune


@listener(is_plugin=False, outgoing=True, command="dme",
          description=lang('sp_des'),
          parameters=lang('sp_parameters'))
async def dme(context):
    """ Deletes specific amount of messages you sent. """
    await selfprune(context)
