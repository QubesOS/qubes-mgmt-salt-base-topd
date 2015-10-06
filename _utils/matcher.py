# -*- coding: utf-8 -*-
#
# vim: set ts=4 sw=4 sts=4 et :
'''
:maintainer:    Jason Mehring <nrgaway@gmail.com>
:maturity:      new
:depends:       none
:platform:      all

--------------------------------------------------------------------------------
XXX: Create proper docs
--------------------------------------------------------------------------------

    regex:
        True: Patterns will be compiled using re.escape
        False: Patterns will be compiled using fnmarch.translate (glob
        pattern.

        Note:
            Multi-field matches require regex as the default search pattern
            syntax.

    labels:
        Optional list of field names used to describe the object(s) to be
        searched.  If the type of `labels` is an ordered dictionary
        or named tuple it's key values will be used to determine the labels
        and values to set the default patterns.

    escape:
        List of fields to escape the patterns within.  Will be escaped with
        re.escape if regex is True, otherwise fnmatch.translate

    patterns:
        For a single field object, pass patterns='default pattern'
        For a multi-field object search, pass either:

            If `labels` defined:
                `field_name = pattern`

            If `labels` not defined:
                `index = pattern`

    Example:

    Set default matcher patterns for each field to prevent needing to
    pass on when calling match methods

    >>> from collections import OrderedDict, namedtuple
    >>> labels = ('saltenv', 'file_root', 'abspath', 'relpath', 'is_pillar')
    >>> PathInfo = namedtuple('PathInfo', fields)
    >>> patterns = OrderedDict.fromkeys(labels, '.*')
    >>> patterns['relpath'] = '*[.]sls'
    >>> matcher = Matcher(labels=field_labels, **patterns)
'''

# Import python libs
import collections
import functools
import logging
import operator
import re

from itertools import (
    chain,
    compress,
    imap,
    )

# Import salt libs
import salt.ext.six as six

from salt.exceptions import SaltInvocationError
from salt.utils.odict import OrderedDict

# Enable logging
log = logging.getLogger(__name__)

try:
    __context__['salt.loaded.ext.util.matcher'] = True
except NameError:
    __context__ = {}

# Define the module's virtual name
__virtualname__ = 'matcher'

#REGEX_DEFAULT_PATTERN = [r'.*']
#GLOB_DEFAULT_PATTERN = [r'*']
DEFAULT_PATTERN = [r'.*']


def __virtual__():
    '''
    '''
    return __virtualname__


# XXX: Test
class Regex(six.text_type):
    '''
    Wrapper to be able to identify regex expressions
    '''
    pass


def getter(index, element, *ignored):
    if isinstance(element, collections.Mapping):
        getter = operator.itemgetter
    else:
        getter = operator.attrgetter

    if not index:
        return lambda x: ()
    if isinstance(index, list):
        return getter(*index)
    else:
        return getter(index)


def extract_labels(element=None, *ignored):
    '''
    Return an element's labels.

    Uses dictionary keys for a dictionary, _fileds for a namedtuple and
    index number for list or regular tuple
    '''
    if not element:
        return []

    try:
        # OrderedDict
        return element.keys()
    except AttributeError:
        try:
            # namedtuple
            return element._fields
        except AttributeError:
            pass

    return element


def generate_selectors(labels=None, *fields, **kwargs):
    '''
    Create an element list based in another objects labels that will create
    a value of True in the corresponding element if in either selectors
    or kwargs, otherwise False.

    Example:

    >>> labels = ['one', 'two', 'three', 'four']
    >>> fields = ['two', 'three']
    >>> generate_selectors(labels, fields)
    [False, True, True, False]
    '''
    if not labels:
        return []

    enabled = True if 'all' in fields or 'all' in kwargs else False
    selectors = [enabled for i in xrange(len(labels))]

    if enabled:
        return selectors

    for index, selector in enumerate(labels):
        if selector in fields or selector in kwargs:
            selectors[index] = True
    return selectors


