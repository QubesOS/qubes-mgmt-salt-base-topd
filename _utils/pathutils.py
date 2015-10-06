# -*- coding: utf-8 -*-
#
# vim: set ts=4 sw=4 sts=4 et :
'''
:maintainer:    Jason Mehring <nrgaway@gmail.com>
:maturity:      new
:depends:       none
:platform:      all

Salt file path utilities for locating file paths and converting paths.

Convert paths types to:
    - relpath(path, saltenv): |
        'topd/init.sls'

    - salt_path(path, saltenv):  |
        'salt://topd/init.sls'

    - cache_path(path, saltenv): |
        '/var/cache/salt/minion/files/base/topd/init.sls'
        'file:///var/cache/salt/minion/files/base/topd/init.sls'

    - local_path(path, saltenv): |
        '/srv/formulas/base/topd-formula/topd/init.sls'
        'file:///srv/formulas/base/topd-formula/topd/init.sls'

    - sls(path, saltenv): |
        'topd'

Determine current path type:
    - is_relpath(path, saltenv) -> boolean
    - is_salt_path(path, saltenv) -> boolean
    - is_cache_path(path, saltenv) -> boolean
    - is_local_path(path, saltenv) -> boolean
    - is_slspath(path, saltenv) -> boolean

Utils:
    - Get cache directory for given salt environment: |
        cache_dir(saltenv):  |
            '/var/cache/salt/minion/files/base'

    - Loacte file_root for any path:
        file_root(path, saltenv='base')

Filter:
    by env and/or pattern
'''


# Import python libs
import collections
import copy
import logging
import os

from functools import  update_wrapper
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
from salt.utils.odict import (
    OrderedDict,
    DefaultOrderedDict
    )

# Import custom libs
import matcher
import fileinfo

from pathinfo import PathInfo

# Enable logging
log = logging.getLogger(__name__)

try:
    __context__['salt.loaded.ext.util.pathutils'] = True
except NameError:
    __context__ = {}

# Define the module's virtual name
__virtualname__ = 'pathutils'


def __virtual__():
    '''
    '''
    return __virtualname__


class PathUtils(object):
    '''
    Mapping and various utility functions for salt paths.
    '''
    def __init__(self, opts, pillar=False, *varargs, **kwargs):
        self.opts = opts
        self.pillar = pillar

        self.client = salt.fileclient.get_file_client(self.opts, self.is_pillar())
        self.server = salt.fileserver.Fileserver(self.opts)

        self._states = DefaultOrderedDict(list)
