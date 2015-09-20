# -*- coding: utf-8 -*-
#
# vim: set ts=4 sw=4 sts=4 et :
'''
:maintainer:    Jason Mehring <nrgaway@gmail.com>
:maturity:      new
:depends:       none
:platform:      all

Salt file path utilities for managing top configurations

'''
# Import python libs
import collections
import itertools
import logging
import os
import re

from itertools import (
    chain,
    ifilter,
    imap,
    product,
    starmap,
    )

# Import salt libs
import salt.fileclient
import salt.ext.six as six

from salt.utils import dictupdate
from salt.exceptions import SaltRenderError
from salt.utils.odict import (OrderedDict, DefaultOrderedDict)

# Import custom libs
import matcher
import fileinfo

from pathutils import PathUtils
from pathinfo import PATHINFO_FIELDS

# Enable logging
log = logging.getLogger(__name__)

try:
    __context__['salt.loaded.ext.util.toputils'] = True
except NameError:
    __context__ = {}

# Define the module's virtual name
__virtualname__ = 'toputils'


def __virtual__():
    '''
    '''
    return __virtualname__


def coerce_to_list(value):
    '''Converts value to a list.
    '''
    if not value:
        value = []
    elif isinstance(value, six.string_types):
        value = [value,]
    elif isinstance(value, tuple):
        value = list(value)
    return value


class TopUtils(object):
    '''
    List status of one or all top files.  If saltenv is not provided, all
    environments will be searched
    '''
    def __init__(self, opts, **kwargs):
        self.opts = opts
        self.pathutils = PathUtils(self.opts)

        # XXX: TODO: Add to salt configuration file
        self.topd_directory = self.opts.get(u'_topd', u'_topd')

##    def topd_patterns(self, path=None, saltenv=None):
##        saltenvs = self.pathutils.saltenvs(saltenv)
##        patterns = []
##        topd_dir = '{0}{1}'.format(self.topd_directory, os.sep)
##        for env in saltenvs:
##            # Wrapped in Regex text object to prevent escaping
##            patterns.append(
##                matcher.Regex(
##                    r'{0}({1})\|.*\.top'.format(matcher.escape_text(topd_dir),
##                                                env)
##                )
##            )
##            patterns.append(
##                matcher.Regex(r'{0}({1}){2}.*\.top'.format(
##                    matcher.escape_text(topd_dir),
##                    matcher.escape_text(os.sep),
##                    env)
##                )
##            )
##        return patterns

    def topd_patterns(self, paths=None, saltenv=None):
        paths = coerce_to_list(paths)
        paths = paths or ['']
        saltenvs = self.pathutils.saltenvs(saltenv)

        patterns = []
        topd_dir = '{0}{1}'.format(self.topd_directory, os.sep)

        _topd_dir = matcher.escape_text(topd_dir)
        _os_sep = matcher.escape_text(os.sep)

        top = r'''(?ix)
            (?P<saltenv>.*?(?=[|])|)(?:[|]|)
            (?P<top>.*(?=[.]top$)|.*)
            (?P<ext>[.]top|)
        '''
        re_top = re.compile(top)

        for path in paths:
            saltenv = ''
            if path:
                try:
                    saltenv, basename, ext = re_top.match(path).groups()
                except AttributeError:
                    basename, ext = os.path.splitext(path)
                basename = matcher.escape_text(basename)
            else:
                basename = '.*'

            envs = [saltenv] if saltenv else saltenvs
            for env in envs:
                # Wrapped in Regex text object to prevent escaping
                patterns.append(
                    matcher.Regex(
                        r'{0}({1})\|{2}\.top'.format(
                            _topd_dir,
                            env,
                            basename
                        )
                    )
                )
                patterns.append(
                    matcher.Regex(
                        r'{0}({1}){2}{3}\.top'.format(
                            _topd_dir,
                            _os_sep,
                            env,
                            basename
                        )
                    )
                )
        return patterns

    def topd_pattern(self):
        '''
        Include only: _topd/<saltenv>|*.top; or
                      _topd/<saltenv>/*.top;
        '''
        pattern = fileinfo.get_pattern(PATHINFO_FIELDS,
                                       relpath=self.topd_patterns())
        return pattern

    # XXX: tops should be searched by sls name
    # tops(self, saltenv: str|list=None, patterns: [str]=None), flat: bool=None -> [str] or {str: [str]}
    def tops(self,
             saltenv=None,
             roots=None,
             files=None,
             view=None,
             flat=None,
             pillar=False,
             **patterns):
        '''
        Return a list of top files in the specified environment or a dictionary
        of all results if saltenv is None matching the given patterns.

        :type saltenv: str
        :type patterns: [str]
        :type flat: [str]
        :rtype : [str] | {str: [str]}

        :param saltenv: Can be a single saltenv such as 'base', a list of
        saltenv's such as ['base', 'all'], or None in which case all saltenv's
        will be set
        :param patterns: Patterns of files to search for. Defaults to ["*"]. Example: ["*.top", "*.sls"]
        :param flat: If True, a list of all environment values will be returned,
        otherwise a dictionary with the passed saltenv will be returned.
        The default for a single salt environment is to flatten
        '''
        if files:
            #return self.pathutils.files(files=files, **patterns)
            return self.pathutils.find(files, **patterns)

        if not roots:
            if pillar:
                include = ['pillar_roots']
            else:
                include = ['file_roots']
            roots = self.pathutils.pathinfo_roots(saltenvs=saltenv,
                                                 include=include)

        view = view if view else 'all'
        default_pattern = {
            'relpath': ['*.top'],
            }

        # Compress patterns values to make sure all patterns have values,
        # otherwise use default_pattern
        if not list(itertools.compress(patterns.values(), patterns.values())):
            patterns = default_pattern

        fileinfo_extra = {}
        fileinfo_extra['_add_hook'] = TopUtils.hook_fix_top_saltenv
        fileinfo_extra['topd_pattern'] = self.topd_pattern()

        return self.pathutils.files(
            saltenv=saltenv,
            roots=roots,
            view=view,
            flat=flat,
            fileinfo_extra=fileinfo_extra,
            **patterns)

