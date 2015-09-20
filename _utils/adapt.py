# -*- coding: utf-8 -*-
#
# vim: set ts=4 sw=4 sts=4 et :
'''
:maintainer:    Jason Mehring <nrgaway@gmail.com>
:maturity:      new
:depends:       none
:platform:      all

Very simple adapter pattern loosly based on zope.interface

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
    ... class Rootpath_NamedTuple(object):
    ...     def __init__(self, context):
    ...         self.context = context
    ...
    ...     def __call__(self):
    ...         return self.context.root

    >>> @adapter(collections.Mapping, IRootpath)
    ... class Rootpath_Mapping(object):
    ...     def __init__(self, context):
    ...         self.context = context
    ...
    ...     def __call__(self):
    ...         return self.context['root']

    >>> @adapter(six.string_types, IRootpath)
    ... class Rootpath_Text(object):
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
    >>> registry.register(FileInfoTuple, IRootpath, '', Rootpath_NamedTuple)
    >>> registry.register(collections.Mapping, IRootpath, '', Rootpath_Mapping)
    >>> registry.register(six.string_types, IRootpath, '', Rootpath_Text)

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
    <__main__.Rootpath_NamedTuple object at 0x...>

    >>> registry.queryAdapter(fileinfo_mapping, IRootpath)  #doctest: +ELLIPSIS
    <__main__.Rootpath_Mapping object at 0x...>

    >>> registry.queryAdapter(fileinfo_rootpath, IRootpath)  #doctest: +ELLIPSIS
    <__main__.Rootpath_Text object at 0x...>

Adapt adapter
=============

    >>> adapt(IRelpath, fileinfo_tuple)
    'top.sls'
    >>> adapt(IRelpath, fileinfo_mapping)
    'top.sls'
    >>> adapt(IRelpath, fileinfo_relpath)
    'top.sls'

    >>> adapt(IRootpath, fileinfo_tuple)  #doctest: +ELLIPSIS
    <__main__.Rootpath_NamedTuple object at 0x...>

    >>> adapt(IRootpath, fileinfo_mapping)  #doctest: +ELLIPSIS
    <__main__.Rootpath_Mapping object at 0x...>

    >>> adapt(IRootpath, fileinfo_rootpath)  #doctest: +ELLIPSIS
    <__main__.Rootpath_Text object at 0x...>

Adapt using Interface
=====================

    >>> IRelpath(fileinfo_tuple)
    'top.sls'
    >>> IRelpath(fileinfo_mapping)
    'top.sls'
    >>> IRelpath(fileinfo_relpath)
    'top.sls'

    >>> IRootpath(fileinfo_tuple)  #doctest: +ELLIPSIS
    <__main__.Rootpath_NamedTuple object at 0x...>

    >>> IRootpath(fileinfo_mapping)  #doctest: +ELLIPSIS
    <__main__.Rootpath_Mapping object at 0x...>

    >>> IRootpath(fileinfo_rootpath)  #doctest: +ELLIPSIS
    <__main__.Rootpath_Text object at 0x...>

'''

# Import python libs
import collections
import logging

# Import salt libs
import salt.ext.six as six

from salt.utils.odict import OrderedDict

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

    @property
    def registry(cls):
        return cls._registry

    @classmethod
    def register(cls, object_type, provided, name, factory):
        pattern = (object_type, provided, factory)
        if pattern not in cls._registry:
            cls._registry.append(pattern)

    @classmethod
    def unregister(cls, object_type, provided, name, factory):
        cls._registry.remove((object_type, provided, factory))

    def __new__(cls, *p, **k):
        if not '_instance' in cls.__dict__:
            cls._instance = object.__new__(cls, *p, **k)
        return cls._instance


    def _check(self, object, class_or_type_or_subclass):
        types = to_tuple(class_or_type_or_subclass)
        for _type in types:
            try:
                if isinstance(object, _type):
                    yield True
                    continue
            except TypeError:
                try:
                    if issubclass(object, _type):
                        yield True
                        continue
                except TypeError:
                    try:
                        if isinstance(object, type(_type)):
                            yield True
                            continue
                    except TypeError:
                        pass
            yield False

    def queryAdapter(self, object, provided, name=None, default=None):
        for required, _provided, factory in self.registry:
            if all(self._check(object, required)):
                #if all(self._check(provided, _provided)):
                if provided == _provided:
                    return factory(object)
        return None


class InterfaceClass(object):
    def __init__(self, name, bases=(), attrs=None, __doc__=None,
                 __module__=None):

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
                    __module__ = sys._getframe(1).f_globals['__name__']
                except (AttributeError, KeyError): #pragma NO COVERAGE
                    pass

        d = attrs.get('__doc__')
        if d is not None:
            #if not isinstance(d, Attribute):
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
        self.__identifier__ = "%s.%s" % (self.__module__, self.__name__)

    def __repr__(self):
        try:
            return self._v_repr
        except AttributeError:
            name = self.__name__
            m = self.__module__
            if m:
                name = '%s.%s' % (m, name)
            r = "<%s %s>" % (self.__class__.__name__, name)
            self._v_repr = r
            return r

    def __call__(self, object):
        return registry.queryAdapter(object, self)


def to_tuple(value):
    if not isinstance(value, collections.Sequence):
        value = (value,)
    return value


def adapter(required, provided, name=''):
    '''
    Decorator to register an adapter

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
            function(*args, **kwargs)
        return wrapped_function
    return wrap


def adapt(provided, object):
    '''
    Allows adapting using IInterfaceName(object) for single adapters.
    '''
    try:
        return registry.queryAdapter(object, provided)
    except TypeError:
        raise AdaptationError


Interface = InterfaceClass('Interface', __module__='adapt')
registry = AdapterRegistry()
queryAdapter = registry.queryAdapter


if __name__ == "__main__":
    import doctest
    doctest.testmod()
