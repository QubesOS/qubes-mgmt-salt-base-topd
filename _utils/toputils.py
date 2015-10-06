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
import copy
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
from pathinfo import (
    PathInfo,
    PATHINFO_FIELDS
    )

# Enable logging
log = logging.getLogger(__name__)

try:
    __context__['salt.loaded.ext.util.toputils'] = True
except NameError:
    __context__ = {}

# Define the module's virtual name
__virtualname__ = 'toputils'

TOPINFO_FIELDS = ('saltenv', 'file_root', 'cache_root', 'abspath', 'relpath',
                  'is_pillar', 'toppath', 'realpath')


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


class TopInfo(PathInfo):
    def __init__(self, parent, match_each=True, **patterns):
        '''
        match_each:
            If True, each file path is matched which prevents uses less memory
            but sacrifices performance a little bit.  If False, the complete
            list is matched after all the file infomations has been added to
            pathinfo

        patterns:
            Contains the patterns to match.
            Example:
                { 'saltenv': 'base', 'relpath': ['*.sls'] }
        '''
        super(TopInfo, self).__init__(match_each=match_each,
                                      **patterns)
        self.parent = parent
        self.TopInfo = collections.namedtuple('Info', TOPINFO_FIELDS)

    def topinfo_element(self, element, **kwargs):
        '''
        Check to see if element is a top file and re-create element if saltenv
        is incorrect.

        This is done here instead of when initially creating the element so
        this regex match would not need to happen on every file; only mathced
        ones.
        '''
        # XXX: Gid rid of needing parent
        pattern = self.parent.pattern_all
        element = element._asdict()

        relpath = element['relpath']
        match = pattern.match(relpath)
        if match:
            info = match.groupdict()
            relpath = info['top'] + info['ext']
            if element['saltenv'] != info['saltenv']:
                element['saltenv'] = info['saltenv']

        element['toppath'] = self.parent.toppath(element, verify=False)

        if os.path.islink(element['abspath']):
            element['realpath'] = os.path.realpath(element['abspath'])
        else:
            element['realpath'] = ''

        return self.TopInfo(**element)

    def add_element(self, element, **kwargs):
        element = self.topinfo_element(element, **kwargs)
        self._elements.add(element)


