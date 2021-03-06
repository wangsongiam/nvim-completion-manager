# -*- coding: utf-8 -*-

# For debugging
# NVIM_PYTHON_LOG_FILE=nvim.log NVIM_PYTHON_LOG_LEVEL=INFO nvim

import os
import sys
import re
import logging
import importlib
from neovim import attach, setup_logging
import cm

logger = logging.getLogger(__name__)

def main():

    start_type = sys.argv[1]

    # the default nice is inheriting from parent neovim process.  Increment it
    # so that heavy calculation will not block the ui.
    try:
        os.nice(5)
    except:
        pass

    # psutil ionice
    try:
        import psutil
        p = psutil.Process(os.getpid())
        p.ionice(psutil.IOPRIO_CLASS_IDLE)
    except:
        pass

    if start_type == 'core':
        modulename = 'cm_core'
        source_name = ''
        addr = sys.argv[2]
    else:
        modulename = sys.argv[2]
        source_name = sys.argv[3]
        addr = sys.argv[4]

    # setup for the module 
    setup_logging(modulename)
    logger = logging.getLogger(modulename)
    logger.setLevel(get_loglevel())

    logger = logging.getLogger(__name__)
    logger.setLevel(get_loglevel())

    # connect neovim
    nvim = nvim_env(addr)

    # change proccess title
    try:
        import setproctitle
        setproctitle.setproctitle('nvim-completion-manager %s' % modulename)
    except:
        pass

    try:
        if start_type == 'core':

            import cm_core
            nvim.vars['_cm_channel_id'] = nvim.channel_id
            handler = cm_core.CoreHandler(nvim)
            logger.info('starting core, enter event loop')
            cm_event_loop('core',logger,nvim,handler)

        elif start_type == 'channel':

            nvim.call('cm#_update_channel_id',source_name,nvim.channel_id)

            if sys.version_info.major==2:
                # python2 doesn't support namespace package
                # use load_source as a workaround
                import imp
                file = modulename.replace('.','/')
                exp = 'globpath(&rtp,"pythonx/%s.py",1)' % file
                path = nvim.eval(exp).strip()
                logger.info('python2 file path: %s, exp: %s',path, exp)
                m = imp.load_source(modulename,path)
            else:
                m = importlib.import_module(modulename)

            handler = m.Source(nvim)
            logger.info('handler created, entering event loop')
            cm_event_loop('channel',logger,nvim,handler)

    except Exception as ex:
        logger.exception('Exception when running %s: %s', modulename, ex)
        exit(1)
    finally:
        # terminate here
        exit(0)

def nvim_env(addr):
    try:
        nvim = attach('stdio')
    except Exception as ex:
        logger.exception('Exception when running : %s', ex)
        logger.info("Fallback to servername: %s",addr)
        # create another connection to avoid synchronization issue?
        if len(addr.split(':'))==2:
            addr,port = addr.split(':')
            port = int(port)
            nvim = attach('tcp',address=addr,port=port)
        else:
            nvim = attach('socket',path=addr)


    # setup pythonx
    pythonxs = nvim.eval('globpath(&rtp,"pythonx",1)')
    for path in pythonxs.split("\n"):
        if not path:
            continue
        if path not in sys.path:
            sys.path.append(path)
    return nvim


def get_loglevel():
    # logging setup
    level = logging.INFO
    if 'NVIM_PYTHON_LOG_LEVEL' in os.environ:
        l = getattr(logging,
                os.environ['NVIM_PYTHON_LOG_LEVEL'].strip(),
                level)
        if isinstance(l, int):
            level = l
    return level


def cm_event_loop(type,logger,nvim,handler):

    def on_setup():
        logger.info('on_setup')

    def on_request(method, args):

        func = getattr(handler,method,None)
        if func is None:
            logger.info('method: %s not implemented, ignore this request', method)
            return None

        func(*args)

    def on_notification(method, args):
        logger.debug('%s method: %s, args: %s', type, method, args)

        if type=='channel' and method=='cm_refresh':
            ctx = args[1]
            # The refresh calculation may be heavy, and the notification queue
            # may have outdated refresh events, it would be  meaningless to
            # process these event
            if nvim.call('cm#context_changed',ctx):
                logger.info('context_changed, ignoring context: %s', ctx)
                return

        func = getattr(handler,method,None)
        if func is None:
            logger.info('method: %s not implemented, ignore this message', method)
            return

        func(*args)

        logger.debug('%s method %s completed', type, method)

    nvim.run_loop(on_request, on_notification, on_setup)

    # shutdown
    func = getattr(handler,'cm_shutdown',None)
    if func:
        func()


main()

