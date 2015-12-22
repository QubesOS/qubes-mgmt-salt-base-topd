# -*- coding: utf-8 -*-
#
# vim: set ts=4 sw=4 sts=4 et :
'''
:maintainer:    Jason Mehring <nrgaway@gmail.com>
:maturity:      new
:depends:       none
:platform:      all

Very simple adapter pattern loosely based on zope.interface

    >>> import collections
    >>> FIELDS = ('root', 'abspath', 'relpath')
    >>> class FileInfoTuple(collections.namedtuple('FileInfoTuple', FIELDS)):
    ...     pass

    >>> fileinfo = FileInfoTuple(root='',
    ...                          abspath='/var/cache/salt/minion/files/top.sls',
    ...                          relpath='top.sls')

    >>> fileinfo
    FileInfoTuple(root='', abspath='/var/cache/salt/minion/files/top.sls', relpath='top.sls')

Test Interfaces

    >>> class IRelpath(Interface):
    ...     """Interface for relpath."""

    >>> class IRootpath(Interface):
    ...     """Interface for rootpath."""

Test function factories

    >>> @adapter(FileInfoTuple, IRelpath)
    ... def relpath_namedtuple(context):
    ...     return context.relpath

    >>> @adapter(collections.Mapping, IRelpath)
    ... def relpath_mapping(context):
    ...     return context['relpath']

    >>> @adapter(six.string_types, IRelpath)
    ... def relpath_text(context):
    ...     return context

Test class factories

    >>> @adapter(FileInfoTuple, IRootpath)
    ... class RootPathNamedTuple(object):
    ...     def __init__(self, context):
    ...         self.context = context
    ...
    ...     def __call__(self):
    ...         return self.context.root

    >>> @adapter(collections.Mapping, IRootpath)
    ... class RootPathMapping(object):
    ...     def __init__(self, context):
    ...         self.context = context
    ...
    ...     def __call__(self):
    ...         return self.context['root']

    >>> @adapter(six.string_types, IRootpath)
    ... class RootPathText(object):
    ...     def __init__(self, context):
    ...         self.context = context
    ...
    ...     def __call__(self):
    ...         return self.context


Register adapters
=================

Either manually register the adapters, or use a decorator as shown in examples
above:

    >>> registry.register(FileInfoTuple, IRelpath, '', relpath_namedtuple)
    >>> registry.register(collections.Mapping, IRelpath, '', relpath_mapping)
    >>> registry.register(six.string_types, IRelpath, '', relpath_text)
    >>> registry.register(FileInfoTuple, IRootpath, '', RootPathNamedTuple)
    >>> registry.register(collections.Mapping, IRootpath, '', RootPathMapping)
    >>> registry.register(six.string_types, IRootpath, '', RootPathText)

    # Create a fileinfo objects of different types to use for adaption
    >>> fileinfo_tuple = FileInfoTuple(*fileinfo)
    >>> fileinfo_mapping = fileinfo._asdict()
    >>> fileinfo_relpath = fileinfo.relpath
    >>> fileinfo_rootpath = fileinfo.root

Query adapter
=============

    >>> registry.queryAdapter(fileinfo_tuple, IRelpath)
    'top.sls'
    >>> registry.queryAdapter(fileinfo_mapping, IRelpath)
    'top.sls'
    >>> registry.queryAdapter(fileinfo_relpath, IRelpath)
    'top.sls'

    >>> registry.queryAdapter(fileinfo_tuple, IRootpath) #doctest: +ELLIPSIS
    <__main__.RootPathNamedTuple object at 0x...>

    >>> registry.queryAdapter(fileinfo_mapping, IRootpath)  #doctest: +ELLIPSIS
    <__main__.RootPathMapping object at 0x...>

    >>> registry.queryAdapter(fileinfo_rootpath, IRootpath)  #doctest: +ELLIPSIS
    <__main__.RootPathText object at 0x...>

Adapt adapter
=============

    >>> adapt(IRelpath, fileinfo_tuple)
    'top.sls'
    >>> adapt(IRelpath, fileinfo_mapping)
    'top.sls'
    >>> adapt(IRelpath, fileinfo_relpath)
    'top.sls'

    >>> adapt(IRootpath, fileinfo_tuple)  #doctest: +ELLIPSIS
    <__main__.RootPathNamedTuple object at 0x...>

    >>> adapt(IRootpath, fileinfo_mapping)  #doctest: +ELLIPSIS
    <__main__.RootPathMapping object at 0x...>

    >>> adapt(IRootpath, fileinfo_rootpath)  #doctest: +ELLIPSIS
    <__main__.RootPathText object at 0x...>

Adapt using Interface
=====================

    >>> IRelpath(fileinfo_tuple)
    'top.sls'
    >>> IRelpath(fileinfo_mapping)
    'top.sls'
    >>> IRelpath(fileinfo_relpath)
    'top.sls'

    >>> IRootpath(fileinfo_tuple)  #doctest: +ELLIPSIS
    <__main__.RootPathNamedTuple object at 0x...>

    >>> IRootpath(fileinfo_mapping)  #doctest: +ELLIPSIS
    <__main__.RootPathMapping object at 0x...>

    >>> IRootpath(fileinfo_rootpath)  #doctest: +ELLIPSIS
    <__main__.RootPathText object at 0x...>

'''

