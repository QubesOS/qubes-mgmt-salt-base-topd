# -*- coding: utf-8 -*-
#
# vim: set ts=4 sw=4 sts=4 et :
'''
:maintainer:    Jason Mehring <nrgaway@gmail.com>
:maturity:      new
:depends:       none
:platform:      all

Salt fileinfo utilities for locating file paths, searching and returning
specific file views.
'''
# Import python libs
import collections
import logging
import os

from itertools import (
    chain,
    compress,
    imap,
    )

# Import salt libs
import salt.ext.six as six

from salt.utils.odict import OrderedDict

# Import custom libs
import matcher

# Enable logging
log = logging.getLogger(__name__)

try:
    __context__['salt.loaded.ext.util.fileinfo'] = True
except NameError:
    __context__ = {}

# Define the module's virtual name
__virtualname__ = 'fileinfo'


def __virtual__():
    '''
    '''
    return __virtualname__


class FileInfo(object):
    def __init__(self, fields=None, match_each=True, **patterns):
        self.fields = fields or ['root', 'abspath', 'relpath']
        self.match_each = match_each
        self.patterns = patterns

        self.Info = collections.namedtuple('Info', self.fields)
        self._elements = set()
        self.pattern = self.element()

    @property
    def pattern(self):
        return self._pattern

    @pattern.setter
    def pattern(self, element):
        self._pattern = get_pattern(element, **self.patterns)
        return self._pattern

    @property
    def as_sequence(self):
        if self.pattern and not self.match_each:
            return list(matcher.ifilter(self._elements, _pattern=pattern))
        return list(self._elements)

    @property
    def elements(self):
        return self._elements

    @elements.setter
    def elements(self, value):
        self._elements = value

    def element(self, root=None, abspath=None, **kwargs):
        '''
        kwargs contain extra information for custom methods

        This method must return a valid empty object if no vars are passed
        to allow introspection to create patterns.
        '''
        if root is None and abspath is None:
            root = os.path.abspath('.')
            abspath = os.path.abspath('.')
        relpath = os.path.relpath(abspath, root)

        element = self.Info(
            root=root,
            abspath=abspath,
            relpath=relpath
        )

        element_hook = kwargs.get('_element_hook', None)
        if element_hook:
            element = element_hook(self, element, **kwargs)

        return element

    def add_element(self, element, **kwargs):
        add_hook = kwargs.get('_add_hook', None)
        if add_hook:
            element = add_hook(self, element, **kwargs)

        self._elements.add(element)

    def filelist(self, roots, **kwargs):
        '''
        roots:
            file_roots, pillar_roots, cache_roots, etc to walk

        kwargs:
            Contains any extra variables to pass to element

        '''
        for root, abspath in walk(roots):
            element = self.element(root, abspath, **kwargs)

            if self.match_each and not all(matcher.match([element], self.pattern)):
                continue

            self.add_element(element, **kwargs)

        return self.as_sequence


def find(files, **patterns):
    '''
    Search files based on one or more patterns, where patterns consist of
    the files 'index_name = pattern' such as:
        relpath = [r'.*\.sls']
    '''
    return list(matcher.ifilter(files, **patterns))


def walk(dirnames, followlinks=True):
    '''
    Helper util to return a list of files in a directory
    '''
    for dirname in dirnames:
        if not os.path.isdir(dirname):
            dirname = os.path.dirname(dirname)

        for root, dirs, files in os.walk(dirname, followlinks=followlinks):
            for filename in files:
                yield dirname, os.path.join(root, filename)


def get_pattern(element, pattern=False, **patterns):
    '''
    Get a compiled pattern based on element fields and pattern one time.

    If a compiled pattern is not returned on the first attempt, pattern
    will return None.
    '''
    if pattern or pattern is None:
        return pattern

    if '_regex' not in patterns:
        patterns['_regex'] = False
    if '_escape' not in patterns:
        patterns['_escape'] = None

    return matcher.get_pattern(element, **patterns)


##def fileinfo(roots, match_each=True, **patterns):
##    '''
##    roots:
##        file_roots, pillar_roots, cache_roots, etc to walk
##
##    match_each:
##        If True, each file path is matched which prevents uses less memory
##        but sacrifices performance a little bit.  If False, the complete
##        list is matched after all the file infomations has been added to
##        fileinfo
##
##    patterns:
##        Contains the patterns to match.
##        Example:
##            { 'saltenv': 'base', 'relpath': [r'.*\.sls'] }
##    '''
##    fileinfo = OrderedDict()
##    pattern = False
##
##    for root, abspath in walk(roots):
##        info = fileinfo.get(key, OrderedDict())
##        info['root'] = root
##        info['abspath'] = abspath
##
##        if pattern is False:
##            pattern = get_pattern(info, pattern, **patterns)
##        if pattern and match_each:
##            match = all(matcher.match([info], pattern))
##        else:
##            match = True
##
##        if match and key not in fileinfo:
##            fileinfo[key] = info
##
##    # Filter files using selected patterns
##    if pattern is False:
##        pattern = get_pattern(info, pattern, **patterns)
##    if pattern and not match_each:
##        fileinfo = list(matcher.ifilter(fileinfo, _pattern=pattern))
##
##    return fileinfo.values()