##        self._toplist = None
        self._saltenvs = self.client.envs()

    def saltenv(self, path, saltenv=None):
        '''
        Returns the saltenv for path if saltenv is None and path is found
        '''
        if saltenv:
            return saltenv

        files = self.find(relpath=path)
        saltenvs = list(imap(lambda s: self.get(s, 'saltenv'), files))
        if saltenvs:
            return saltenvs[0]
        return None

    def get(self, element, key):
        return matcher.getter(key, element)(element)

    def saltenvs(self, saltenv=None):
        '''
        Return either the passed saltenv as a list or client.envs if saltenv
        is None.

        Also move 'base' env to start of list since list is used to find paths
        when no saltenv is passed or known to make sure 'base' is searched
        first.
        '''
        if saltenv:
            saltenvs = saltenv
            if isinstance(saltenv, six.string_types):
                saltenvs = [saltenvs]
        else:
            if not self._saltenvs:
                self._saltenvs = self.client.envs()
            saltenvs = self._saltenvs

        if 'base' in saltenvs and saltenvs[0] != 'base':
            saltenvs.insert(0, saltenvs.pop(saltenvs.index('base')))
        return saltenvs

    def pathinfo_roots(self, saltenvs=None, include=None):
        '''
        Returns a dictionay of pillar roots which will contain both the
        saltenv and directories used when gathering files.

        saltenvs:
            List of salt evnironments to include within roots.

        include:
            List of roots to include (cache_roots, file_roots and/or
            pillar_roots).  If include is None, all roots are included.
        '''
        if isinstance(include, six.string_types):
            include = [include]
        default_includes = ['cache_roots', 'file_roots', 'pillar_roots']
        include = include if include else default_includes

        saltenvs = self.saltenvs(saltenvs)
        roots = set()

        Roots = collections.namedtuple('Roots', 'saltenv root')
        def to_named_tuple(element):
            return  list(Roots(saltenv, root)
                         for saltenv, roots in six.iteritems(element)
                         for root in roots
                         if saltenv in saltenvs)

        if 'cache_roots' in include:
            roots.update(set(starmap(
                lambda *x: Roots(x[-1], os.path.join(*x)),
                product(
                    [self.opts['cachedir']],
                    ['files', 'localfiles'],
                    saltenvs))))

        if 'file_roots' in include:
            roots.update(to_named_tuple(self.opts['file_roots']))

        if 'pillar_roots' in include:
            roots.update(to_named_tuple(self.opts['pillar_roots']))

        return fileinfo.reduceby('saltenv', 'root', roots)

    def files(self,
              saltenv=None,
              roots=None,
              view=None,
              files=None,
              flat=None,
##              fileinfo_extra=None,
              pathinfo=None,
              **patterns):
        '''
        Return a list of the files in the file server's specified environment
        or a dictionary of all results if saltenv is None.

        All files will be filtered if a pattern is supplied.

        saltenv:
            Can be a single saltenv such as 'base', a list of saltenv's such
            as ['base', 'all'], or None in which case all saltenv's will be
            set

        patterns:
            Only return files that match wildcard pattern filter such as
            '*.tops'

        flat:
            If True, a list of all environment values will be returned,
            otherwise a dictionary with the passed saltenv will be returned.
            The default for a single salt environment is to flatten

        pathinfo:
            FileInfo instance to use to parse filelist
        '''
        if files:
            return self.find(files, **patterns)

        # Convert saltenv to list; include all environments if saltenv is None
        saltenvs = self.saltenvs(saltenv)

        # XXX: Test with get_top; maybe don't need cache_roots / file_roots
        #      if pillar is True
        # Get default file_roots, pillar_roots and cache_roots if roots is None
        if not roots:
            roots = self.pathinfo_roots(saltenvs)

        # Select patterns to use for filtering file list or defualt to selected
        # saltenvs
        patterns = patterns or dict(saltenv=saltenvs)

        # XXX: Add a way to determine which object to use?
        #      topinfo may want to have different object; maybe a routine
        #      that calls this one first so as not to overload file signature
        # Walk roots to retreive a listing of all files
        pathinfo = pathinfo or PathInfo(match_each=True, **patterns)

        # Extra kwargs for pathinfo
        extra_kwargs = {}
        extra_kwargs['cachedir'] = self.opts.get('cachedir', None)
        extra_kwargs['is_pillar'] = self.is_pillar()

        # Generate filtered pathinfo list
        files = pathinfo.filelist(roots=roots, **extra_kwargs)

        # Determine and return pathinfo view which can be one of flattened,
        # reduceby (dictionary) or all (un-modified).
        if len(saltenvs) == 1 and flat is None:
            flat = True
        view = view or ['saltenv', 'relpath']
        return fileinfo.fileinfo_view(files, view=view, flat=flat)

    def find(self, files=None, **patterns):
        '''
        Search files based on one or more patterns, where patterns consist of
        the files 'index_name = pattern' such as:
            relpath = ['*.sls']
        '''
        if files is None:
            files = self.files(view='raw')
        return fileinfo.find(files, **patterns)

    def states(self, saltenv=None):
        '''
        Return a list of state files in the specified environment
        or a dictionary of all results if saltenv is None.
        '''
        states = {}
        for saltenvs in self.saltenvs(saltenv):
            # Cache states
            if saltenv not in self._states:
                self._states[saltenv] = self.client.list_states(saltenv)
            states[saltenv] = copy.deepcopy(self._states[saltenv])
        return states