from __future__ import absolute_import

# Import python libs
import collections
import logging
import sys

# Enable logging
log = logging.getLogger(__name__)

try:
    __context__['salt.loaded.ext.util.adapt'] = True
except NameError:
    __context__ = {}

# Define the module's virtual name
__virtualname__ = 'adapt'


def __virtual__():
    '''
    '''
    return __virtualname__


class AdaptationError(TypeError):
    pass


class AdapterRegistry(object):
    _registry = []

    def __init__(self):
        if not self._instance:
            pass

    # noinspection PyMethodParameters
    @property
    def registry(cls):  # pylint: disable=E0213
        return cls._registry

    @classmethod
    def register(
        cls, object_type, provided, name, factory
    ):  # pylint: disable=W0613
        pattern = (object_type, provided, factory)
        if pattern not in cls._registry:
            cls._registry.append(pattern)

    @classmethod
    def unregister(
        cls, object_type, provided, name, factory
    ):  # pylint: disable=W0613
        cls._registry.remove((object_type, provided, factory))

    def __new__(cls, *p, **k):  # pylint: disable=W0613
        if '_instance' not in cls.__dict__:
            cls._instance = object.__new__(cls, *p)
        return cls._instance

    @staticmethod
    def _check(_object, class_or_type_or_subclass):
        types = to_tuple(class_or_type_or_subclass)
        for _type in types:
            try:
                if isinstance(_object, _type):
                    yield True
                    continue
            except TypeError:
                try:
                    if issubclass(_object, _type):
                        yield True
                        continue
                except TypeError:
                    try:
                        if isinstance(_object, type(_type)):
                            yield True
                            continue
                    except TypeError:
                        pass
            yield False

    def queryAdapter(
        self,
        _object,
        provided,
        name=None,
        default=None
    ):  # pylint: disable=W0613
        for required, _provided, factory in self.registry:
            if all(self._check(_object, required)):
                if provided == _provided:
                    return factory(_object)
        return None


class InterfaceClass(object):
    def __init__(
        self,
        name,
        bases=(),
        attrs=None,
        __doc__=None,
        __module__=None
    ):  # pylint: disable=W0622

        if attrs is None:
            attrs = {}

        if __module__ is None:
            __module__ = attrs.get('__module__')
            if isinstance(__module__, str):
                del attrs['__module__']
            else:
                try:
                    # Figure out what module defined the Interface.
                    # This is how cPython figures out the module of
                    # a class, but of course it does it in C. :-/
                    # noinspection PyProtectedMember
                    __module__ = sys._getframe(1).f_globals[
                        '__name__'
                    ]  # pylint: disable=W0212
                except (AttributeError, KeyError):  # pragma NO COVERAGE
                    pass

        d = attrs.get('__doc__')
        if d is not None:
            if __doc__ is None:
                __doc__ = d
            del attrs['__doc__']

        if __doc__ is None:
            __doc__ = ''

        for base in bases:
            if not isinstance(base, InterfaceClass):
                raise TypeError('Expected base interfaces')

        self.__name__ = name
        self.__doc__ = __doc__
        self.__module__ = __module__
        self.__identifier__ = '{0}.{1}'.format(self.__module__, self.__name__)

    def __repr__(self):
        try:
            return self._v_repr
        except AttributeError:
            name = self.__name__
            m = self.__module__
            if m:
                name = '{0}.{1}'.format(m, name)
            r = '<{0} {1}>'.format(self.__class__.__name__, name)
            self._v_repr = r  # pylint: disable=W0201
            return r

    def __call__(self, _object):
        return registry.queryAdapter(_object, self)


def to_tuple(value):
    if not isinstance(value, collections.Sequence):
        value = (value, )
    return value


def adapter(required, provided, name=''):  # pylint: disable=W0613
    '''
    Decorator to register an adapter

    Args:
        required:
            Required object class(es), type(s), or subclass(es)

        provided:
            Provided adapter Interface

        name:
            Name adapter, default is unnamed adapter

    Example:
        @adapter((collections.Mapping,), IRelpath, '')
    '''

    def wrap(factory):
        registry.register(to_tuple(required), provided, '', factory)

        def wrapped_function(*args, **kwargs):
            factory(*args, **kwargs)

        return wrapped_function

    return wrap


def adapt(provided, _object):
    '''
    Allows adapting using IInterfaceName(object) for single adapters.

    Args:
        provided:
        _object:
    '''
    try:
        return registry.queryAdapter(_object, provided)
    except TypeError:
        raise AdaptationError


Interface = InterfaceClass('Interface', __module__='adapt')
registry = AdapterRegistry()
queryAdapter = registry.queryAdapter

if __name__ == '__main__':
    import doctest
    doctest.testmod()