class TopUtils(PathUtils):
    '''
    List status of one or all top files.  If saltenv is not provided, all
    environments will be searched
    '''
    def __init__(self, opts, pillar=False, **kwargs):
        super(TopUtils, self).__init__(opts=opts, pillar=pillar, **kwargs)

        # XXX: TODO: Add to salt configuration file
        self.topd_directory = self.opts.get(u'topd_dir', u'_topd')

        if pillar:
            # XXX: TODO: Add to salt configuration file
            self.topd_base = self.opts.get(u'topd_base_pillar', u'/srv/pillar')
        else:
            # XXX: TODO: Add to salt configuration file
            self.topd_base = self.opts.get(u'topd_base_state', u'/srv/salt')

        # All enabled tops pattern
        self.pattern_enable = re.compile(r'{0}{1}*.top'.format(
            os.path.join(self.topd_base, self.topd_directory), os.sep))

        # All tops pattern
        self.pattern_all = re.compile(matcher.Regex(r'''(?ix)
            (?P<dir> .*? )
            (?P<saltenv> {0} )
            (?P<sep> [{1}] | [|] )
            (?P<top>.*(?=[.]top$)|.*)
            (?P<ext>[.]top|)
            '''.format('|'.join(self.saltenvs()), os.sep)))

        self._toplist = self.files()
        self._tops = self.tops()

    def tops(self, saltenv=None):
        '''
        Return a list of tops files in the specified environment or a dictionary
        of all results if saltenv is None.
        '''
        # Only return SALTENV if provided, otherwise ALL
        try:
            if saltenv:
                return {saltenv: self._tops[saltenv]}
            return self._tops
        except AttributeError:
            pass

        toplist = self.files(saltenv=saltenv)

        tops = DefaultOrderedDict(list)
        for info in toplist:
            toppath = self.toppath(info, verify=False)
            tops[self.get(info, 'saltenv')].append(toppath)

        if saltenv:
            return {saltenv: tops[saltenv]}
        return tops

    def path_type(self, path, saltenv=None):
        '''
        Return path type.
        '''
        if self.is_toppath(path, saltenv):
            return 'toppath'

        return super(TopUtils, self).path_type(path, saltenv)

    def path(self, path, saltenv=None, path_type=None):
        '''
        Relative salt path is the base path that all paths rely on.  Any
        conversions from formats that are not relative will happen here.
        '''
        if isinstance(path, list):
            return [self.path(p, saltenv) for p in path]

        path_type = path_type or self.path_type(path, saltenv)

        # XXX: Grabs 1st entry.  Maybe need more logic
        if path_type in ['toppath']:
            tops = self.files(saltenv=saltenv, toppath=path)
            try:
                topinfo = iter(tops).next()
                relpath = matcher.getter('relpath', topinfo)
                return relpath(topinfo)
            except StopIteration:
                return ''

        return super(TopUtils, self).path(path, saltenv, path_type=path_type)

    def is_relpath(self, path, saltenv=None):
        '''
        path:      'topd/init.sls'
        relpath:   'topd/init.sls'
        '''
        try:
            if path.endswith('.top'):
                return False
        except AttributeError:
            pass
        return super(TopUtils, self).is_relpath(path, saltenv)

    # XXX Add to docs
    def is_toppath(self, path, saltenv=None):
        '''
        toppath: 'salt'        (relpath: salt/init.top)
        toppath: 'salt.minion' (relpath: salt/minion.top)
        toppath: 'salt.minion' (relpath: topd/base|salt.minion)
        '''
        return bool(set(ifilter(
            lambda x: x==path,
            chain.from_iterable(six.itervalues(self.tops())))))

    # XXX Add to docs
    def toppath(self, path, saltenv=None, verify=True):
        '''
        toppath: 'salt'        (relpath: salt/init.top)
        toppath: 'salt.minion' (relpath: salt/minion.top)
        toppath: 'salt.minion' (relpath: topd/base|salt.minion)
        '''
        if isinstance(path, list):
            return [self.toppath(p, saltenv) for p in path]
        try:
            saltenv = self.get(path, 'saltenv')
            relpath = self.get(path, 'relpath')
        except AttributeError:
            if not path.endswith('.top'):
                path = path + '.top'
            if self.is_toppath(path, saltenv):
                return path
            saltenv = saltenv or self.saltenv(path, saltenv)
            try:
                relpath = self.relpath(path, saltenv)
            except SaltRenderError:
                return ''

        topd_dir = self.opts.get(u'topd_dir', u'_topd')
        if relpath.startswith(self.topd_directory):
            relpath = relpath.split(self.topd_directory + os.sep)[1]

        match = self.pattern_all.match(relpath)
        if match:
            info = match.groupdict()
            relpath = info['top'] + info['ext']

        top = relpath.lower().split('/init.top')[0]
        top = os.path.splitext(top)[0].replace('/', '.')
        top = top + '.top'

        if not verify or self.is_toppath(top, saltenv):
            return top
        return ''

    # tops(self, saltenv: str|list=None, patterns: [str]=None), flat: bool=None -> [str] or {str: [str]}
    def files(self,
             saltenv=None,
             roots=None,
             files=None,
             view=None,
             flat=None,
             force=False,
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
        # Reset cache
        if force:
            self._toplist = None

        try:
            files = files or self._toplist
        except AttributeError:
            pass

        if files:
            return self.find(files, **patterns)

        if not roots:
            if self.pillar:
                include = ['pillar_roots']
            else:
                include = ['file_roots']

            roots = self.pathinfo_roots(saltenvs=saltenv, include=include)

        # XXX: Let look at ALWAYS returning 'raw'
        #      Same for ALL methods; so remove that feature from ALL methods
        #      and have display methods like status and report handle views
        view = view if view else 'raw'
        default_pattern = {
            'relpath': ['*.top'],
            }

        # Compress patterns values to make sure all patterns have values,
        # otherwise use default_pattern
        if not list(itertools.compress(patterns.values(), patterns.values())):
            patterns = default_pattern

        topinfo = TopInfo(parent=self,
                          match_each=True,
                          **patterns)

        self._toplist = super(TopUtils, self).files(
            saltenv=saltenv,
            roots=roots,
            view=view,
            flat=flat,
            pathinfo=topinfo,
            **patterns)

        return self._toplist

    def prepare_paths(self, paths):
        seen = set()
        unseen = set()

        if not paths:
            unseen.add('No top files provided')
        else:
            for path in paths:
                toppath = self.toppath(path)
                if toppath:
                    seen.add(toppath)
                else:
                    unseen.add(path)

        return seen, unseen

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
                realpath = os.path.realpath(abspath(topinfo))
                includes.extend(self.files(saltenv=saltenv(topinfo),
                                           abspath=realpath))
        return includes

    def is_enabled(self, paths=None, saltenv=None, view=None, flat=None):
        '''
        '''
        tops = self.files(saltenv, view='raw')
        enabled = self.enabled(paths, saltenv, files=tops, view='raw')
        disabled = self.disabled(paths, saltenv, files=tops, view='raw')
        return self._status(disabled=disabled, enabled=enabled)

    def enabled(self, paths=None, saltenv=None, files=None, view=None,
                flat=False):
        '''
        '''
        # Convert paths to top_paths
        #toppaths = self.toppath(paths, saltenv)
        toppaths, unseen = self.prepare_paths(paths)

        enabled = self.files(saltenv=saltenv,
                             files=files,
                             view='raw',
                             toppath=toppaths,
                             abspath=self.pattern_enable)

        view = view or ['saltenv', 'abspath']
        return fileinfo.fileinfo_view(enabled, view=view, flat=flat)

    #
    # TODO:
    # =====
    #
    # masked values (/dev/null) could fail the virtual()
    #   - Not sure how to handle that; monkey patch? or add into the section
    #     where the modules initially loads
    #
    # enabled; disabled should be same as is_enabled; IE only print status
    #                   - Use reporting / status  for path details or provide
    #                     options for more detail
    #
    # symlinks = client.symlink_list(saltenv='base',  prefix='')
    # enabled = top in symlinks
    #

    def disabled(self, paths=None, saltenv=None, files=None, view=None,
                 flat=False):
        '''
        '''
        # Convert paths to top_paths
        toppaths, unseen = self.prepare_paths(paths)

        all_tops = self.files(saltenv=saltenv,
                              files=files,
                              view='raw',
                              toppath=toppaths)

        # Don't include enabled tops
        enabled = set(self.enabled(paths=paths,
                                   saltenv=saltenv,
                                   files=files,
                                   view='raw'))

        # Don't include tops link target
        enabled.update(set(self.include_links(enabled)))

        disabled = set(all_tops).difference(enabled)

        view = view or ['saltenv', 'abspath']
        return fileinfo.fileinfo_view(disabled, view=view, flat=flat)

    def enable(self, paths=None, saltenv=None, view=None, flat=None):
        '''
        '''
        results = DefaultOrderedDict(list)
        toppaths, unseen = self.prepare_paths(paths)

        if toppaths:
            tops = self.disabled(paths=toppaths,
                                 saltenv=saltenv,
                                 view='raw')

            for topinfo in tops:
                topdir = os.path.join(self.topd_base,
                                      self.topd_directory,
                                      topinfo.saltenv)
                topfile = topinfo.toppath + '.top'
                path = os.path.join(topdir, topinfo.toppath)
                if not os.path.exists(topdir):
                    os.makedirs(topdir)

                if not os.path.exists(path):
                    os.symlink(topinfo.abspath, path)
                    results['enabled'].append(topinfo.toppath)
                    toppaths.remove(topinfo.toppath)

        if toppaths:
            enabled = self.enabled(paths=toppaths,
                                   saltenv=saltenv,
                                   view='raw')
            for topinfo in enabled:
                results['unchanged'].append(topinfo.toppath)
                toppaths.remove(topinfo.toppath)

        if unseen:
            for path in unseen:
                results['error'].append(path)

        return results

    def disable(self, paths=None, saltenv=None, view=None, flat=None):
        '''
        '''
        results = DefaultOrderedDict(list)
        toppaths, unseen = self.prepare_paths(paths)

        if toppaths:
            tops = self.enabled(paths=paths,
                                saltenv=saltenv,
                                view='raw')

            for topinfo in tops:
                if os.path.exists(topinfo.abspath):
                    os.remove(topinfo.abspath)
                    results['disabled'].append(topinfo.toppath)

        if toppaths:
            tops = self.disabled(paths=toppaths,
                                 saltenv=saltenv,
                                 view='raw')
            for topinfo in tops:
                results['unchanged'].append(topinfo.toppath)
                toppaths.remove(topinfo.toppath)

        if unseen:
            for path in unseen:
                results['error'].append(path)
        return results

    def _status(self, view=None, flat=None, **kwargs):
        view = view or ['saltenv', 'abspath']
        status = {}
        for key, topinfo in six.iteritems(kwargs):
            if topinfo:
                status[key] = fileinfo.fileinfo_view(topinfo,
                                                     view=view,
                                                     flat=flat)
        return status

    def _report(self, files=None, saltenv=None, patterns=None):
        if not files:
            saltenvs = self.saltenvs(saltenv)
            files = self.files(saltenvs, view='raw', **patterns)
        report = OrderedDict()

        for pathinfo in files:
            info = self.info(pathinfo)
            info['is_toppath'] = self.is_toppath(pathinfo)
            info['toppath'] = self.toppath(pathinfo)
            report[self.get(pathinfo, 'abspath')] = info
        return report

    # XXX: need to re-add filtering back in
    def report(self, paths=None, saltenv=None):
        from timeit import default_timer as timer
        print('Report 1: Starting timer...')
        start = timer()
        report1 = self._report(files=self.files(saltenv, flat=False))
        end = timer()
        print 'Report 1 Time: {0}'.format(end - start)
        print

        print('Report 2: Starting timer...')
        start = timer()
        tops = self.files(paths=paths,
                          saltenv=saltenv,
                          view='raw',
                          flat=False)
        disabled = self.disabled(paths=paths,
                                 saltenv=saltenv,
                                 files=tops,
                                 view='raw',
                                 flat=False)
        enabled = self.enabled(paths=paths,
                               saltenv=saltenv,
                               files=tops,
                               view='raw',
                               flat=False)
        report2 = self._status(all=tops,
                               disabled=disabled,
                               enabled=enabled)
        end = timer()
        print 'Report 2 Time: {0}'.format(end - start)
        print

        print('Report 3: Starting timer...')
        start = timer()
        report3 = OrderedDict()
        report3['all'] = self._report(tops)
        report3['disabled'] = self._report(disabled)
        report3['enabled'] = self._report(enabled)
        end = timer()
        print 'Report 3 Time: {0}'.format(end - start)
        print

        return report3

