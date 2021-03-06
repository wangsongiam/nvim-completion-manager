#!/usr/bin/env python
# -*- coding: utf-8 -*-

# For debugging
# NVIM_PYTHON_LOG_FILE=nvim.log NVIM_PYTHON_LOG_LEVEL=INFO nvim

import cm
cm.register_source(name='cm-tmux',
                   abbreviation='Tmux',
                   priority=4,
                   cm_refresh_patterns=[r'[0-9a-zA-Z_#]{3,}$'],
                   events=['CursorHold','CursorHoldI','FocusGained','WinEnter'],
                   detach=1)

import os
import re
import logging
import subprocess

logger = logging.getLogger(__name__)

class Source:

    def __init__(self,nvim):

        self._nvim = nvim

        if 'TMUX' not in  os.environ:
            # suiside for tmux not available
            logger.info('no tmux, suiside')
            nvim.call("cm#remove_source",'cm-tmux')

        logger.info('tmux: %s', os.environ['TMUX'])

        self._words = set()

        self._split_pattern = r'[^0-9a-zA-Z_]+'
        self._kw_pattern = r'[0-9a-zA-Z_]'

        self.refresh_keyword()

    def cm_event(self,event,ctx,*args):
        if event in ['CursorHold','CursorHoldI','FocusGained','BufEnter']:
            logger.info('refresh_keyword on event %s', event)
            self.refresh_keyword()


    def refresh_keyword(self):
        pat = re.compile(self._split_pattern)
        self._words = set()

        # tmux list-window -F '#{window_index},#{window_panes}'
        # tmux capture-pane -p -t "$window_index.$pane_index"
        proc = subprocess.Popen(args=['tmux','list-window','-F','#{window_index},#{window_panes}'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        outs,errs = proc.communicate(timeout=15)
        outs = outs.decode('utf-8')
        logger.info('list-window: %s', outs)

        # parse windows
        panes = []
        for line in outs.split("\n"):
            fields = line.split(',')
            if len(fields)!=2:
                continue
            # windows.append(fields)
            win_index = fields[0]
            pane_cnt = int(fields[1])
            for pane_id in range(pane_cnt):
                proc = subprocess.Popen(args=['tmux','capture-pane','-p','-t','%s.%s' % (win_index,pane_id)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                outs,errs = proc.communicate(timeout=15)
                try:
                    outs = outs.decode('utf-8')
                    panes.append(outs)
                except Exception as ex:
                    logger.exception('exception, failed to decode output, %s', ex)
                    pass


        for pane in panes:
            for word in re.split(pat,pane):
                self._words.add(word)

        logger.info('keyword refresh complete, count: %s', len(self._words))


    def cm_refresh(self,info,ctx):

        lnum = ctx['lnum']
        col = ctx['col']
        typed = ctx['typed']
 
        kw = re.search(self._kw_pattern+r'*?$',typed).group(0)
        startcol = col-len(kw)

        matches = (dict(word=word,icase=1)  for word in self._words)
        matches = cm.get_matcher(self._nvim).process(info['name'], ctx, startcol, matches)

        # cm#complete(src, context, startcol, matches)
        self._nvim.call('cm#complete', info['name'], ctx, startcol, matches, async=True)