##    def get(self, paths=None, saltenv=None):
##        return self.tops(paths, saltenv)

    @staticmethod
    def prepend(text, sequence):
        sequence = coerce_to_list(sequence)
        for index, path in enumerate(sequence):
            if path.startswith(text):
                continue
            sequence[index] = '{0}{1}'.format(text, path)
        return sequence

    def prepare_paths(self, paths, saltenv, default=None):
        '''
        Prepend relpath of _topd directory to paths
        '''
        topd_dir = '{0}{1}'.format(self.topd_directory, os.sep)
        paths = self.prepend('{0}'.format(topd_dir), paths)
        if not paths and default:
            paths.extend(coerce_to_list(default))
        return paths

    def include_links(self, tops):
        includes = []
        try:
            top = iter(tops).next()
            saltenv = matcher.getter('saltenv', top)
            abspath = matcher.getter('abspath', top)
        except StopIteration:
            return includes

        for topinfo in tops:
            if os.path.islink(abspath(topinfo)):
                path = os.path.realpath(abspath(topinfo))
                includes.extend(self.pathutils.find(saltenv=saltenv(topinfo),
                                                    abspath=path))
        return includes

    def enabled(self, paths=None, saltenv=None, files=None, view=None,
                flat=False, pillar=False):
        '''
        '''
        view = view or ['saltenv', 'abspath']
        paths = self.topd_patterns(paths, saltenv)
        enabled = self.tops(saltenv, files=files, view='all',
                            relpath=paths, pillar=pillar)
        return fileinfo.fileinfo_view(enabled, view=view, flat=flat)

    #
    # TODO:
    # =====
    #
    # Add better logic for enabled/disabled... Only enabled if in topd direct
    # AND the link is valid to the parent!
    #
    # masked values (/dev/null) could fail the virtual()
    #   - Not sure how to handle that; monkey patch? or add into the section
    #     where the modules initially loads
    #
    # topd and *.top should be same name; maybe within own ENV?
    #
    # enabled; disabled should be same as is_enabled; IE only print status
    #                   - Use reporting / status  for path details or provide
    #                     options for more detail
    #
    # symlinks = client.symlink_list(saltenv='base',  prefix='')
    # enabled = top in symlinks
    #

    # XXX: send args to another function to clean them up; too many
    #
    # XXX: Disabled should include disabled *.top and *.sls that do not have
    #      a .top
    def disabled(self, paths=None, saltenv=None, files=None, view=None,
                 flat=False, pillar=False):
        '''
        '''
        view = view or ['saltenv', 'abspath']
        # XXX: Why preparing paths for disabled; Need to find ALL *tops
        #      not just in _tops directories!!
        paths = self.prepare_paths(paths, saltenv, default=['*.top'])

        tops = self.tops(saltenv, files=files, view='all',
                         relpath=paths, pillar=pillar)
        enabled = set(self.enabled(saltenv=saltenv, files=tops,
                                   view='all', pillar=pillar))
        enabled.update(set(self.include_links(enabled)))
        disabled = set(tops).difference(enabled)
        return fileinfo.fileinfo_view(disabled, view=view, flat=flat)

    def status(self, view=None, flat=None, **kwargs):
        view = view or ['saltenv', 'abspath']
        status = {}
        for key, topinfo in six.iteritems(kwargs):
            status[key] = fileinfo.fileinfo_view(topinfo, view=view, flat=flat)
        return status

    def is_enabled(self, paths=None, saltenv=None, view=None, flat=None, pillar=False):
        '''
        '''
        tops = self.tops(paths, saltenv, view='all', pillar=pillar)
        enabled = self.enabled(paths, saltenv, files=tops,
                               view='all', pillar=pillar)
        disabled = self.disabled(paths, saltenv, files=tops,
                                 view='all', pillar=pillar)
        return self.status(disabled=disabled, enabled=enabled)

    # enable <state> or <top>
    #   - Will create new file if top does not exist yet
    #   - If top and state exists, top wins; link
    #
    # convert salt://top.sls
    # convert existing tops to topd format
    '''
    all:
        - /srv/formulas/all/privacy-formula/privacy/init.top
            enable privacy saltenv=all
            enable 'all|privacy'
            enable 'all/privacy'
    base:
        - /srv/salt/test/test-top.top
            enable test.test-top

        - /srv/formulas/base/salt-formula/salt/formulas.top
            enable salt.formulas

        - /srv/formulas/base/salt-formula/salt/pkgrepo/pkgrepo.top
            enable salt.pkgrepo

        - /srv/formulas/base/salt-formula/salt/gitfs_dulwich.top
            enable salt.gitfs_dulwich

        - /srv/formulas/base/salt-formula/salt/standalone.top
            enable salt.standalone

        - /srv/salt/_topd/test.top
            XXX: THIS SHOULD NOT SHOW AS DISABLED; ITS ENABLED!

        - /srv/formulas/base/salt-formula/salt/user.top
            enable salt.user
    '''