def get_view(sequence, view=None, flat=None):
    '''
    Determine type of view to return (flattened, reduceby, raw)
    '''
    if not sequence:
        return sequence

    view = view if view else []
    if isinstance(view, six.string_types):
        view = [view]

    labels = matcher.extract_labels(*sequence)
    if 'raw' in view:
        view = labels
    selectors = matcher.generate_selectors(labels, *view)
    fields = list(compress(labels, selectors))

    viewinfo = {
        'labels': labels,
        'fields': fields,
        'selectors': selectors,
        'primary_key': fields[0],
        'secondary_key': fields[-1],
    }

    if len(fields) in [1] and flat:
        viewinfo['mode'] = 'flat'
    elif len(fields) in [1,2]:
        viewinfo['mode'] = 'reduceby'
    else:
        viewinfo['mode'] = 'raw'

    return viewinfo


def fileinfo_view(fileinfo, view=None, flat=False):
    '''
    Determine and return fileinfo view which can be one of flattened,
    reduceby (dictionary) or raw (un-modified).
    '''
    if not fileinfo:
        return fileinfo

    # Determine type of view to return (flattened, reduceby, raw)
    viewinfo = get_view(fileinfo,
                        view=view,
                        flat=flat)

    # Flatten
    if 'flat' in viewinfo['mode']:
        fileinfo = flatten(viewinfo['primary_key'], fileinfo)

    # Return dictionary using `key` as key index
    elif 'reduceby' in viewinfo['mode']:
        fileinfo = reduceby(viewinfo['primary_key'],
                            viewinfo['secondary_key'],
                            fileinfo)
        if flat:
            fileinfo = flatten(viewinfo['secondary_key'], fileinfo)

    return fileinfo


def flatten(key, sequence):
    '''
    Flattens (reduces) sequence by key. Returns a list.

    key:
        sequence key of data to flatten

    sequence:
        list of objects

    Example
    -------

    >>> data = [
    ...     {'saltenv': 'base',
    ...      'relpath': 'test/init.sls',
    ...      'is_pillar': True},
    ...     {'saltenv': 'base',
    ...      'relpath': 'test/test.sls',
    ...      'is_pillar': True},
    ...     {'saltenv': 'all',
    ...      'relpath': 'demo/demo.sls',
    ...      'is_pillar': True}
    ... ]

    >>> flatten('relpath', data)

    ['test/init.sls', 'test/test.sls', 'demo/demo.sls']
    '''
    if not sequence:
        return []

    try:
        # Mapping
        return sorted(chain.from_iterable(sequence.values()))
    except AttributeError:
        # Sequence
        getter = matcher.getter(key, *sequence)
        return sorted(imap(lambda s: getter(s), sequence))


def reduceby(key, field, sequence):
    '''
    Groups sequence by group key and reduces (only contains) values from
    the field key. Returns a dictionary

    key:
        sequence key to use to group data

    field:
        sequence key used to populate group data

    sequence:
        list of objects

    Example
    -------

    >>> data = [
    ...     {'saltenv': 'base',
    ...      'relpath': 'test/init.sls',
    ...      'is_pillar': True},
    ...     {'saltenv': 'base',
    ...      'relpath': 'test/test.sls',
    ...      'is_pillar': True},
    ...     {'saltenv': 'all',
    ...      'relpath': 'demo/demo.sls',
    ...      'is_pillar': True}
    ... ]

    >>> reduceby('saltenv', 'relpath', data)

    {'all': ['demo/demo.sls'], 'base': ['test/init.sls', 'test/test.sls']}
    '''
    def add_field_item(group_list, info):
        '''
        Field value to add.  Will be added to dictionary[key]
        as its value
        '''
        field_key = matcher.getter(field, info)
        value = field_key(info)
        if value not in group_list:
            group_list.append(value)
        return group_list

    odict = OrderedDict()

    if not sequence:
        return odict

    getter = matcher.getter(key, *sequence)
    for item in sequence:
        key = getter(item)
        if key not in odict:
            odict[key] = list()
        odict[key] = add_field_item(odict[key], item)
    return odict
