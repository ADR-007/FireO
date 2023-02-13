import re

from google.cloud import firestore


def collection_name(model):
    return re.sub('(?!^)([A-Z]+)', r'_\1', model).lower()


def ref_path(key):
    return key.split('/')


def collection_path(key):
    return '/'.join(key.split('/')[:-1])


def get_parent(key):
    return collection_path(key)


def get_parent_doc(key):
    return '/'.join(key.split('/')[:-2])


def get_id(key):
    try:
        return key.split('/')[-1]
    except AttributeError:
        return None


def GeoPoint(latitude: float, longitude: float):
    return firestore.GeoPoint(latitude, longitude)


def get_nested(dict, *args):
    if args and dict:
        element = args[0]
        if element:
            value = dict.get(element)
            return value if len(args) == 1 else get_nested(value, *args[1:])


def join_keys(first_arg, *args):
    """Join keys with dot.

    Example:
        >>> join_keys('a', 'b', 3, 'c')
        'a.b[3].c'
    """
    result = str(first_arg)
    for arg in args:
        if isinstance(arg, int):
            result += f'[{arg}]'
        else:
            result += f'.{arg}'

    return result


def get_flat_dict(dict_, prefix: str = None):
    """Get flat dict from nested dict by joining keys with dot.

    Example:
        >>> get_flat_dict({'a': 1, 'b': {'c': 2, 'd': {'e': 3}}})
        {'a': 1, 'b.c': 2, 'b.d.e': 3}
    """
    flat_dict = {}
    for key, value in dict_.items():
        if prefix:
            key = f'{prefix}.{key}'

        if isinstance(value, dict):
            flat_dict.update(get_flat_dict(value, key))
        else:
            flat_dict[key] = value
    return flat_dict


def generateKeyFromId(model, id):
    return model.collection_name + "/" + id


def isKey(str):
    return "/" in str


def remove_none_field(values):
    """Remove None values from dict or list.

    Example:
        >>> remove_none_field({'a': 1, 'b': None})
        {'a': 1}
    """
    if isinstance(values, list):
        return [remove_none_field(v) for v in values]

    if not isinstance(values, dict):
        return values

    result = {}
    for k, v in values.items():
        if v is not None:
            if isinstance(v, (dict, list)):
                v = remove_none_field(v)

            result[k] = v

    return result