##    def _update(self, adict, label, data):
##        if data:
##            adict[label] = data

    # XXX: need to re-add filtering back in
    def report(self, paths=None, saltenv=None):
        from timeit import default_timer as timer
        print('Report 1: Starting timer...')
        start = timer()
        report = self.pathutils.report(files=self.tops(saltenv, flat=False))
        end = timer()
        print 'Report 1 Time: {0}'.format(end - start)
        print

        print('Report 2: Starting timer...')
        start = timer()

        tops = self.tops(saltenv, paths, view='all', flat=False)
        #saltenvs = [saltenv] if saltenv else self.saltenvs
        #for env in saltenvs:
        #    self._update(report, env, self.tops(env, paths, flat=True))
        disabled = self.disabled(saltenv, paths, files=tops,
                                 view='all', flat=False)
        enabled = self.enabled(saltenv, paths,
                               files=tops, view='all', flat=False)

        end = timer()
        print 'Report 2 Time: {0}'.format(end - start)
        print

        return self.status(all=tops,
                           disabled=disabled,
                           enabled=enabled)

    @staticmethod
    def hook_fix_top_saltenv(parent, element, **kwargs):
        '''
        Check to see if element is a top file and re-create element if saltenv
        is incorrect.

        This is done here instead of when initially creating the element so
        this regex match would not need to happen on every file; only mathced
        ones.
        '''
        pattern = kwargs.get('topd_pattern', None)
        if pattern:
            try:
                # Filter _topd/<saltenv>|*.top; or
                #        _topd/<saltenv>/*.top;
                match = matcher.match([element], pattern).next()
            except StopIteration:
                match = False
            if match:
                # XXX: Maybe create getters automaticly in __init__ for each
                #      field if it takes too long
                saltenv = matcher.getter('saltenv', element)
                file_root = matcher.getter('file_root', element)
                cache_root = matcher.getter('cache_root', element)
                abspath = matcher.getter('abspath', element)
                if match.lastindex and match.group(match.lastindex) != saltenv(element):
                    kwargs = kwargs.copy()
                    kwargs['saltenv'] = match.group(match.lastindex)
                    element = parent.element(root=file_root(element) or cache_root(element),
                                           abspath=abspath(element),
                                           **kwargs)
        return element