def translate(pattern):
    '''
    Based on fnmatch.translate

    Translate a shell PATTERN to a regular expression.

    There is no way to quote meta-characters.
    '''
    i, n = 0, len(pattern)
    res = ''
    while i < n:
        c = pattern[i]
        i = i+1
        if c == '*':
            res = res + '.*'
        elif c == '?':
            res = res + '.'
        elif c == '[':
            j = i
            if j < n and pattern[j] == '!':
                j = j+1
            if j < n and pattern[j] == ']':
                j = j+1
            while j < n and pattern[j] != ']':
                j = j+1
            if j >= n:
                res = res + '\\['
            else:
                stuff = pattern[i:j].replace('\\','\\\\')
                i = j+1
                if stuff[0] == '!':
                    stuff = '^' + stuff[1:]
                elif stuff[0] == '^':
                    stuff = '\\' + stuff
                res = '%s[%s]' % (res, stuff)
        else:
            res = res + re.escape(c)
    return res


def escape_text(text, regex=False):
    '''
    Escape text for regex pattern match
    '''
    if isinstance(text, Regex):
        # Don't escape regex strings as they are assumed to be peoper syntax
        return text
    elif regex:
        return re.escape(text)
    return translate(text)


def get_default_pattern(regex):
    #if regex:
    #    return REGEX_DEFAULT_PATTERN
    #else:
    #    return GLOB_DEFAULT_PATTERN
    return DEFAULT_PATTERN


def compile(labels, **patterns):
    '''
    Compile patterns
    '''
    pattern = patterns.pop('_pattern', None)
    if pattern:
        return pattern

    regex = patterns.pop('_regex', False)
    escape = patterns.pop('_escape', [])

    if not patterns or not labels:
        return None

    # XXX: Think patterns should be re-created, not
    # popped, incase those values are needed elsewhere
    for pattern in list(patterns.keys()):
        if pattern not in labels:
            patterns.pop(pattern)
            #raise SaltInvocationError(
            #    'Invalid pattern key: {0}'.format(pattern))

##    # XXX: Maybe allow if new translate works
##    #
##    # Do not allow glob pattern matching on multi-field matches
##    regex = True if len(labels) > 1 else regex

    default_pattern = get_default_pattern(regex)
    escape = escape if escape else []
    _escape_text = functools.partial(escape_text, regex=regex)

    # Set default values and join patterns for each field
    pattern = OrderedDict.fromkeys(labels, None)
    for label in labels:
        if label in patterns and patterns[label]:
            field = patterns[label]
            if isinstance(field, re._pattern_type):
                field = [field.pattern]
            if isinstance(field, six.string_types):
                field = [field]
            if label in escape or not regex:
                field = [_escape_text(text) for text in field]
        else:
            field = default_pattern
        pattern[label] = r'(?:{0})'.format(r'|'.join(field))

    try:
        return re.compile(r'\n'.join(six.itervalues(pattern)),
                             re.MULTILINE|re.DOTALL)
    except NameError:
        raise

    # Should never get here
    raise


def itext(element):
    '''
    Converts element to a text string suitable for regex parsing.
    '''
    # Dictionary
    if isinstance(element, collections.Mapping):
        return '\n'.join(imap(six.text_type, six.itervalues(element)))

    # Tuple / list
    else:
        return '\n'.join(imap(six.text_type, element))


def match(sequence, pattern):
    '''
    Regex match

    sequence:
        Either a string, list of strings or list of lists / tuples
    '''
    if not pattern:
        return chain(sequence)

    # Match to text string created from element
    return imap(pattern.match, imap(itext, sequence))

# XXX: - Missing escaped
#      - Have some smart way of using regex to translate...
#      - maybe patterns can contain something, or escaped can be
#        either a list of tuples like:
#          escaped = {('relpath', GLOB)}
#      - TEST by escaping everything thats not already a regex expression?
#      - Switch to regex=False if new translate works

def get_pattern(sequence=None, *ignored, **patterns):
    if '_pattern' in patterns:
        return patterns['_pattern']
    labels = extract_labels(sequence)
    return compile(labels, **patterns)

def ifilter(sequence, **patterns):
    pattern = get_pattern(*sequence, **patterns)
    return compress(sequence, match(sequence, pattern))

def filter(sequence, **patterns):
    return list(ifilter(sequence, **patterns))