##    # XXX Move to top_utils; have top_utils extend path_utils
##    def tops(self, saltenv=None):
##        '''
##        Return a list of tops files in the specified environment or a dictionary
##        of all results if saltenv is None.
##        '''
##        if self._toplist is None:
##            self._toplist = self.files(saltenv=saltenv,
##                                       view='raw',
##                                       relpath=['*.top'])
##        toplist = copy.deepcopy(self._toplist)
##
##        tops = DefaultOrderedDict(list)
##        for info in toplist:
##            relpath = self.get(info, 'relpath')
##            if salt.utils.is_windows():
##                relpath = relpath.replace('\\', '/')
##            if relpath.endswith('{0}init.top'.format('/')):
##                tops[self.get(info, 'saltenv')].append(
##                    relpath.replace('/', '.')[:-9])
##            else:
##                tops[self.get(info, 'saltenv')].append(
##                    relpath.replace('/', '.')[:-4])
##        return tops

    def report(self, files=None, saltenv=None, patterns=None):
        if not files:
            saltenvs = self.saltenvs(saltenv)
            files = self.files(saltenvs, view='raw', **patterns)
        report = OrderedDict()

        for pathinfo in files:
            report[self.get(pathinfo, 'abspath')] = self.info(pathinfo)
        return report

    def info(self, pathinfo):
        '''
        Returns a mapping of paths if found or '' if not found.
        '''
        info = OrderedDict()
        try:
            info['pathinfo'] = pathinfo._asdict()
        except AttributeError:
            info['pathinfo'] = pathinfo
        info['saltenv'] = self.get(pathinfo, 'saltenv')
        info['file_root'] = self.get(pathinfo, 'file_root')
        info['relpath'] = self.get(pathinfo, 'relpath')
        info['abspath'] = self.get(pathinfo, 'abspath')
        info['cache_path'] = self.cache_path(pathinfo)
        if info['cache_path']:
            info['cache_path_exists'] = os.path.exists(info['cache_path'])
        info['local_path'] = self.local_path(pathinfo)
        if info['local_path']:
            info['local_path_exists'] = os.path.exists(info['local_path'])
        #info['server_path'] = self.server.find_file(self.get(pathinfo, 'relpath'),
        #                                            self.get(pathinfo, 'saltenv'))
        info['salt_path'] = self.salt_path(pathinfo)
        info['slspath'] = self.slspath(pathinfo)
        info['is_pillar'] = self.get(pathinfo, 'is_pillar')
        #info['test'] = self.get(pathinfo, 'file_root').split('|')
        return info

    def _normpath(self, path):
        if not salt.utils.urlparse(path).scheme:
            return os.path.normpath(path)
        return path

    def is_pillar(self):
        opts = self.opts
        #opts = self.client.opts
        return True if opts['file_roots'] is opts['pillar_roots'] else False

    def path_type(self, path, saltenv=None):
        '''
        Return path type.
        '''
        saltenv = saltenv or self.saltenv(path, saltenv)
        path = self._normpath(path)

        if self.is_relpath(path, saltenv):
            return 'relpath'

        elif self.is_slspath(path, saltenv):
            return 'sls'

        elif self.is_cache_path(path):
            return 'cache_path'

        elif self.is_local_path(path):
            return 'local_path'

        elif self.is_salt_path(path):
            return 'salt_path'

        else:
            return 'unknown'

    def path(self, path, saltenv=None, path_type=None):
        '''
        Relative salt path is the base path that all paths rely on.  Any
        conversions from formats that are not relative will happen here.
        '''
        if isinstance(path, list):
            return [self.path(p, saltenv) for p in path]

        path = self._normpath(path)
        saltenv = saltenv or self.saltenv(path, saltenv)
        url = salt.utils.urlparse(path)
        path_type = path_type or self.path_type(path, saltenv)

        if path_type in ['relpath']:
            #return url.path
            return path

        if path_type in ['slspath']:
            source = self.client.get_state(url.path, saltenv).get('source')
            return salt.utils.url.parse(source)[0]

        if path_type in ['cache_path']:
            return os.path.relpath(url.path, self.cache_dir(saltenv))

        if path_type in ['local_path']:
            roots = self.file_root(url.path, saltenv)
            for root in roots:
                if not self.is_cache_path(root):
                    return os.path.relpath(url.path, root)
            return ''

        if path_type in ['salt_path']:
            return url.netloc + url.path

        raise SaltRenderError('Could not find relpath for {0}'.format(path))

    def is_relpath(self, path, saltenv=None):
        '''
        path:      'topd/init.sls'
        relpath:   'topd/init.sls'
        '''
        try:
            saltenv = saltenv or self.saltenv(path, saltenv)
            url = salt.utils.urlparse(path)
            if not salt.utils.url.validate(path, ['']) or os.path.isabs(url.path):
                return False
            return not self.is_slspath(url.path, saltenv)
        except AttributeError:
            return False

    def relpath(self, path, saltenv=None):
        '''
        path:      'topd/init.sls'
        relpath:   'topd/init.sls'
        '''
        if isinstance(path, list):
            return [self.relpath(p, saltenv) for p in path]
        try:
            return self.get(path, 'relpath')
        except AttributeError:
            pass
        if self.is_relpath(path, saltenv):
            return path
        return self.path(path, saltenv)

    def is_salt_path(self, path):
        '''
        salt_path: 'salt://topd/init.sls'
        '''
        #try:
        #    return salt.utils.url.validate(path, ['salt'])
        #except AttributeError:
        #    return False
        if isinstance(path, six.string_types):
            return salt.utils.url.validate(path, ['salt'])
        return False

    def salt_path(self, path, saltenv=None):
        '''
        salt_path: 'salt://topd/init.sls'
        '''
        if isinstance(path, list):
            return [self.salt_path(p, saltenv) for p in path]
        if self.is_salt_path(path):
            return path
        try:
            relpath = self.get(path, 'relpath')
        except AttributeError:
            saltenv = saltenv or self.saltenv(path, saltenv)
            relpath = self.relpath(path, saltenv)
        if not relpath:
            return ''
        return salt.utils.url.create(relpath)

    def cache_dir(self, saltenv):
        '''
        cache_dir: '/var/cache/salt/minion/files/base'
        '''
        return salt.utils.path_join(self.opts['cachedir'],
                                    'files',
                                    saltenv)

    def is_cache_path(self, path):
        '''
        cache_path: '/var/cache/salt/minion/files/base/topd/init.sls'
                    'file:///var/cache/salt/minion/files/base/topd/init.sls'
        '''
        #if self.is_pillar():
        #    return False
        try:
            return os.path.commonprefix(
                [self.get(path, 'abspath'), self.opts['cachedir']]) == self.opts['cachedir']
        except AttributeError:
            if salt.utils.url.validate(path, ['', 'file']):
                url = salt.utils.urlparse(path)
                return os.path.commonprefix(
                    [url.path, self.opts['cachedir']]) == self.opts['cachedir']
        return False

    def cache_path(self, path, saltenv=None):
        '''
        cache_path: '/var/cache/salt/minion/files/base/topd/init.sls'
                    'file:///var/cache/salt/minion/files/base/topd/init.sls'
        '''
        if isinstance(path, list):
            return [self.cache_path(p, saltenv) for p in path]
        #if self.is_pillar():
        #    return ''
        try:
            if self.is_cache_path(self.get(path, 'abspath')):
                return self.get(path, 'abspath')
            return ''
        except AttributeError:
            pass
        if self.is_cache_path(path):
            return path
        saltenv = saltenv or self.saltenv(path, saltenv)
        relpath = self.relpath(path, saltenv)
        cache_path = salt.utils.path_join(self.cache_dir(saltenv), relpath)
        if os.path.exists(cache_path):
            return cache_path
        return ''

    def is_local_path(self, path):
        '''
        local_path: '/srv/formulas/base/topd-formula/topd/init.sls'
                    'file:///srv/formulas/base/topd-formula/topd/init.sls'
        '''
        try:
            path = self.get(path, 'abspath')
        except AttributeError:
            pass
        if salt.utils.url.validate(path, ['', 'file']):
            url = salt.utils.urlparse(path)
            return not self.is_cache_path(path) and os.path.isabs(url.path)
        return False

    def local_path(self, path, saltenv=None):
        '''
        local_path: '/srv/formulas/base/topd-formula/topd/init.sls'
                    'file:///srv/formulas/base/topd-formula/topd/init.sls'
        '''
        if isinstance(path, list):
            return [self.local_path(p, saltenv) for p in path]
        try:
            if self.is_local_path(self.get(path, 'abspath')):
                return self.get(path, 'abspath')
            return ''
        except AttributeError:
            if self.is_local_path(path):
                return path
            saltenv = saltenv or self.saltenv(path, saltenv)
            relpath = self.relpath(path, saltenv)
            files = self.find(relpath=path, saltenv=saltenv)
            #
            # XXX: Confirm the get in lambda is okay here
            #
            abspaths = list(imap(lambda s: self.get(s, 'abspath'), files))
            for abspath in abspaths:
                if not self.is_cache_path(abspath):
                    return abspath
            return ''

    def is_slspath(self, path, saltenv=None):
        '''
        slspath: 'topd'
        '''
        #saltenv = saltenv if saltenv else self.saltenv(path, saltenv)
        #for env in self.saltenvs(saltenv):
        #    if path in self.states(env):
        #        return True
        #return False
        return bool(set(ifilter(
            lambda x: x==path,
            chain.from_iterable(six.itervalues(self.states())))))

    def slspath(self, path, saltenv=None):
        '''
        slspath: 'topd'
        '''
        if isinstance(path, list):
            return [self.slspath(p, saltenv) for p in path]
        try:
            saltenv = self.get(path, 'saltenv')
            relpath = self.get(path, 'relpath')
        except AttributeError:
            saltenv = saltenv or self.saltenv(path, saltenv)
            relpath = self.relpath(path, saltenv)
        if not relpath:
            return ''
        sls = relpath.lower().split('/init.sls')[0]
        sls = os.path.splitext(sls)[0].replace('/', '.')
        if self.is_slspath(sls, saltenv):
            return sls
        return ''

