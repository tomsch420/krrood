from typing_extensions import get_origin, get_args


def get_generic_type_param(cls, generic_base):
    """
    Given a subclass and its generic base, return the concrete type parameter(s).

    Example:
        get_generic_type_param(Employee, Role) -> (<class '__main__.Person'>,)
    """
    for base in getattr(cls, "__orig_bases__", []):
        if get_origin(base) is generic_base:
            return get_args(base)
    return None