##    # XXX Add to docs and report and path
##    # XXX Move to top_utils; have top_utils extend path_utils
##    def is_toppath(self, path, saltenv=None):
##        '''
##        toppath: 'salt'        (relpath: salt/init.top)
##        toppath: 'salt.minion' (relpath: salt/minion.top)
##        toppath: 'salt.minion' (relpath: topd/base|salt.minion)
##        '''
##        return bool(set(ifilter(
##            lambda x: x==path,
##            chain.from_iterable(six.itervalues(self.tops())))))
##
##    # XXX Add to docs and report and path
##    # XXX Move to top_utils; have top_utils extend path_utils
##    def toppath(self, path, saltenv=None):
##        '''
##        toppath: 'salt'        (relpath: salt/init.top)
##        toppath: 'salt.minion' (relpath: salt/minion.top)
##        toppath: 'salt.minion' (relpath: topd/base|salt.minion)
##        '''
##        if isinstance(path, list):
##            return [self.toppath(p, saltenv) for p in path]
##        try:
##            saltenv = self.get(path, 'saltenv')
##            relpath = self.get(path, 'relpath')
##        except AttributeError:
##            if self.is_toppath(path, saltenv):
##                return path
##            saltenv = saltenv or self.saltenv(path, saltenv)
##            relpath = self.relpath(path, saltenv)
##
##        # XXX: Change to self.topd_directory once moved to top_utils
##        topd_dir = self.opts.get(u'topd_dir', u'_topd')
##        if relpath.startswith(topd_dir):
##            relpath = relpath.split(topd_dir)[1]
##
##        top = relpath.lower().split('/init.top')[0]
##        top = os.path.splitext(top)[0].replace('/', '.')
##        if self.is_toppath(top, saltenv):
##            return top
##        return ''

    def file_root(self, path, saltenv=None):
        '''
        Return the file_root for a given path.
        '''
        if isinstance(path, list):
            return [self.file_root(p, saltenv) for p in path]

        try:
            return self.get(path, 'root')
        except AttributeError:
            pass
        saltenv = saltenv or self.saltenv(path, saltenv)
        relpath = self.relpath(path, saltenv)
        files = self.find(relpath=path, saltenv=saltenv)
        # XXX: Need to determine which one to return if more than one???
        roots = set(imap(lambda s: s.root, files))
        return sorted(roots)

def pathutils(opts, *varargs, **kwargs):
    return PathUtils(opts, *varargs, **kwargs)
